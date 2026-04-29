"""Hypothesis lifecycle tracker.

States: proposed -> under_test -> {supported, refuted}
        proposed -> {supported, refuted}   (direct when an agent resolves it)

Resolution is mechanical: we scan `result` and `critique` entries for
[hyp #N] references and classify the referring text with a small keyword
verdict function. Conservative — ambiguous text leaves state at under_test.

The agent prompts already encourage [hyp #N] references (see archetype
system_prompts for replicator and critic). Agents who don't cite will not
produce transitions.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Literal

_HYP_REF_RE = re.compile(r"\[\s*hyp\s*#(\d+)\s*\]", re.IGNORECASE)

# Phrases that unambiguously signal refutation — they win over support stems
# even when the support stem appears inside them (e.g. "does not replicate"
# contains the support stem "replicat").
_COMPOUND_REFUTE: tuple[str, ...] = (
    "does not replicate", "does not reproduce",
    "does not hold", "does not survive",
    "fails to replicate", "fails to reproduce",
    "is not supported by",
)

# Stems — match all verb forms (confirm/confirms/confirmed, refute/refutes/refuted)
_SUPPORT_KEYWORDS: tuple[str, ...] = (
    "confirm", "validat", "holds up", "robust to",
    "surviv", "reproduc", "replicat",
    "consistent with", "supported by evidence",
)
_REFUTE_KEYWORDS: tuple[str, ...] = (
    "refute", "contradict", "disprov", "overturn",
    "is wrong", " flaw", "invalid",
    "category error", "architectural fallacy", "fallac",
    "leap of faith", "dangerous reduction",
)

Verdict = Literal["support", "refute", "neutral"]


def classify_verdict(text: str) -> Verdict:
    """Conservative keyword classifier.

    Order:
        1. Compound-refute phrases ("does not replicate") — always refute.
        2. Support + refute both present → neutral (comparative text).
        3. Otherwise, whichever signal fires.
    """
    lower = (text or "").lower()
    if any(k in lower for k in _COMPOUND_REFUTE):
        return "refute"
    support_hit = any(k in lower for k in _SUPPORT_KEYWORDS)
    refute_hit = any(k in lower for k in _REFUTE_KEYWORDS)
    if refute_hit and not support_hit:
        return "refute"
    if support_hit and not refute_hit:
        return "support"
    return "neutral"


def extract_hypothesis_refs(text: str) -> list[int]:
    return [int(m.group(1)) for m in _HYP_REF_RE.finditer(text or "")]


_VERDICT_TO_STATE = {
    "support": "supported",
    "refute": "refuted",
    "neutral": "under_test",
}


def resolve_hypothesis_refs(
    conn: sqlite3.Connection, *, project_id: int, turn: int
) -> dict[str, int]:
    """Scan result/critique entries from `turn` for [hyp #N] refs and
    transition referenced hypotheses. Never regresses supported/refuted
    back to under_test.

    Each transition appends a structured entry to the hypothesis's
    `resolutions_json` audit log capturing prev_state, new_state, the
    triggering entry, and the verdict — enough to reconstruct the
    full state history of any hypothesis.

    Returns counts by verdict type.
    """
    rows = conn.execute(
        "SELECT id, content, kind, agent_id FROM blackboard_entries "
        "WHERE project_id = ? AND turn = ? AND kind IN ('result', 'critique')",
        (project_id, turn),
    ).fetchall()
    counts = {"support": 0, "refute": 0, "neutral": 0}
    for r in rows:
        refs = extract_hypothesis_refs(r["content"] or "")
        if not refs:
            continue
        verdict: Verdict = classify_verdict(r["content"] or "")
        new_state = _VERDICT_TO_STATE[verdict]
        for hyp_id in refs:
            hyp = conn.execute(
                "SELECT state, resolutions_json FROM blackboard_entries "
                "WHERE id = ? AND project_id = ? AND kind = 'hypothesis'",
                (hyp_id, project_id),
            ).fetchone()
            if not hyp:
                continue
            current = hyp["state"] or "proposed"
            # Don't regress terminal states back to under_test.
            if current in ("supported", "refuted") and verdict == "neutral":
                continue
            # Skip no-op transitions (state would not actually change). This
            # keeps the audit log free of duplicate "supported -> supported"
            # entries when many critiques pile on after a verdict is reached.
            if current == new_state:
                continue
            resolutions = json.loads(hyp["resolutions_json"] or "[]")
            resolutions.append({
                "from_entry_id": r["id"],
                "kind": r["kind"],
                "verdict": verdict,
                "prev_state": current,
                "new_state": new_state,
                "turn": turn,
                "agent_id": r["agent_id"],
            })
            conn.execute(
                "UPDATE blackboard_entries "
                "SET state = ?, resolutions_json = ? WHERE id = ?",
                (new_state, json.dumps(resolutions), hyp_id),
            )
            counts[verdict] += 1
    conn.commit()
    return counts


def get_state_history(
    conn: sqlite3.Connection, *, project_id: int, hypothesis_id: int
) -> list[dict]:
    """Reconstruct the full state-transition history of a hypothesis from
    its resolutions_json audit log.

    Returns a chronological list of transitions, each a dict with keys
    `prev_state`, `new_state`, `turn`, `verdict`, `from_entry_id`, `agent_id`.

    Returns empty list if hypothesis has had no transitions (still in
    initial 'proposed' state).
    """
    row = conn.execute(
        "SELECT resolutions_json FROM blackboard_entries "
        "WHERE id = ? AND project_id = ? AND kind = 'hypothesis'",
        (hypothesis_id, project_id),
    ).fetchone()
    if not row:
        return []
    resolutions = json.loads(row["resolutions_json"] or "[]")
    # Filter to entries that captured a transition (post-#1 enrichment).
    # Older entries lacked prev_state/new_state — treat them as historical
    # transitions to a best-effort reconstructed new_state.
    history: list[dict] = []
    for r in resolutions:
        if "new_state" in r:
            history.append(r)
        elif "verdict" in r:
            # Legacy entry without explicit transition; reconstruct.
            history.append({
                **r,
                "prev_state": "(legacy unknown)",
                "new_state": _VERDICT_TO_STATE.get(r["verdict"], "under_test"),
            })
    history.sort(key=lambda x: (x.get("turn", 0), x.get("from_entry_id", 0)))
    return history


def hypotheses_in_play(
    conn: sqlite3.Connection, *, project_id: int, limit: int = 6
) -> list[tuple[int, str, str]]:
    """Return (id, state, content) for hypotheses currently under_test or
    proposed. Used to give agents a [hyp #N] reference list they can call
    out in their posts.
    """
    rows = conn.execute(
        "SELECT id, state, content FROM blackboard_entries "
        "WHERE project_id = ? AND kind = 'hypothesis' "
        "AND state IN ('proposed', 'under_test') "
        "ORDER BY id DESC LIMIT ?",
        (project_id, limit),
    ).fetchall()
    return [
        (r["id"], r["state"] or "proposed", r["content"] or "") for r in rows
    ]

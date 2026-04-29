"""Structured query helpers for the writer/reviewer agents.

Lesson from the agent-memory benchmark series (E6 specifically): preserving
storage isn't enough — the query surface needs to expose the structure.
Our blackboard already preserves everything in append-only form. These
helpers expose specific structural slices so the writer/reviewer agents
don't have to pattern-match across the full blackboard from scratch.

Each helper takes a sqlite3 connection + project_id and returns a list of
BlackboardEntry objects (or simple structured dicts where appropriate).
All helpers are read-only.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .blackboard import (
    KIND_CRITIQUE, KIND_EVIDENCE, KIND_EXPERIMENT, KIND_HYPOTHESIS,
    KIND_RESULT, KIND_REVIEW, BlackboardEntry, _SELECT_COLS, list_entries,
)
from .lifecycle import extract_hypothesis_refs, get_state_history

# Regex for [src #N] / [evi #N] / [exp #N] / [result #N] etc.
_REF_RE = re.compile(r"\[\s*(src|evi|hyp|exp|crit|result)\s*#(\d+)\s*\]", re.IGNORECASE)


def _entries_with_ref(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    kind: str,
    target_id: int,
    target_marker: str,
) -> list[BlackboardEntry]:
    """Return entries of `kind` whose content references `[target_marker #target_id]`.

    Uses simple substring scan over content. Cheap; correct enough for our
    blackboard volume. If the same entry references the same target multiple
    times, returned once.
    """
    rows = conn.execute(
        f"SELECT {_SELECT_COLS} FROM blackboard_entries "
        "WHERE project_id = ? AND kind = ? ORDER BY id",
        (project_id, kind),
    ).fetchall()
    # Pattern that tolerates whitespace / case variants: "[hyp #3]" matches
    # "[ hyp #3 ]", "[HYP#3]", etc.
    needle = re.compile(
        rf"\[\s*{re.escape(target_marker)}\s*#\s*{target_id}\s*\]",
        re.IGNORECASE,
    )
    out: list[BlackboardEntry] = []
    for r in rows:
        if needle.search(r["content"] or ""):
            out.append(BlackboardEntry(
                id=r["id"], project_id=r["project_id"], agent_id=r["agent_id"],
                kind=r["kind"], content=r["content"],
                refs=json.loads(r["refs_json"] or "[]"),
                turn=r["turn"],
                echo_count=int(r["echo_count"] or 0),
                echo_refs=json.loads(r["echo_refs_json"] or "[]"),
                state=r["state"],
                resolutions=json.loads(r["resolutions_json"] or "[]"),
                confidence=r["confidence"] or "EXTRACTED",
            ))
    return out


def get_critiques_for(
    conn: sqlite3.Connection, *, project_id: int, hypothesis_id: int,
) -> list[BlackboardEntry]:
    """All critique entries that reference [hyp #N] of the given hypothesis_id."""
    return _entries_with_ref(
        conn, project_id=project_id, kind=KIND_CRITIQUE,
        target_id=hypothesis_id, target_marker="hyp",
    )


def get_results_for(
    conn: sqlite3.Connection, *, project_id: int, hypothesis_id: int,
) -> list[BlackboardEntry]:
    """All result entries that reference [hyp #N]."""
    return _entries_with_ref(
        conn, project_id=project_id, kind=KIND_RESULT,
        target_id=hypothesis_id, target_marker="hyp",
    )


def get_experiments_for(
    conn: sqlite3.Connection, *, project_id: int, hypothesis_id: int,
) -> list[BlackboardEntry]:
    """All experiment entries that reference [hyp #N] (verification proposals)."""
    return _entries_with_ref(
        conn, project_id=project_id, kind=KIND_EXPERIMENT,
        target_id=hypothesis_id, target_marker="hyp",
    )


def get_supporting_evidence(
    conn: sqlite3.Connection, *, project_id: int, hypothesis_id: int,
) -> list[BlackboardEntry]:
    """Evidence entries cited as backing the hypothesis, traced via the
    hypothesis's own refs_json + any results that confirmed it.

    We collect: (a) evidence entries directly referenced in the hypothesis's
    `refs_json`, and (b) evidence entries referenced by RESULT entries that
    confirmed the hypothesis.
    """
    hyp_row = conn.execute(
        f"SELECT {_SELECT_COLS} FROM blackboard_entries "
        "WHERE id = ? AND project_id = ? AND kind = 'hypothesis'",
        (hypothesis_id, project_id),
    ).fetchone()
    if not hyp_row:
        return []

    evidence_ids: set[int] = set()
    # (a) direct refs from the hypothesis itself
    for ref in json.loads(hyp_row["refs_json"] or "[]"):
        if isinstance(ref, dict) and ref.get("kind") == "evidence":
            evidence_ids.add(int(ref["id"]))
        elif isinstance(ref, int):
            evidence_ids.add(ref)
    # Plus parse [src #N] / [evi #N] from hypothesis content
    for marker, num in _REF_RE.findall(hyp_row["content"] or ""):
        if marker.lower() in ("src", "evi"):
            evidence_ids.add(int(num))

    # (b) evidence refs from supporting RESULT entries
    supporting_results = [
        r for r in get_results_for(conn, project_id=project_id, hypothesis_id=hypothesis_id)
        if any(rsv.get("verdict") == "support"
               and rsv.get("from_entry_id") == r.id
               for rsv in get_state_history(
                   conn, project_id=project_id, hypothesis_id=hypothesis_id))
    ]
    for r in supporting_results:
        for marker, num in _REF_RE.findall(r.content or ""):
            if marker.lower() in ("src", "evi"):
                evidence_ids.add(int(num))

    if not evidence_ids:
        return []
    # Fetch the evidence entries
    placeholders = ",".join("?" * len(evidence_ids))
    rows = conn.execute(
        f"SELECT {_SELECT_COLS} FROM blackboard_entries "
        f"WHERE project_id = ? AND kind = 'evidence' AND id IN ({placeholders}) "
        "ORDER BY id",
        (project_id, *evidence_ids),
    ).fetchall()
    return [
        BlackboardEntry(
            id=r["id"], project_id=r["project_id"], agent_id=r["agent_id"],
            kind=r["kind"], content=r["content"],
            refs=json.loads(r["refs_json"] or "[]"),
            turn=r["turn"],
            echo_count=int(r["echo_count"] or 0),
            echo_refs=json.loads(r["echo_refs_json"] or "[]"),
            state=r["state"],
            resolutions=json.loads(r["resolutions_json"] or "[]"),
            confidence=r["confidence"] or "EXTRACTED",
        )
        for r in rows
    ]


def get_disagreements(
    conn: sqlite3.Connection, *, project_id: int, max_pairs: int = 20,
) -> list[dict[str, Any]]:
    """Return (hypothesis, surviving_critiques) pairs where the critic's
    refute did NOT cause the hypothesis to be refuted (i.e., something
    else later supported it OR the critique was overridden).

    These are the productive tensions the writer should highlight in the
    final report — places where agents disagreed and the disagreement
    persisted to a non-trivial outcome.
    """
    hypotheses = list_entries(conn, project_id, kind=KIND_HYPOTHESIS)
    out: list[dict[str, Any]] = []
    for hyp in hypotheses:
        critiques = get_critiques_for(
            conn, project_id=project_id, hypothesis_id=hyp.id,
        )
        # Find critiques whose verdict was 'refute' but the hypothesis is
        # not currently refuted — meaning the refute didn't stick.
        refute_critiques = [
            c for c in critiques
            if any(r.get("from_entry_id") == c.id
                   and r.get("verdict") == "refute"
                   for r in hyp.resolutions)
        ]
        if refute_critiques and hyp.state != "refuted":
            out.append({
                "hypothesis": hyp,
                "surviving_critiques": refute_critiques,
                "current_state": hyp.state,
            })
        if len(out) >= max_pairs:
            break
    return out


def get_hypothesis_arc(
    conn: sqlite3.Connection, *, project_id: int, hypothesis_id: int,
) -> dict[str, Any]:
    """Compose the full arc of a hypothesis: itself + critiques + results +
    experiments + state-transition history. Single-call view for the writer.
    """
    hyp_list = [
        h for h in list_entries(conn, project_id, kind=KIND_HYPOTHESIS)
        if h.id == hypothesis_id
    ]
    if not hyp_list:
        return {"hypothesis": None}
    return {
        "hypothesis": hyp_list[0],
        "critiques": get_critiques_for(
            conn, project_id=project_id, hypothesis_id=hypothesis_id,
        ),
        "results": get_results_for(
            conn, project_id=project_id, hypothesis_id=hypothesis_id,
        ),
        "experiments": get_experiments_for(
            conn, project_id=project_id, hypothesis_id=hypothesis_id,
        ),
        "supporting_evidence": get_supporting_evidence(
            conn, project_id=project_id, hypothesis_id=hypothesis_id,
        ),
        "state_history": get_state_history(
            conn, project_id=project_id, hypothesis_id=hypothesis_id,
        ),
    }

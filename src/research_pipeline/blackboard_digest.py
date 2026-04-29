"""Structural digest of project state — for writer/reviewer prompts.

Roadmap 2.5: writer / reviewer agents currently see a flat dump of
top-k cosine retrieval per kind. They miss the *shape* of the project —
what's confirmed, what's contested, who disagreed. This module emits a
compact markdown rollup that captures that shape so the writer can
prioritise and the reviewer can see open tensions explicitly.

The digest is **structural compression, not semantic** — it's a static
reformat of facts already in the blackboard, not an LLM summary. ~500-
800 tokens for a typical project. Cheap to compute (a few SQL queries
+ Python aggregation).

Sections:
  - hypothesis state matrix: counts by lifecycle state
  - top-N hypotheses by inbound reference count
  - latest N hypothesis state transitions (per lifecycle.get_state_history)
  - open disagreements (via query_helpers.get_disagreements)
  - top-N surviving critiques + top-N results
  - confidence ratio: EXTRACTED:INFERRED:AMBIGUOUS (per blackboard 2.4)

Use case: writer prompt becomes "DIGEST: [shape] + EVIDENCE: [retrieved
chunks]". Reviewer prompt sees the same shape so review is anchored on
project-level tensions instead of just the draft text.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from typing import Any

from .blackboard import (
    CONFIDENCES,
    KIND_CRITIQUE,
    KIND_HYPOTHESIS,
    KIND_RESULT,
    list_entries,
)
from .lifecycle import get_state_history
from .query_helpers import get_disagreements

# Order states from "in progress" to "terminal" so the matrix reads
# left-to-right in narrative order.
_STATE_ORDER = ("proposed", "under_test", "supported", "refuted")
_HYP_REF_RE = re.compile(r"\[\s*hyp\s*#\s*(\d+)\s*\]", re.IGNORECASE)


def _hypothesis_inbound_ref_counts(
    conn: sqlite3.Connection, project_id: int,
) -> Counter[int]:
    """How many other entries reference each hypothesis via [hyp #N].

    A hypothesis with many critiques + results referencing it is the
    project's centre of gravity — the writer should foreground it.
    """
    counts: Counter[int] = Counter()
    rows = conn.execute(
        "SELECT id, content, kind FROM blackboard_entries "
        "WHERE project_id = ? AND kind != 'hypothesis'",
        (project_id,),
    ).fetchall()
    for r in rows:
        for m in _HYP_REF_RE.finditer(r["content"] or ""):
            try:
                counts[int(m.group(1))] += 1
            except (TypeError, ValueError):
                continue
    return counts


def _confidence_ratio(
    conn: sqlite3.Connection, project_id: int,
) -> dict[str, int]:
    """Per-label entry count for this project. Useful as a memory-health
    signal — a corpus that's 90% INFERRED is hypothesis-heavy and may
    need more scout grounding."""
    out = {label: 0 for label in CONFIDENCES}
    rows = conn.execute(
        "SELECT confidence, COUNT(*) AS n FROM blackboard_entries "
        "WHERE project_id = ? GROUP BY confidence",
        (project_id,),
    ).fetchall()
    for r in rows:
        out[r["confidence"] or "EXTRACTED"] = out.get(
            r["confidence"] or "EXTRACTED", 0,
        ) + int(r["n"])
    return out


def _latest_transitions(
    conn: sqlite3.Connection, project_id: int, n: int = 3,
) -> list[dict[str, Any]]:
    """Most recent hypothesis state transitions across all hypotheses,
    sorted by turn descending."""
    hyps = list_entries(conn, project_id, kind=KIND_HYPOTHESIS)
    flat: list[dict[str, Any]] = []
    for h in hyps:
        for t in get_state_history(
            conn, project_id=project_id, hypothesis_id=h.id,
        ):
            flat.append({
                "hypothesis_id": h.id,
                "hypothesis_content": h.content,
                **t,
            })
    flat.sort(key=lambda x: int(x.get("turn", 0)), reverse=True)
    return flat[:n]


def render_digest(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    top_n: int = 5,
    transitions_n: int = 3,
) -> str:
    """Return a compact markdown digest of project state.

    Self-contained: callers can prepend this to writer/reviewer prompts
    or write it to disk for debugging.
    """
    hyps = list_entries(conn, project_id, kind=KIND_HYPOTHESIS)
    crits = list_entries(conn, project_id, kind=KIND_CRITIQUE)
    results = list_entries(conn, project_id, kind=KIND_RESULT)

    if not (hyps or crits or results):
        return "## Project digest\n\n_(blackboard empty — no shape to summarise)_\n"

    lines: list[str] = ["## Project digest"]

    # State matrix
    lines.append("\n### Hypothesis state matrix")
    state_counts: dict[str, int] = {s: 0 for s in _STATE_ORDER}
    for h in hyps:
        state_counts[h.state] = state_counts.get(h.state, 0) + 1
    cells = " | ".join(f"{s}={state_counts.get(s, 0)}" for s in _STATE_ORDER)
    lines.append(f"- {cells}  (total: {len(hyps)})")

    # Top hypotheses by inbound reference count
    if hyps:
        ref_counts = _hypothesis_inbound_ref_counts(conn, project_id)
        ranked = sorted(
            hyps, key=lambda h: (ref_counts.get(h.id, 0), h.id), reverse=True,
        )[:top_n]
        lines.append(f"\n### Top {min(top_n, len(ranked))} hypotheses by inbound refs")
        for h in ranked:
            n_refs = ref_counts.get(h.id, 0)
            preview = (h.content or "").strip().splitlines()[0][:120]
            lines.append(
                f"- **#{h.id}** [{h.state}, {n_refs} refs, {h.confidence}]: {preview}"
            )

    # Latest hypothesis transitions
    transitions = _latest_transitions(conn, project_id, n=transitions_n)
    if transitions:
        lines.append(f"\n### Latest {len(transitions)} hypothesis state transitions")
        for t in transitions:
            prev = t.get("prev_state", "?")
            new = t.get("new_state", "?")
            verdict = t.get("verdict", "—")
            lines.append(
                f"- turn {t.get('turn', '?')}: hyp #{t['hypothesis_id']} "
                f"{prev} → {new}  (verdict: {verdict})"
            )

    # Open disagreements
    diss = get_disagreements(conn, project_id=project_id, max_pairs=top_n)
    if diss:
        lines.append(f"\n### Open disagreements ({len(diss)})")
        for d in diss:
            h = d["hypothesis"]
            n_critiques = len(d["surviving_critiques"])
            preview = (h.content or "").strip().splitlines()[0][:100]
            lines.append(
                f"- **#{h.id}** [now {d['current_state']}, "
                f"{n_critiques} surviving critique(s)]: {preview}"
            )
    else:
        lines.append("\n### Open disagreements\n- _(none — no surviving refute critiques)_")

    # Top results
    if results:
        ranked_r = sorted(results, key=lambda r: r.id, reverse=True)[:top_n]
        lines.append(f"\n### Recent {len(ranked_r)} results")
        for r in ranked_r:
            preview = (r.content or "").strip().splitlines()[0][:120]
            lines.append(
                f"- **#{r.id}** [{r.state}, {r.confidence}]: {preview}"
            )

    # Top surviving critiques (those whose hypothesis is NOT refuted)
    if crits:
        non_refute_ids = {h.id for h in hyps if h.state != "refuted"}
        survivors = [
            c for c in crits
            if any(int(m.group(1)) in non_refute_ids
                   for m in _HYP_REF_RE.finditer(c.content or ""))
        ]
        if survivors:
            ranked_c = sorted(survivors, key=lambda c: c.id, reverse=True)[:top_n]
            lines.append(f"\n### Recent {len(ranked_c)} surviving critiques")
            for c in ranked_c:
                preview = (c.content or "").strip().splitlines()[0][:120]
                lines.append(
                    f"- **#{c.id}** [{c.confidence}]: {preview}"
                )

    # Confidence ratio
    ratio = _confidence_ratio(conn, project_id)
    total = sum(ratio.values()) or 1
    parts = " : ".join(
        f"{label}={ratio[label]} ({100*ratio[label]/total:.0f}%)"
        for label in CONFIDENCES
    )
    lines.append(f"\n### Confidence mix\n- {parts}  (n={total})")

    return "\n".join(lines) + "\n"

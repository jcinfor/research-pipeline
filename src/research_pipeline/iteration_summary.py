"""Per-iteration summary emitter for the optimize loop.

After each `project optimize` iteration, write a small markdown digest to
    projects/project_{id}/iterations/iter_{NN}.md

This makes long optimize runs navigable without polluting the blackboard
(which stays append-only and untouched). Each summary captures:

    - iteration index + decision context (weakest agent, action taken)
    - what's NEW on the blackboard since the previous iteration
    - hypothesis state transitions in this iteration (using lifecycle's
      new prev_state -> new_state audit log)
    - KPI before/after
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .blackboard import KIND_HYPOTHESIS, list_entries
from .lifecycle import get_state_history


def _entries_in_turn_range(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    turn_start: int,
    turn_end: int,
) -> dict[str, list[Any]]:
    """Return blackboard entries from turns in [turn_start, turn_end] grouped by kind."""
    all_entries = list_entries(conn, project_id)
    in_range = [
        e for e in all_entries
        if turn_start <= e.turn <= turn_end
    ]
    by_kind: dict[str, list[Any]] = {}
    for e in in_range:
        by_kind.setdefault(e.kind, []).append(e)
    return by_kind


def _hypothesis_transitions_in_turn_range(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    turn_start: int,
    turn_end: int,
) -> list[dict[str, Any]]:
    """Find hypothesis state transitions whose `turn` is in [turn_start, turn_end]."""
    hyps = list_entries(conn, project_id, kind=KIND_HYPOTHESIS)
    transitions: list[dict[str, Any]] = []
    for h in hyps:
        history = get_state_history(
            conn, project_id=project_id, hypothesis_id=h.id,
        )
        for t in history:
            if turn_start <= int(t.get("turn", -1)) <= turn_end:
                transitions.append({
                    "hypothesis_id": h.id,
                    "hypothesis_content": h.content,
                    **t,
                })
    transitions.sort(key=lambda x: (x.get("turn", 0), x.get("from_entry_id", 0)))
    return transitions


def write_iteration_summary(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    iteration_index: int,
    turn_start: int,
    turn_end: int,
    weakest_agent_id: int | None,
    weakest_metric: str | None,
    decision_action: str | None,
    decision_rationale: str | None,
    kpi_before: dict[str, float],
    kpi_after: dict[str, float],
    project_dir: Path,
) -> Path:
    """Write a markdown summary for one optimize iteration. Returns the file path."""
    out_dir = project_dir / f"project_{project_id}" / "iterations"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"iter_{iteration_index:02d}.md"

    by_kind = _entries_in_turn_range(
        conn, project_id=project_id,
        turn_start=turn_start, turn_end=turn_end,
    )
    transitions = _hypothesis_transitions_in_turn_range(
        conn, project_id=project_id,
        turn_start=turn_start, turn_end=turn_end,
    )

    now = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = [
        f"# Iteration {iteration_index} — project {project_id}\n",
        f"*Generated {now}* · turns {turn_start}–{turn_end}\n",
    ]

    # Decision context
    lines.append("## Decision\n")
    if weakest_agent_id is None:
        lines.append("- weakest agent: _none identified_\n")
    else:
        lines.append(f"- weakest agent: `{weakest_agent_id}`")
        lines.append(f"- weakest dimension: `{weakest_metric}`")
        if decision_action:
            lines.append(f"- action: `{decision_action}`")
        if decision_rationale:
            lines.append(f"- rationale: {decision_rationale}")
        lines.append("")

    # KPI before/after
    if kpi_before or kpi_after:
        lines.append("## KPI\n")
        all_metrics = sorted(set(kpi_before) | set(kpi_after))
        lines.append("| metric | before | after | delta |")
        lines.append("|---|---|---|---|")
        for m in all_metrics:
            b = kpi_before.get(m, 0.0)
            a = kpi_after.get(m, 0.0)
            d = a - b
            sign = "+" if d > 0 else ""
            lines.append(f"| {m} | {b:.3f} | {a:.3f} | {sign}{d:.3f} |")
        lines.append("")

    # Hypothesis state transitions
    if transitions:
        lines.append("## Hypothesis transitions\n")
        for t in transitions:
            hid = t.get("hypothesis_id")
            prev = t.get("prev_state", "?")
            new = t.get("new_state", "?")
            verdict = t.get("verdict", "?")
            turn_n = t.get("turn", "?")
            entry_id = t.get("from_entry_id", "?")
            preview = (t.get("hypothesis_content") or "")[:80]
            lines.append(
                f"- `[hyp #{hid}]` `{prev}` → **`{new}`** "
                f"(turn {turn_n}, verdict={verdict}, via entry #{entry_id})  "
                f"\n  _{preview}…_"
            )
        lines.append("")
    else:
        lines.append("## Hypothesis transitions\n\n_(none)_\n")

    # New blackboard entries summary
    if by_kind:
        lines.append("## New blackboard entries\n")
        lines.append("| kind | count |")
        lines.append("|---|---|")
        for kind in sorted(by_kind):
            lines.append(f"| {kind} | {len(by_kind[kind])} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_optimization_index(
    *,
    project_id: int,
    iteration_paths: list[Path],
    project_dir: Path,
) -> Path:
    """After all iterations, write an index listing all iter_NN.md files."""
    out_dir = project_dir / f"project_{project_id}" / "iterations"
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.md"

    now = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = [
        f"# Optimization iterations — project {project_id}\n",
        f"*Generated {now}* · {len(iteration_paths)} iterations\n",
        "## Iterations\n",
    ]
    for p in iteration_paths:
        lines.append(f"- [{p.name}]({p.name})")
    lines.append("")
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path

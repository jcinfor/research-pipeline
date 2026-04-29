"""Blackboard: append-only shared evidence store for a project.

Entries carry a `kind` drawn from a small enum of research artifacts.
The blackboard is the *durable* research memory — channel posts are ephemeral
social signals, blackboard entries are what the final report is built from.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

KIND_EVIDENCE = "evidence"
KIND_HYPOTHESIS = "hypothesis"
KIND_EXPERIMENT = "experiment"
KIND_RESULT = "result"
KIND_CRITIQUE = "critique"
KIND_DRAFT = "draft"
KIND_REVIEW = "review"

KINDS = (
    KIND_EVIDENCE,
    KIND_HYPOTHESIS,
    KIND_EXPERIMENT,
    KIND_RESULT,
    KIND_CRITIQUE,
    KIND_DRAFT,
    KIND_REVIEW,
)

# Roadmap 2.4 — confidence labels.
# EXTRACTED: pulled directly from a source (scout reads paper, replicator
#            cites a measured result, ingest reads a doc).
# INFERRED:  synthesised by an agent — hypothesis, critique argument,
#            writer/reviewer claim derived from other entries.
# AMBIGUOUS: low-confidence; e.g. a critique whose surviving doubt is
#            itself uncertain. Distinct from missing-info.
CONF_EXTRACTED = "EXTRACTED"
CONF_INFERRED = "INFERRED"
CONF_AMBIGUOUS = "AMBIGUOUS"

CONFIDENCES = (CONF_EXTRACTED, CONF_INFERRED, CONF_AMBIGUOUS)
# Order from strongest to weakest, used when a downstream entry
# inherits the lowest label from cited entries.
_CONF_RANK = {CONF_EXTRACTED: 0, CONF_INFERRED: 1, CONF_AMBIGUOUS: 2}


def lowest_confidence(labels: list[str]) -> str:
    """Return the weakest label among `labels`, or EXTRACTED if empty.

    Use case: when a writer/reviewer cites several entries, the synthesis
    inherits the lowest confidence among its sources — chain-of-reasoning
    is only as strong as its weakest link.
    """
    if not labels:
        return CONF_EXTRACTED
    return max(labels, key=lambda c: _CONF_RANK.get(c, 0))


@dataclass(frozen=True)
class BlackboardEntry:
    id: int
    project_id: int
    agent_id: int | None
    kind: str
    content: str
    refs: list[Any]
    turn: int
    echo_count: int = 0
    echo_refs: list[Any] = ()  # type: ignore[assignment]
    state: str = "proposed"
    resolutions: list[Any] = ()  # type: ignore[assignment]
    confidence: str = CONF_EXTRACTED


def add_entry(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    kind: str,
    content: str,
    turn: int,
    agent_id: int | None = None,
    refs: list[Any] | None = None,
    confidence: str = CONF_EXTRACTED,
) -> int:
    if kind not in KINDS:
        raise ValueError(f"Unknown blackboard kind: {kind!r}. Known: {KINDS}")
    if confidence not in CONFIDENCES:
        raise ValueError(
            f"Unknown confidence: {confidence!r}. Known: {CONFIDENCES}"
        )
    cur = conn.execute(
        "INSERT INTO blackboard_entries "
        "(project_id, agent_id, kind, content, refs_json, turn, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            agent_id,
            kind,
            content,
            json.dumps(refs or []),
            turn,
            confidence,
        ),
    )
    conn.commit()
    eid = cur.lastrowid
    assert eid is not None
    return eid


_SELECT_COLS = (
    "id, project_id, agent_id, kind, content, refs_json, turn, "
    "COALESCE(echo_count, 0) AS echo_count, "
    "COALESCE(echo_refs_json, '[]') AS echo_refs_json, "
    "COALESCE(state, 'proposed') AS state, "
    "COALESCE(resolutions_json, '[]') AS resolutions_json, "
    "COALESCE(confidence, 'EXTRACTED') AS confidence"
)


def list_entries(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    kind: str | None = None,
) -> list[BlackboardEntry]:
    if kind is None:
        rows = conn.execute(
            f"SELECT {_SELECT_COLS} FROM blackboard_entries "
            "WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {_SELECT_COLS} FROM blackboard_entries "
            "WHERE project_id = ? AND kind = ? ORDER BY id",
            (project_id, kind),
        ).fetchall()
    return [
        BlackboardEntry(
            id=r["id"],
            project_id=r["project_id"],
            agent_id=r["agent_id"],
            kind=r["kind"],
            content=r["content"],
            refs=json.loads(r["refs_json"] or "[]"),
            turn=r["turn"],
            echo_count=int(r["echo_count"] or 0),
            echo_refs=json.loads(r["echo_refs_json"] or "[]"),
            state=r["state"],
            resolutions=json.loads(r["resolutions_json"] or "[]"),
            confidence=r["confidence"] or CONF_EXTRACTED,
        )
        for r in rows
    ]


def render_markdown(conn: sqlite3.Connection, project_id: int) -> str:
    entries = list_entries(conn, project_id)
    if not entries:
        return f"# Project {project_id} blackboard\n\n_(empty)_\n"
    by_kind: dict[str, list[BlackboardEntry]] = {}
    for e in entries:
        by_kind.setdefault(e.kind, []).append(e)
    out = [f"# Project {project_id} blackboard\n"]
    for kind in KINDS:
        items = by_kind.get(kind, [])
        if not items:
            continue
        out.append(f"\n## {kind} ({len(items)})\n")
        for e in items:
            agent = f"agent {e.agent_id}" if e.agent_id is not None else "system"
            refs = ", ".join(str(r) for r in e.refs) or "—"
            out.append(f"- **[turn {e.turn}, {agent}]** {e.content}")
            out.append(f"  *refs:* {refs}")
    return "\n".join(out) + "\n"

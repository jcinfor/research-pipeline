"""Embedding-based deduplication of blackboard entries.

When a new entry is near-duplicate of an existing one (same kind, cosine
similarity above threshold), we skip the insert and record an "echo" on the
canonical entry instead. Echoes preserve the convergence signal (who arrived
at the same point, and when) without polluting the blackboard.
"""
from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from .adapter import LLMClient
from .blackboard import CONF_EXTRACTED, CONFIDENCES, KINDS, add_entry


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def find_near_duplicate(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    kind: str,
    new_embedding: list[float],
    threshold: float,
) -> tuple[int, float] | None:
    best_id: int | None = None
    best_sim = -1.0
    for r in conn.execute(
        "SELECT id, embedding_json FROM blackboard_entries "
        "WHERE project_id = ? AND kind = ? AND embedding_json IS NOT NULL",
        (project_id, kind),
    ):
        try:
            emb = json.loads(r["embedding_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        sim = cosine(new_embedding, emb)
        if sim > best_sim:
            best_sim = sim
            best_id = r["id"]
    if best_id is not None and best_sim >= threshold:
        return (best_id, best_sim)
    return None


def add_entry_with_dedup(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    kind: str,
    content: str,
    turn: int,
    agent_id: int | None = None,
    refs: list[Any] | None = None,
    llm: LLMClient | None = None,
    threshold: float = 0.85,
    confidence: str = CONF_EXTRACTED,
) -> tuple[int, bool, float]:
    """Add an entry with optional embedding-based dedup.

    Returns (entry_id, was_deduped, similarity). When llm is None, dedup is
    skipped and this degrades to a plain add_entry.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown blackboard kind: {kind!r}")
    if confidence not in CONFIDENCES:
        raise ValueError(f"Unknown confidence: {confidence!r}")
    refs = refs or []

    if llm is None:
        eid = add_entry(
            conn,
            project_id=project_id,
            kind=kind,
            content=content,
            turn=turn,
            agent_id=agent_id,
            refs=refs,
            confidence=confidence,
        )
        return (eid, False, 0.0)

    new_vec = llm.embed("embedding", content)[0]
    match = find_near_duplicate(
        conn,
        project_id=project_id,
        kind=kind,
        new_embedding=new_vec,
        threshold=threshold,
    )
    if match is not None:
        canonical_id, sim = match
        row = conn.execute(
            "SELECT echo_refs_json FROM blackboard_entries WHERE id = ?",
            (canonical_id,),
        ).fetchone()
        echoes = json.loads(row["echo_refs_json"] or "[]")
        echoes.append(
            {
                "agent_id": agent_id,
                "turn": turn,
                "content": content[:240],
                "similarity": round(sim, 3),
            }
        )
        conn.execute(
            "UPDATE blackboard_entries SET echo_count = echo_count + 1, "
            "echo_refs_json = ? WHERE id = ?",
            (json.dumps(echoes), canonical_id),
        )
        conn.commit()
        return (canonical_id, True, sim)

    cur = conn.execute(
        "INSERT INTO blackboard_entries "
        "(project_id, agent_id, kind, content, refs_json, turn, embedding_json, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            agent_id,
            kind,
            content,
            json.dumps(refs),
            turn,
            json.dumps(new_vec),
            confidence,
        ),
    )
    conn.commit()
    eid = cur.lastrowid
    assert eid is not None
    return (eid, False, 0.0)

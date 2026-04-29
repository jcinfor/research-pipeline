"""Embedding-based retrieval over the blackboard.

Given a query, embed it and rank blackboard entries by cosine similarity to
return the top-k most relevant. Used by the Writer/Reviewer to ground the
synthesis report in the highest-signal material rather than a raw dump.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .adapter import LLMClient
from .blackboard import BlackboardEntry, list_entries
from .dedup import cosine


@dataclass(frozen=True)
class ScoredEntry:
    entry: BlackboardEntry
    score: float


def search_blackboard(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    query: str,
    llm: LLMClient,
    top_k: int = 8,
    kind: str | None = None,
    visibility: str = "visible",
) -> list[ScoredEntry]:
    """Embed `query` and return the top-k entries ordered by descending
    cosine similarity.

    Visibility defaults to 'visible' so agents never see held-out evidence
    (that partition is reserved for PGR scoring). Pass `visibility="all"` to
    include everything; `"held_out"` for just the held-out set.
    """
    query_vec = llm.embed("embedding", query)[0]
    params: list = [project_id]
    sql = (
        "SELECT id, embedding_json FROM blackboard_entries "
        "WHERE project_id = ? AND embedding_json IS NOT NULL"
    )
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    if visibility != "all":
        sql += " AND COALESCE(visibility, 'visible') = ?"
        params.append(visibility)
    scored: list[tuple[int, float]] = []
    for r in conn.execute(sql, params):
        try:
            emb = json.loads(r["embedding_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        scored.append((r["id"], cosine(query_vec, emb)))
    scored.sort(key=lambda x: -x[1])
    top = scored[:top_k]
    id_score = dict(top)
    entries = list_entries(conn, project_id, kind=kind)
    by_id = {e.id: e for e in entries}
    return [
        ScoredEntry(entry=by_id[i], score=id_score[i])
        for i, _ in top
        if i in by_id
    ]

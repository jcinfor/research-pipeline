"""Per-user Karpathy-style wiki: a compounding library of promoted blackboard
entries that persists across projects.

Flow:
    rp wiki promote <project_id>   project blackboard -> user wiki (top-K per kind)
    rp wiki seed <project_id>      user wiki -> target project blackboard (seed)
    rp wiki search <query>         cosine search across the wiki
    rp wiki show                   markdown render of the wiki, grouped by kind
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter import LLMClient
from .blackboard import KINDS, list_entries
from .dedup import cosine
from .projects import get_project


@dataclass(frozen=True)
class WikiEntry:
    id: int
    user_id: int
    kind: str
    content: str
    refs: list[Any]
    source_project_id: int | None
    promoted_score: float
    t_ref: str | None = None  # temporal anchor: when the claim is TRUE (ISO date)


def _row_to_entry(r: sqlite3.Row) -> WikiEntry:
    # t_ref is optional (migrated column; older rows have NULL)
    t_ref = None
    try:
        t_ref = r["t_ref"]
    except (IndexError, KeyError):
        pass
    return WikiEntry(
        id=r["id"],
        user_id=r["user_id"],
        kind=r["kind"],
        content=r["content"],
        refs=json.loads(r["refs_json"] or "[]"),
        source_project_id=r["source_project_id"],
        promoted_score=float(r["promoted_score"] or 0.0),
        t_ref=t_ref,
    )


_YEAR_IN_REF_RE = None  # module-level regex compiled lazily


def _extract_t_ref(refs: list[Any]) -> str | None:
    """Derive a temporal anchor from an entry's refs.

    Strategy (cheap, deterministic):
      - Look for 4-digit years in the 1900-2099 range anywhere in refs
      - Return the MAX year found (latest is usually most relevant)
      - Return as ISO date "YYYY-01-01" for sortable comparison
      - Return None if nothing found — the entry is atemporal

    This is the hybrid bridge: we steal Zep's idea of an explicit temporal
    reference per entry, but derive it from plain-text refs (no graph DB,
    no custom extraction pipeline). Enough to power "as-of" queries.
    """
    import re
    global _YEAR_IN_REF_RE
    if _YEAR_IN_REF_RE is None:
        _YEAR_IN_REF_RE = re.compile(r"\b(19|20)\d{2}\b")
    years: list[int] = []
    for ref in refs or []:
        s = str(ref)
        for m in _YEAR_IN_REF_RE.finditer(s):
            try:
                years.append(int(m.group(0)))
            except ValueError:
                continue
    if not years:
        return None
    return f"{max(years)}-01-01"


def _score_entry(entry, kpi_snapshot: dict[str, float]) -> float:
    """Rank candidates for promotion.

    Heuristic: weight by rubric relevance + rigor + citation_quality, bump when
    the entry has refs (grounded), and give echoes a modest credit (signal of
    convergence from multiple agents)."""
    base = (
        kpi_snapshot.get("relevance_to_goal", 0.0)
        + kpi_snapshot.get("rigor", 0.0)
        + kpi_snapshot.get("citation_quality", 0.0)
    )
    refs_bonus = 1.0 if entry.refs else 0.0
    echo_bonus = 0.3 * getattr(entry, "echo_count", 0)
    content_len_factor = min(1.0, len(entry.content) / 400.0)
    return base + refs_bonus + echo_bonus + content_len_factor


def promote_project_to_wiki(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    top_k_per_kind: int = 3,
    kinds: tuple[str, ...] = KINDS,
) -> dict[str, int]:
    """Copy the top-K entries per kind from a project's blackboard into the
    user's wiki. Already-promoted entries (exact content match for the same
    user) are skipped.

    Returns a {kind: count} dict of entries newly promoted.
    """
    project = get_project(conn, project_id)
    user_id = project.user_id

    # Latest project-level rubric for scoring
    kpi_rows = conn.execute(
        """
        SELECT metric, value FROM kpi_scores
        WHERE project_id = ? AND agent_id IS NULL
        AND turn = (
            SELECT MAX(turn) FROM kpi_scores
            WHERE project_id = ? AND agent_id IS NULL AND metric = kpi_scores.metric
        )
        """,
        (project_id, project_id),
    ).fetchall()
    kpi_snapshot = {r["metric"]: float(r["value"]) for r in kpi_rows}

    promoted: dict[str, int] = {}
    for kind in kinds:
        entries = list_entries(conn, project_id, kind=kind)
        if not entries:
            continue
        ranked = sorted(entries, key=lambda e: _score_entry(e, kpi_snapshot), reverse=True)
        for e in ranked[:top_k_per_kind]:
            exists = conn.execute(
                "SELECT 1 FROM user_wiki_entries "
                "WHERE user_id = ? AND content = ? LIMIT 1",
                (user_id, e.content),
            ).fetchone()
            if exists:
                continue
            # Preserve embedding if the blackboard had one
            emb_row = conn.execute(
                "SELECT embedding_json FROM blackboard_entries WHERE id = ?",
                (e.id,),
            ).fetchone()
            embedding_json = emb_row["embedding_json"] if emb_row else None
            t_ref = _extract_t_ref(e.refs or [])
            conn.execute(
                "INSERT INTO user_wiki_entries "
                "(user_id, kind, content, refs_json, embedding_json, "
                " source_project_id, promoted_score, t_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    e.kind,
                    e.content,
                    json.dumps(e.refs or []),
                    embedding_json,
                    project_id,
                    _score_entry(e, kpi_snapshot),
                    t_ref,
                ),
            )
            promoted[kind] = promoted.get(kind, 0) + 1
    conn.commit()
    return promoted


def list_wiki(
    conn: sqlite3.Connection, *, user_id: int, kind: str | None = None
) -> list[WikiEntry]:
    if kind is None:
        rows = conn.execute(
            "SELECT * FROM user_wiki_entries WHERE user_id = ? "
            "ORDER BY promoted_score DESC, id DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM user_wiki_entries WHERE user_id = ? AND kind = ? "
            "ORDER BY promoted_score DESC, id DESC",
            (user_id, kind),
        ).fetchall()
    return [_row_to_entry(r) for r in rows]


def search_wiki(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    query: str,
    llm: LLMClient,
    top_k: int = 8,
    kind: str | None = None,
    as_of: str | None = None,
) -> list[tuple[WikiEntry, float]]:
    """Cosine-rank wiki entries by similarity to `query`. Entries without
    embeddings are excluded from the ranking.

    `as_of` (ISO date 'YYYY-MM-DD'): when set, only return entries whose
    temporal anchor is at or before this date, OR entries without a t_ref
    (treated as atemporal). This is the Zep-style temporal filter applied
    to Karpathy-style markdown storage — lets you query "what did the
    wiki know as of X".
    """
    qvec = llm.embed("embedding", query)[0]
    base_sql = (
        "SELECT * FROM user_wiki_entries "
        "WHERE user_id = ? AND embedding_json IS NOT NULL"
    )
    params: list = [user_id]
    if kind is not None:
        base_sql += " AND kind = ?"
        params.append(kind)
    if as_of is not None:
        base_sql += " AND (t_ref IS NULL OR t_ref <= ?)"
        params.append(as_of)
    scored: list[tuple[WikiEntry, float]] = []
    for r in conn.execute(base_sql, params):
        try:
            emb = json.loads(r["embedding_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        scored.append((_row_to_entry(r), cosine(qvec, emb)))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


def seed_project_from_wiki(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient,
    top_k: int = 6,
) -> int:
    """Pull top-k wiki entries most relevant to the project goal and file them
    as `kind=evidence` with refs tagged `source=user_wiki#<id>`. Returns count
    inserted. Idempotent: skips wiki entries already seeded into this project.
    """
    from .dedup import add_entry_with_dedup  # local import to avoid cycle

    project = get_project(conn, project_id)
    hits = search_wiki(
        conn,
        user_id=project.user_id,
        query=project.goal,
        llm=llm,
        top_k=top_k,
    )
    inserted = 0
    for entry, score in hits:
        source_tag = f"source=user_wiki#{entry.id}"
        # Idempotency guard
        already = conn.execute(
            "SELECT 1 FROM blackboard_entries "
            "WHERE project_id = ? AND content = ? LIMIT 1",
            (project_id, entry.content),
        ).fetchone()
        if already:
            continue
        refs = [source_tag] + list(entry.refs)
        add_entry_with_dedup(
            conn,
            project_id=project_id,
            kind=entry.kind,
            content=entry.content,
            turn=0,
            agent_id=None,
            refs=refs,
            llm=llm,
            threshold=0.98,  # strict — wiki content is already vetted
        )
        inserted += 1
    return inserted


def render_wiki_markdown(conn: sqlite3.Connection, *, user_id: int) -> str:
    entries = list_wiki(conn, user_id=user_id)
    if not entries:
        return f"# User {user_id} wiki\n\n_(empty — run `rp wiki promote <project_id>`)_\n"
    by_kind: dict[str, list[WikiEntry]] = {}
    for e in entries:
        by_kind.setdefault(e.kind, []).append(e)
    out = [f"# User {user_id} wiki\n"]
    for kind in KINDS:
        items = by_kind.get(kind, [])
        if not items:
            continue
        out.append(f"\n## {kind} ({len(items)})\n")
        for e in items:
            src = f" *(project {e.source_project_id})*" if e.source_project_id else ""
            t_ref = f" `t_ref={e.t_ref}`" if e.t_ref else ""
            refs = ", ".join(str(r) for r in e.refs) or "—"
            out.append(f"- **#{e.id}** score={e.promoted_score:.2f}{t_ref}{src}")
            out.append(f"  {e.content}")
            out.append(f"  *refs:* {refs}")
    return "\n".join(out) + "\n"

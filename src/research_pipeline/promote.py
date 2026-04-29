"""Rules that promote channel posts into durable blackboard entries.

Phase 1 rule: archetype → kind (scout→evidence, hypogen→hypothesis, etc.),
with lightweight regex-based citation extraction into `refs`.
"""
from __future__ import annotations

import re
import sqlite3

from .adapter import LLMClient
from .archetypes import by_id
from .blackboard import (
    CONF_AMBIGUOUS,
    CONF_EXTRACTED,
    CONF_INFERRED,
    KIND_CRITIQUE,
    KIND_DRAFT,
    KIND_EVIDENCE,
    KIND_EXPERIMENT,
    KIND_HYPOTHESIS,
    KIND_RESULT,
    KIND_REVIEW,
)
from .dedup import add_entry_with_dedup

ARCHETYPE_TO_KIND = {
    "scout": KIND_EVIDENCE,
    "hypogen": KIND_HYPOTHESIS,
    "experimenter": KIND_EXPERIMENT,
    "critic": KIND_CRITIQUE,
    "replicator": KIND_RESULT,
    "statistician": KIND_CRITIQUE,
    "writer": KIND_DRAFT,
    "reviewer": KIND_REVIEW,
}

# Roadmap 2.4 — per-archetype default confidence label.
#
# scout pulls from sources → EXTRACTED.
# hypogen / experimenter / critic / statistician / writer / reviewer
# synthesise → INFERRED.
# replicator's defaults are computed dynamically from refs (see
# `_replicator_confidence`): EXTRACTED when the result cites a real
# source (DOI/arxiv), INFERRED when it doesn't.
ARCHETYPE_TO_CONFIDENCE = {
    "scout": CONF_EXTRACTED,
    "hypogen": CONF_INFERRED,
    "experimenter": CONF_INFERRED,
    "critic": CONF_INFERRED,
    "statistician": CONF_INFERRED,
    "replicator": CONF_EXTRACTED,  # overridden when refs is empty
    "writer": CONF_INFERRED,
    "reviewer": CONF_INFERRED,
}

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[\w./-]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"\barxiv:\s*\d{4}\.\d{4,5}", re.IGNORECASE)
_AUTHOR_ET_AL_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+et\s+al\.?", re.MULTILINE)


def _has_strong_citation(refs: list[str]) -> bool:
    """A 'strong' citation is a DOI, arxiv id, or author-et-al — anything
    other than a bare year. Replicator results without a strong citation
    fall back to INFERRED rather than the EXTRACTED default."""
    for r in refs:
        if _DOI_RE.search(r) or _ARXIV_RE.search(r) or _AUTHOR_ET_AL_RE.search(r):
            return True
    return False


def confidence_for(archetype: str, refs: list[str]) -> str:
    """Default confidence label for a post written by `archetype`.

    Replicator (KIND_RESULT) is the only archetype whose default depends
    on whether the post cites a real source — a result without a citation
    is an inference about expected behavior, not a measurement.
    """
    if archetype == "replicator":
        return CONF_EXTRACTED if _has_strong_citation(refs) else CONF_INFERRED
    return ARCHETYPE_TO_CONFIDENCE.get(archetype, CONF_INFERRED)


def extract_refs(content: str) -> list[str]:
    refs: list[str] = []
    refs.extend(m.group(0) for m in _DOI_RE.finditer(content))
    refs.extend(m.group(0) for m in _ARXIV_RE.finditer(content))
    refs.extend(f"{m.group(1)} et al." for m in _AUTHOR_ET_AL_RE.finditer(content))
    refs.extend(m.group(0) for m in _YEAR_RE.finditer(content))
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        key = r.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def promote_project_posts(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    turn: int,
    llm: LLMClient | None = None,
    dedup_threshold: float = 0.85,
) -> dict:
    """Promote every channel_post at `turn` into a blackboard entry by archetype.

    If `llm` is supplied, near-duplicate entries (same kind, cosine similarity
    above threshold) collapse into an existing canonical entry as an "echo"
    rather than a new row. Without `llm`, dedup is skipped.

    Returns {"added": N, "echoed": M, "skipped": K}.
    """
    agent_arch: dict[int, str] = {}
    for r in conn.execute(
        "SELECT id, archetype FROM agents WHERE project_id = ?", (project_id,)
    ):
        agent_arch[r["id"]] = r["archetype"]

    added = 0
    echoed = 0
    skipped = 0
    for post in conn.execute(
        "SELECT id, agent_id, content FROM channel_posts "
        "WHERE project_id = ? AND turn = ? AND agent_id IS NOT NULL",
        (project_id, turn),
    ).fetchall():
        archetype_id = agent_arch.get(post["agent_id"])
        if not archetype_id:
            continue
        kind = ARCHETYPE_TO_KIND.get(archetype_id)
        if not kind:
            continue
        # Idempotency: exact content already promoted at this (project, agent, turn)
        existing = conn.execute(
            "SELECT 1 FROM blackboard_entries "
            "WHERE project_id = ? AND agent_id = ? AND turn = ? AND content = ? "
            "LIMIT 1",
            (project_id, post["agent_id"], turn, post["content"]),
        ).fetchone()
        if existing:
            skipped += 1
            continue
        refs = extract_refs(post["content"] or "")
        confidence = confidence_for(archetype_id, refs)
        _, was_dedup, _ = add_entry_with_dedup(
            conn,
            project_id=project_id,
            agent_id=post["agent_id"],
            kind=kind,
            content=post["content"] or "",
            turn=turn,
            refs=refs,
            llm=llm,
            threshold=dedup_threshold,
            confidence=confidence,
        )
        by_id(archetype_id)  # validate
        if was_dedup:
            echoed += 1
        else:
            added += 1
    return {"added": added, "echoed": echoed, "skipped": skipped}

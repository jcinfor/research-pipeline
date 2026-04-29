"""KPI evaluator.

Two layers:
    counters  — mechanical, SQL-only, cheap, per-turn
    rubric    — LLM-judged (role=judge), expensive, call sparingly

Phase 1 records counters every turn and rubric once at end-of-run.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Iterable

from .adapter import LLMClient
from .blackboard import (
    KIND_CRITIQUE,
    KIND_DRAFT,
    KIND_EVIDENCE,
    KIND_EXPERIMENT,
    KIND_HYPOTHESIS,
    KIND_RESULT,
)
from .dedup import cosine

# Per-agent counter metrics
M_POSTS_PUBLISHED = "posts_published"
M_EVIDENCE_FILED = "evidence_filed"
M_HYPOTHESES_GENERATED = "hypotheses_generated"
M_EXPERIMENTS_DESIGNED = "experiments_designed"
M_RESULTS_RECORDED = "results_recorded"
M_CRITIQUES_ISSUED = "critiques_issued"
M_DRAFT_SECTIONS = "draft_sections"

# Project-level counter metrics
M_EVIDENCE_DENSITY = "evidence_density"          # evidence / hypotheses (guardrail)
M_COVERAGE = "coverage"                           # distinct archetype contributions
M_IDEA_DIVERSITY = "idea_diversity"               # mean pairwise cosine distance on blackboard (0-1)
M_ECHO_RATE = "echo_rate"                          # echoes / (added + echoes)

PROJECT_COUNTERS = (M_COVERAGE, M_EVIDENCE_DENSITY, M_IDEA_DIVERSITY, M_ECHO_RATE)

# Phase 3 — PGR proxies (written by pgr.score_project, read for trajectory)
M_PGR_CITE = "pgr_cite"
M_PGR_SUPPORT = "pgr_support"      # partial-credit companion to pgr_cite
M_PGR_HELDOUT = "pgr_heldout"
M_PGR_ADV = "pgr_adv"
M_PGR_COMPOSITE = "pgr_composite"
PGR_METRICS = (
    M_PGR_CITE, M_PGR_SUPPORT, M_PGR_HELDOUT, M_PGR_ADV, M_PGR_COMPOSITE,
)

# Rubric metrics (LLM-judged, 1..5)
RUBRIC_METRICS = ("relevance_to_goal", "novelty", "rigor", "citation_quality")


@dataclass(frozen=True)
class CountersRow:
    agent_id: int | None
    metric: str
    value: float


def _record(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    agent_id: int | None,
    metric: str,
    value: float,
    turn: int,
) -> None:
    conn.execute(
        "INSERT INTO kpi_scores (project_id, agent_id, metric, value, turn) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, agent_id, metric, float(value), turn),
    )


def snapshot_counters(
    conn: sqlite3.Connection, *, project_id: int, turn: int
) -> list[CountersRow]:
    """Compute and persist per-agent + project-level counters for a turn."""
    out: list[CountersRow] = []

    # Per-agent post count
    for r in conn.execute(
        "SELECT agent_id, COUNT(*) n FROM channel_posts "
        "WHERE project_id = ? GROUP BY agent_id",
        (project_id,),
    ):
        _record(
            conn,
            project_id=project_id,
            agent_id=r["agent_id"],
            metric=M_POSTS_PUBLISHED,
            value=r["n"],
            turn=turn,
        )
        out.append(CountersRow(agent_id=r["agent_id"], metric=M_POSTS_PUBLISHED, value=r["n"]))

    # Per-agent blackboard counts by kind
    kind_to_metric = {
        KIND_EVIDENCE: M_EVIDENCE_FILED,
        KIND_HYPOTHESIS: M_HYPOTHESES_GENERATED,
        KIND_EXPERIMENT: M_EXPERIMENTS_DESIGNED,
        KIND_RESULT: M_RESULTS_RECORDED,
        KIND_CRITIQUE: M_CRITIQUES_ISSUED,
        KIND_DRAFT: M_DRAFT_SECTIONS,
    }
    for kind, metric in kind_to_metric.items():
        for r in conn.execute(
            "SELECT agent_id, COUNT(*) n FROM blackboard_entries "
            "WHERE project_id = ? AND kind = ? GROUP BY agent_id",
            (project_id, kind),
        ):
            _record(
                conn,
                project_id=project_id,
                agent_id=r["agent_id"],
                metric=metric,
                value=r["n"],
                turn=turn,
            )
            out.append(CountersRow(agent_id=r["agent_id"], metric=metric, value=r["n"]))

    # Project-level: evidence density = evidence / max(hypotheses, 1)
    ev = conn.execute(
        "SELECT COUNT(*) FROM blackboard_entries WHERE project_id = ? AND kind = ?",
        (project_id, KIND_EVIDENCE),
    ).fetchone()[0]
    hy = conn.execute(
        "SELECT COUNT(*) FROM blackboard_entries WHERE project_id = ? AND kind = ?",
        (project_id, KIND_HYPOTHESIS),
    ).fetchone()[0]
    density = ev / max(hy, 1)
    _record(
        conn,
        project_id=project_id,
        agent_id=None,
        metric=M_EVIDENCE_DENSITY,
        value=density,
        turn=turn,
    )
    out.append(CountersRow(agent_id=None, metric=M_EVIDENCE_DENSITY, value=density))

    # Coverage: distinct agents that contributed at least one post OR entry
    cov = conn.execute(
        "SELECT COUNT(DISTINCT agent_id) FROM ("
        "  SELECT agent_id FROM channel_posts WHERE project_id = ? "
        "  UNION "
        "  SELECT agent_id FROM blackboard_entries WHERE project_id = ?"
        ")",
        (project_id, project_id),
    ).fetchone()[0]
    _record(
        conn,
        project_id=project_id,
        agent_id=None,
        metric=M_COVERAGE,
        value=cov,
        turn=turn,
    )
    out.append(CountersRow(agent_id=None, metric=M_COVERAGE, value=cov))

    # Idea diversity: mean pairwise cosine distance over blackboard embeddings.
    # High = healthy exploration; low = convergence collapse.
    diversity = _compute_idea_diversity(conn, project_id)
    _record(
        conn,
        project_id=project_id,
        agent_id=None,
        metric=M_IDEA_DIVERSITY,
        value=diversity,
        turn=turn,
    )
    out.append(CountersRow(agent_id=None, metric=M_IDEA_DIVERSITY, value=diversity))

    # Echo rate: fraction of promotion attempts absorbed as echoes.
    totals = conn.execute(
        "SELECT COUNT(*) AS n_entries, COALESCE(SUM(echo_count), 0) AS n_echoes "
        "FROM blackboard_entries WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    n_entries = totals["n_entries"] or 0
    n_echoes = totals["n_echoes"] or 0
    attempts = n_entries + n_echoes
    echo_rate = (n_echoes / attempts) if attempts > 0 else 0.0
    _record(
        conn,
        project_id=project_id,
        agent_id=None,
        metric=M_ECHO_RATE,
        value=echo_rate,
        turn=turn,
    )
    out.append(CountersRow(agent_id=None, metric=M_ECHO_RATE, value=echo_rate))

    conn.commit()
    return out


def _compute_idea_diversity(conn: sqlite3.Connection, project_id: int) -> float:
    vecs: list[list[float]] = []
    for r in conn.execute(
        "SELECT embedding_json FROM blackboard_entries "
        "WHERE project_id = ? AND embedding_json IS NOT NULL",
        (project_id,),
    ):
        try:
            vecs.append(json.loads(r["embedding_json"]))
        except (TypeError, json.JSONDecodeError):
            continue
    if len(vecs) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            total += 1.0 - cosine(vecs[i], vecs[j])
            count += 1
    return total / count if count > 0 else 0.0


RUBRIC_PROMPT = """You are a strict research KPI judge. Score the supplied
research artifacts on a 1-5 scale across these four axes:

- relevance_to_goal: does the work advance the stated research goal?
- novelty: is the work non-obvious, or does it restate known facts?
- rigor: is the reasoning grounded in evidence, with caveats acknowledged?
- citation_quality: are sources traceable and appropriate?

Respond with a JSON object only, no prose, shaped like:
{"relevance_to_goal": N, "novelty": N, "rigor": N, "citation_quality": N, "notes": "..."}
"""


def judge_project(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    goal: str,
    llm: LLMClient,
    turn: int,
    sample_size: int = 40,
) -> dict[str, float | str]:
    """Have the LLM judge the project artifacts on the rubric. Persists scores."""
    posts = conn.execute(
        "SELECT agent_id, content FROM channel_posts WHERE project_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (project_id, sample_size),
    ).fetchall()
    entries = conn.execute(
        "SELECT agent_id, kind, content FROM blackboard_entries WHERE project_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (project_id, sample_size),
    ).fetchall()
    artifacts_text = "\n".join(
        [f"[post a={r['agent_id']}] {r['content']}" for r in posts]
        + [f"[{r['kind']} a={r['agent_id']}] {r['content']}" for r in entries]
    ) or "(no artifacts yet)"

    resp = llm.chat(
        "judge",
        messages=[
            {"role": "system", "content": RUBRIC_PROMPT},
            {
                "role": "user",
                "content": f"RESEARCH GOAL: {goal}\n\nARTIFACTS:\n{artifacts_text}",
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=512,
        temperature=0,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        scores = json.loads(raw)
    except json.JSONDecodeError:
        scores = {}

    for metric in RUBRIC_METRICS:
        v = scores.get(metric)
        if isinstance(v, (int, float)):
            _record(
                conn,
                project_id=project_id,
                agent_id=None,
                metric=metric,
                value=float(v),
                turn=turn,
            )
    conn.commit()
    return scores


def latest_snapshot(
    conn: sqlite3.Connection, *, project_id: int, metrics: Iterable[str] | None = None
) -> list[sqlite3.Row]:
    """Return the most recent value per (agent_id, metric) for a project."""
    where_metric = ""
    params: list = [project_id]
    if metrics:
        where_metric = "AND metric IN (" + ",".join("?" * len(tuple(metrics))) + ")"
        params.extend(tuple(metrics))
    return conn.execute(
        f"""
        SELECT agent_id, metric, value, turn
        FROM kpi_scores
        WHERE project_id = ? {where_metric}
        GROUP BY agent_id, metric
        HAVING turn = MAX(turn)
        ORDER BY metric, agent_id
        """,
        params,
    ).fetchall()

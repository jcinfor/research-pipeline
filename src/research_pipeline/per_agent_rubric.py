"""Per-agent rubric judge.

Where the project-level rubric in `kpi.py` asks "how good is the whole run?",
this module asks "how good is each individual agent?" — on six dimensions
(four shared with the project rubric, plus two agent-specific ones).

Output is persisted as `kpi_scores` rows with non-null `agent_id`. The
optimization loop (phase 2 Track B) reads these to identify the weakest
agent per iteration and tune its config.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .adapter import LLMClient
from .archetypes import by_id


AGENT_RUBRIC_METRICS: tuple[str, ...] = (
    "relevance_to_goal",
    "novelty",
    "rigor",
    "citation_quality",
    "role_consistency",
    "collaboration_signal",
)


AGENT_JUDGE_SYSTEM = """You are a strict research KPI judge scoring a single
agent's contributions to a multi-agent research simulation.

Score on each axis 1-5 (5 = strong, 1 = weak):

- relevance_to_goal: does this agent's work advance the stated research goal?
- novelty: is it non-obvious, or does it restate known facts?
- rigor: grounded in evidence, caveats acknowledged?
- citation_quality: are sources traceable and appropriate?
- role_consistency: did the agent stay in its archetype's distinctive voice?
- collaboration_signal: did the agent advance peers' work (reply, extend,
  challenge specifically), or did it talk past them?

Respond with a JSON object only, no prose:
{"relevance_to_goal": N, "novelty": N, "rigor": N, "citation_quality": N,
 "role_consistency": N, "collaboration_signal": N, "notes": "..."}
"""


@dataclass(frozen=True)
class AgentScoreRow:
    agent_id: int
    archetype: str
    scores: dict[str, float]
    notes: str


def _gather_agent_slice(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    agent_id: int,
    post_limit: int = 8,
    entry_limit: int = 6,
) -> tuple[list[str], list[str]]:
    posts = conn.execute(
        "SELECT content FROM channel_posts WHERE project_id = ? AND agent_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (project_id, agent_id, post_limit),
    ).fetchall()
    entries = conn.execute(
        "SELECT kind, content FROM blackboard_entries "
        "WHERE project_id = ? AND agent_id = ? ORDER BY id DESC LIMIT ?",
        (project_id, agent_id, entry_limit),
    ).fetchall()
    post_texts = [(r["content"] or "").replace("\n", " ")[:400] for r in posts]
    entry_texts = [
        f"[{r['kind']}] {(r['content'] or '').replace(chr(10), ' ')[:400]}"
        for r in entries
    ]
    return post_texts, entry_texts


def _format_agent_payload(
    *,
    archetype: str,
    role_hint: str,
    role_description: str,
    goal: str,
    posts: list[str],
    entries: list[str],
) -> str:
    lines: list[str] = []
    lines.append(f"RESEARCH GOAL: {goal}")
    lines.append("")
    lines.append(f"AGENT ARCHETYPE: {archetype} ({role_hint})")
    lines.append(f"ROLE: {role_description}")
    lines.append("")
    lines.append(f"POSTS BY THIS AGENT ({len(posts)}):")
    if posts:
        for p in posts:
            lines.append(f"- {p}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"BLACKBOARD ENTRIES BY THIS AGENT ({len(entries)}):")
    if entries:
        for e in entries:
            lines.append(f"- {e}")
    else:
        lines.append("  (none)")
    return "\n".join(lines)


def judge_agents(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    goal: str,
    llm: LLMClient,
    turn: int,
) -> list[AgentScoreRow]:
    """Score each agent in the project on the 6-dim rubric. Persists to
    `kpi_scores` with `agent_id` set. Returns one row per agent that
    actually has contributions — agents with no posts and no entries are
    skipped (judge won't have anything to score)."""
    agents = conn.execute(
        "SELECT id, archetype FROM agents WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()

    out: list[AgentScoreRow] = []
    for a in agents:
        aid = a["id"]
        archetype_id = a["archetype"]
        try:
            arch = by_id(archetype_id)
        except KeyError:
            continue
        posts, entries = _gather_agent_slice(conn, project_id=project_id, agent_id=aid)
        if not posts and not entries:
            continue
        payload = _format_agent_payload(
            archetype=archetype_id,
            role_hint=arch.role_hint,
            role_description=arch.system_prompt.splitlines()[0],
            goal=goal,
            posts=posts,
            entries=entries,
        )
        try:
            resp = llm.chat(
                "judge",
                messages=[
                    {"role": "system", "content": AGENT_JUDGE_SYSTEM},
                    {"role": "user", "content": payload},
                ],
                response_format={"type": "json_object"},
                max_tokens=512,
                temperature=0,
            )
        except Exception as e:
            print(f"[per-agent-rubric] judge failed for agent {aid}: {e}")
            continue
        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        scores: dict[str, float] = {}
        for metric in AGENT_RUBRIC_METRICS:
            v = data.get(metric)
            if isinstance(v, (int, float)):
                scores[metric] = float(v)
                conn.execute(
                    "INSERT INTO kpi_scores (project_id, agent_id, metric, value, turn) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (project_id, aid, metric, float(v), turn),
                )
        notes = str(data.get("notes", ""))[:500]
        out.append(AgentScoreRow(
            agent_id=aid, archetype=archetype_id, scores=scores, notes=notes,
        ))
    conn.commit()
    return out


def latest_per_agent_scores(
    conn: sqlite3.Connection, *, project_id: int
) -> dict[int, dict[str, float]]:
    """Return {agent_id: {metric: value}} with each agent's latest per-metric
    score (agent_id-keyed kpi_scores rows only)."""
    placeholders = ",".join("?" * len(AGENT_RUBRIC_METRICS))
    rows = conn.execute(
        f"""
        SELECT agent_id, metric, value FROM kpi_scores
        WHERE project_id = ? AND agent_id IS NOT NULL AND metric IN ({placeholders})
        AND turn = (
            SELECT MAX(turn) FROM kpi_scores k2
            WHERE k2.project_id = kpi_scores.project_id
            AND k2.agent_id = kpi_scores.agent_id
            AND k2.metric = kpi_scores.metric
        )
        """,
        (project_id, *AGENT_RUBRIC_METRICS),
    ).fetchall()
    out: dict[int, dict[str, float]] = {}
    for r in rows:
        out.setdefault(r["agent_id"], {})[r["metric"]] = float(r["value"])
    return out


def weakest_agent(
    per_agent_scores: dict[int, dict[str, float]],
    *,
    weights: dict[str, float] | None = None,
) -> tuple[int, str, float] | None:
    """Pick the agent with the lowest weighted-mean rubric. Also returns the
    single dimension that's lowest for that agent (used by the optimization
    loop's decision tree).

    Returns (agent_id, weakest_metric, weighted_score) or None if input empty.
    """
    if not per_agent_scores:
        return None
    weights = weights or {m: 1.0 for m in AGENT_RUBRIC_METRICS}
    weight_sum = sum(weights.get(m, 1.0) for m in AGENT_RUBRIC_METRICS)
    best: tuple[int, str, float] | None = None
    for agent_id, scores in per_agent_scores.items():
        weighted = sum(
            scores.get(m, 3.0) * weights.get(m, 1.0)
            for m in AGENT_RUBRIC_METRICS
        ) / weight_sum
        if best is None or weighted < best[2]:
            weakest_metric = min(
                AGENT_RUBRIC_METRICS,
                key=lambda m: scores.get(m, 3.0),
            )
            best = (agent_id, weakest_metric, weighted)
    return best

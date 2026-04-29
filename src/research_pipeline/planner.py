"""LLM-driven agent-archetype planner.

Given a research goal, the current user-wiki coverage, and the archetype
roster, pick a weighted subset of archetypes that best fits this project.
Prefers archetypes that fill gaps left by the wiki (e.g., if the wiki already
has lots of `evidence` on the topic, de-prioritize Scout).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .adapter import LLMClient
from .archetypes import ROSTER, by_id


@dataclass(frozen=True)
class PlannedAgent:
    archetype_id: str
    weight: int
    rationale: str


PLANNER_SYSTEM = """You are the Research Planner. Given a goal, a wiki-coverage
summary, and an archetype roster, return a weighted subset of archetypes to
activate for this project.

Rules:
- Always include at least one of: scout, hypogen, critic (the generative core).
- Always include reviewer if the project produces a report (assume yes).
- Prefer archetypes that fill GAPS: if the wiki already has strong evidence,
  downweight scout; if it has no critiques, include critic.
- Pick between 3 and 8 distinct archetypes total.
- Weights are integers 1-3 (count of agent instances to spawn per archetype).
- Return ONLY JSON, no prose:
{
  "archetypes": [
    {"id": "scout", "weight": 1, "rationale": "..."},
    {"id": "hypogen", "weight": 2, "rationale": "..."},
    ...
  ]
}
"""


def _format_roster() -> str:
    return "\n".join(
        f"- {a.id} ({a.name}): {a.system_prompt.splitlines()[0]}"
        for a in ROSTER
    )


def _wiki_coverage_summary(conn: sqlite3.Connection, user_id: int) -> str:
    rows = conn.execute(
        "SELECT kind, COUNT(*) n FROM user_wiki_entries "
        "WHERE user_id = ? GROUP BY kind ORDER BY n DESC",
        (user_id,),
    ).fetchall()
    if not rows:
        return "(empty — fresh slate, no prior project knowledge)"
    return ", ".join(f"{r['kind']}={r['n']}" for r in rows)


def plan_archetypes(
    conn: sqlite3.Connection,
    *,
    goal: str,
    user_id: int,
    n_agents: int,
    llm: LLMClient,
) -> list[PlannedAgent]:
    coverage = _wiki_coverage_summary(conn, user_id)
    user_msg = (
        f"GOAL: {goal}\n\n"
        f"WIKI COVERAGE (prior knowledge accumulated across the user's "
        f"previous projects): {coverage}\n\n"
        f"AGENT BUDGET: pick a subset whose weights sum to ~{n_agents}.\n\n"
        f"ARCHETYPE ROSTER:\n{_format_roster()}\n\n"
        "Return the weighted subset that best advances this goal given the "
        "existing wiki coverage. Follow the JSON shape exactly."
    )
    resp = llm.chat(
        "planner",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        max_tokens=1024,
        temperature=0.2,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Conservative fallback: the standard phase-1 trio.
        return [
            PlannedAgent("scout", 1, "fallback: planner returned invalid JSON"),
            PlannedAgent("hypogen", 1, "fallback"),
            PlannedAgent("critic", 1, "fallback"),
        ]

    out: list[PlannedAgent] = []
    for item in data.get("archetypes", []):
        aid = item.get("id")
        if not aid:
            continue
        try:
            by_id(aid)
        except KeyError:
            continue  # planner hallucinated an archetype
        weight = max(1, min(3, int(item.get("weight", 1))))
        rationale = str(item.get("rationale", ""))[:400]
        out.append(PlannedAgent(archetype_id=aid, weight=weight, rationale=rationale))

    if not out:
        return [
            PlannedAgent("scout", 1, "fallback: empty plan"),
            PlannedAgent("hypogen", 1, "fallback"),
            PlannedAgent("critic", 1, "fallback"),
        ]
    return out


def expand_plan_to_archetype_list(plan: list[PlannedAgent]) -> list[str]:
    """Flatten weighted plan into the per-agent archetype list used by
    `create_project` (one entry per agent instance)."""
    out: list[str] = []
    for p in plan:
        out.extend([p.archetype_id] * p.weight)
    return out

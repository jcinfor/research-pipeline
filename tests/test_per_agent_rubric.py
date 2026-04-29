import json
from dataclasses import dataclass
from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, KIND_HYPOTHESIS, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.per_agent_rubric import (
    AGENT_RUBRIC_METRICS,
    _gather_agent_slice,
    judge_agents,
    latest_per_agent_scores,
    weakest_agent,
)
from research_pipeline.projects import create_project, update_agent_config, upsert_user


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _FakeJudge:
    """Returns a pre-seeded JSON response per agent_id.

    The simulation identifies agents by order; we read `calls` in order and
    pop responses to simulate different verdicts per agent.
    """

    def __init__(self, per_agent_responses: list[dict]):
        self._queue = [json.dumps(r) for r in per_agent_responses]
        self.calls = 0

    def chat(self, role, messages, **kwargs):
        self.calls += 1
        text = self._queue.pop(0) if self._queue else "{}"
        return _Resp(choices=[_Choice(message=_Msg(content=text))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        return [[0.0] * 8 for _ in texts]


def _setup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="test goal",
            archetype_ids=["scout", "hypogen", "critic"],
        )
        scout_id, hypogen_id, critic_id = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,)
            )
        ]
    return db, pid, scout_id, hypogen_id, critic_id


def test_agent_config_defaults(tmp_path: Path):
    db, pid, scout_id, _, _ = _setup(tmp_path)
    with connect(db) as conn:
        from research_pipeline.projects import get_project_agents
        agents = get_project_agents(conn, pid)
    scout = next(a for a in agents if a.id == scout_id)
    assert scout.temperature == 0.75
    assert scout.max_tokens == 300
    assert scout.specialty_focus is None
    assert scout.token_budget == 20000


def test_update_agent_config_patches_only_given_fields(tmp_path: Path):
    db, pid, scout_id, _, _ = _setup(tmp_path)
    with connect(db) as conn:
        update_agent_config(conn, agent_id=scout_id, temperature=0.5, specialty_focus="kras")
        from research_pipeline.projects import get_project_agents
        scout = next(a for a in get_project_agents(conn, pid) if a.id == scout_id)
    assert scout.temperature == 0.5
    assert scout.specialty_focus == "kras"
    # Untouched fields stay at defaults
    assert scout.max_tokens == 300
    assert scout.token_budget == 20000


def test_gather_agent_slice_only_own_rows(tmp_path: Path):
    db, pid, scout_id, hypogen_id, _ = _setup(tmp_path)
    with connect(db) as conn:
        conn.executemany(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, 'twitter', ?, ?, 0)",
            [
                (pid, scout_id, "scout post A"),
                (pid, scout_id, "scout post B"),
                (pid, hypogen_id, "hypogen post"),
            ],
        )
        conn.commit()
        posts, entries = _gather_agent_slice(
            conn, project_id=pid, agent_id=scout_id,
        )
    assert len(posts) == 2
    assert all("scout" in p for p in posts)


def test_judge_agents_persists_per_agent_scores(tmp_path: Path):
    db, pid, scout_id, hypogen_id, critic_id = _setup(tmp_path)
    with connect(db) as conn:
        # Give each agent one post so they all have material to judge
        conn.executemany(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, 'twitter', ?, ?, 0)",
            [
                (pid, scout_id, "scout claims X [src #1]"),
                (pid, hypogen_id, "hypogen proposes Y"),
                (pid, critic_id, "critic challenges Y"),
            ],
        )
        conn.commit()
        llm = _FakeJudge([
            {
                "relevance_to_goal": 4, "novelty": 4, "rigor": 4,
                "citation_quality": 5, "role_consistency": 5,
                "collaboration_signal": 3, "notes": "solid scout",
            },
            {
                "relevance_to_goal": 3, "novelty": 2, "rigor": 2,
                "citation_quality": 2, "role_consistency": 3,
                "collaboration_signal": 2, "notes": "weak",
            },
            {
                "relevance_to_goal": 5, "novelty": 4, "rigor": 5,
                "citation_quality": 3, "role_consistency": 5,
                "collaboration_signal": 4, "notes": "strong critic",
            },
        ])
        rows = judge_agents(
            conn, project_id=pid, goal="test", llm=llm, turn=1,
        )
        scores = latest_per_agent_scores(conn, project_id=pid)

    assert len(rows) == 3
    assert llm.calls == 3
    assert set(scores.keys()) == {scout_id, hypogen_id, critic_id}
    for metric in AGENT_RUBRIC_METRICS:
        assert metric in scores[scout_id]
        assert scores[scout_id][metric] > 0


def test_weakest_agent_picks_lowest_weighted(tmp_path: Path):
    scores = {
        10: {"relevance_to_goal": 5, "novelty": 5, "rigor": 5,
             "citation_quality": 5, "role_consistency": 5,
             "collaboration_signal": 5},
        20: {"relevance_to_goal": 3, "novelty": 2, "rigor": 2,
             "citation_quality": 3, "role_consistency": 3,
             "collaboration_signal": 2},
        30: {"relevance_to_goal": 4, "novelty": 4, "rigor": 4,
             "citation_quality": 4, "role_consistency": 4,
             "collaboration_signal": 4},
    }
    weakest_id, weakest_metric, weighted = weakest_agent(scores)
    assert weakest_id == 20
    # Tied at 2.0 between novelty, rigor, collaboration; min() returns first
    assert weakest_metric in ("novelty", "rigor", "collaboration_signal")
    assert abs(weighted - sum(scores[20].values()) / 6) < 1e-6


def test_judge_skips_agents_with_no_material(tmp_path: Path):
    db, pid, scout_id, hypogen_id, critic_id = _setup(tmp_path)
    with connect(db) as conn:
        # Only scout has a post
        conn.execute(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, 'twitter', ?, 'only post', 0)",
            (pid, scout_id),
        )
        conn.commit()
        llm = _FakeJudge([
            {"relevance_to_goal": 4, "novelty": 4, "rigor": 4,
             "citation_quality": 4, "role_consistency": 4,
             "collaboration_signal": 4},
        ])
        rows = judge_agents(
            conn, project_id=pid, goal="test", llm=llm, turn=1,
        )
    assert len(rows) == 1
    assert rows[0].agent_id == scout_id
    assert llm.calls == 1  # only called for the agent with material

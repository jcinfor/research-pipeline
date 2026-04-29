import json
from pathlib import Path

from research_pipeline.db import connect, init_db
from research_pipeline.planner import (
    expand_plan_to_archetype_list,
    plan_archetypes,
    PlannedAgent,
)
from research_pipeline.projects import upsert_user
from research_pipeline.wiki import promote_project_to_wiki


class _FakeJSONLLM:
    """Returns a canned JSON response on chat. Used to test parser + fallback."""

    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def chat(self, role, messages, **kwargs):
        self.calls.append((role, messages, kwargs))
        class _M:
            content = self.response
        class _C:
            message = _M()
        class _R:
            choices = [_C()]
        return _R()

    # stubs for interface compatibility
    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        return [[0.0] * 64 for _ in texts]


def _setup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
    return db, uid


def test_plan_parses_valid_json(tmp_path: Path):
    db, uid = _setup(tmp_path)
    llm = _FakeJSONLLM(json.dumps({
        "archetypes": [
            {"id": "scout", "weight": 2, "rationale": "need fresh sources"},
            {"id": "hypogen", "weight": 1, "rationale": "generate options"},
            {"id": "critic", "weight": 2, "rationale": "pressure test"},
        ]
    }))
    with connect(db) as conn:
        plan = plan_archetypes(
            conn, goal="test goal", user_id=uid, n_agents=5, llm=llm,
        )
    assert [p.archetype_id for p in plan] == ["scout", "hypogen", "critic"]
    assert [p.weight for p in plan] == [2, 1, 2]
    assert "fresh sources" in plan[0].rationale

    flat = expand_plan_to_archetype_list(plan)
    assert flat == ["scout", "scout", "hypogen", "critic", "critic"]


def test_plan_fallback_on_bad_json(tmp_path: Path):
    db, uid = _setup(tmp_path)
    llm = _FakeJSONLLM("not json at all")
    with connect(db) as conn:
        plan = plan_archetypes(conn, goal="g", user_id=uid, n_agents=3, llm=llm)
    assert len(plan) == 3
    assert {p.archetype_id for p in plan} == {"scout", "hypogen", "critic"}


def test_plan_skips_hallucinated_archetypes(tmp_path: Path):
    db, uid = _setup(tmp_path)
    llm = _FakeJSONLLM(json.dumps({
        "archetypes": [
            {"id": "scout", "weight": 1},
            {"id": "unicorn", "weight": 1},
            {"id": "hypogen", "weight": 1},
        ]
    }))
    with connect(db) as conn:
        plan = plan_archetypes(conn, goal="g", user_id=uid, n_agents=3, llm=llm)
    ids = [p.archetype_id for p in plan]
    assert "unicorn" not in ids
    assert "scout" in ids and "hypogen" in ids


def test_plan_clamps_weight_range(tmp_path: Path):
    db, uid = _setup(tmp_path)
    llm = _FakeJSONLLM(json.dumps({
        "archetypes": [
            {"id": "scout", "weight": 99},
            {"id": "hypogen", "weight": 0},
            {"id": "critic", "weight": -5},
        ]
    }))
    with connect(db) as conn:
        plan = plan_archetypes(conn, goal="g", user_id=uid, n_agents=3, llm=llm)
    weights = {p.archetype_id: p.weight for p in plan}
    assert weights["scout"] == 3   # clamped down
    assert weights["hypogen"] == 1  # clamped up
    assert weights["critic"] == 1   # clamped up

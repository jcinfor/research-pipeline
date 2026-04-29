import json
from pathlib import Path

from research_pipeline.db import connect, init_db
from research_pipeline.optimize import (
    Adjustment,
    MAX_MAX_TOKENS,
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    _max_abs_delta,
    _persist_trace,
    _rubric_delta,
    apply_adjustment,
    propose_adjustment,
)
from research_pipeline.projects import (
    create_project,
    get_project_agents,
    update_agent_config,
    upsert_user,
)


def test_propose_rigor_cools_agent():
    adj = propose_adjustment(
        weakest_metric="rigor",
        current_temperature=0.75,
        current_max_tokens=300,
        current_specialty_focus=None,
        project_goal="g",
    )
    assert adj.action == "lower_temperature"
    assert adj.temperature == 0.65


def test_propose_novelty_warms_agent():
    adj = propose_adjustment(
        weakest_metric="novelty",
        current_temperature=0.75,
        current_max_tokens=300,
        current_specialty_focus=None,
        project_goal="g",
    )
    assert adj.action == "raise_temperature"
    assert adj.temperature == 0.85


def test_propose_relevance_sets_specialty_focus():
    adj = propose_adjustment(
        weakest_metric="relevance_to_goal",
        current_temperature=0.75,
        current_max_tokens=300,
        current_specialty_focus=None,
        project_goal="find KRAS inhibitors",
    )
    assert adj.action == "set_specialty_focus"
    assert adj.specialty_focus is not None
    assert "KRAS" in adj.specialty_focus


def test_propose_collaboration_expands_tokens():
    adj = propose_adjustment(
        weakest_metric="collaboration_signal",
        current_temperature=0.75,
        current_max_tokens=300,
        current_specialty_focus=None,
        project_goal="g",
    )
    assert adj.action == "raise_max_tokens"
    assert adj.max_tokens == 380


def test_propose_clamps_temperature_to_floor():
    adj = propose_adjustment(
        weakest_metric="rigor",
        current_temperature=MIN_TEMPERATURE,
        current_max_tokens=300,
        current_specialty_focus=None,
        project_goal="g",
    )
    assert adj.temperature == MIN_TEMPERATURE


def test_propose_clamps_temperature_to_ceiling():
    adj = propose_adjustment(
        weakest_metric="novelty",
        current_temperature=MAX_TEMPERATURE,
        current_max_tokens=300,
        current_specialty_focus=None,
        project_goal="g",
    )
    assert adj.temperature == MAX_TEMPERATURE


def test_propose_max_tokens_capped():
    adj = propose_adjustment(
        weakest_metric="collaboration_signal",
        current_temperature=0.75,
        current_max_tokens=MAX_MAX_TOKENS,
        current_specialty_focus=None,
        project_goal="g",
    )
    assert adj.max_tokens == MAX_MAX_TOKENS


def test_propose_unknown_metric_returns_noop():
    adj = propose_adjustment(
        weakest_metric="made_up_dimension",
        current_temperature=0.75,
        current_max_tokens=300,
        current_specialty_focus=None,
        project_goal="g",
    )
    assert adj.action == "noop"


def test_rubric_delta_computes_per_metric_change():
    before = {"relevance_to_goal": 3.0, "novelty": 2.0, "rigor": 4.0, "citation_quality": 3.0}
    after = {"relevance_to_goal": 4.0, "novelty": 3.0, "rigor": 4.0, "citation_quality": 2.0}
    delta = _rubric_delta(before, after)
    assert delta["relevance_to_goal"] == 1.0
    assert delta["novelty"] == 1.0
    assert delta["rigor"] == 0.0
    assert delta["citation_quality"] == -1.0
    assert _max_abs_delta(delta) == 1.0


def test_apply_adjustment_updates_agent_config(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="g", archetype_ids=["scout"])
        scout = get_project_agents(conn, pid)[0]
        adj = Adjustment(
            action="lower_temperature",
            rationale="rigor low",
            temperature=0.5,
        )
        apply_adjustment(conn, agent_id=scout.id, decision=adj)
        scout_after = get_project_agents(conn, pid)[0]
    assert scout_after.temperature == 0.5
    assert scout_after.max_tokens == scout.max_tokens  # untouched


def test_apply_adjustment_noop_does_nothing(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="g", archetype_ids=["scout"])
        scout_before = get_project_agents(conn, pid)[0]
        adj = Adjustment(action="noop", rationale="nothing to do")
        apply_adjustment(conn, agent_id=scout_before.id, decision=adj)
        scout_after = get_project_agents(conn, pid)[0]
    assert scout_before == scout_after


def test_persist_trace_writes_row(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="g", archetype_ids=["scout"])
        scout = get_project_agents(conn, pid)[0]
        adj = Adjustment(action="lower_temperature", rationale="test",
                         temperature=0.6)
        _persist_trace(
            conn,
            project_id=pid,
            iteration=0,
            weakest_agent_id=scout.id,
            decision=adj,
            kpi_before={"relevance_to_goal": 3.0, "novelty": 3.0, "rigor": 3.0, "citation_quality": 3.0},
            kpi_after={"relevance_to_goal": 4.0, "novelty": 3.0, "rigor": 3.0, "citation_quality": 3.0},
        )
        row = conn.execute(
            "SELECT iteration, weakest_agent_id, decision_rationale, "
            "config_delta_json, kpi_before_json, kpi_after_json "
            "FROM optimization_traces WHERE project_id = ?",
            (pid,),
        ).fetchone()
    assert row is not None
    assert row["iteration"] == 0
    assert row["weakest_agent_id"] == scout.id
    assert row["decision_rationale"] == "test"
    delta = json.loads(row["config_delta_json"])
    assert delta["action"] == "lower_temperature"
    assert delta["temperature"] == 0.6
    before = json.loads(row["kpi_before_json"])
    after = json.loads(row["kpi_after_json"])
    assert before["relevance_to_goal"] == 3.0
    assert after["relevance_to_goal"] == 4.0

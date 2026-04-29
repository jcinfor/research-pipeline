"""Tests for iteration_summary — markdown digest emitted per optimize iteration."""
from pathlib import Path

from research_pipeline.blackboard import (
    KIND_CRITIQUE, KIND_HYPOTHESIS, KIND_RESULT, add_entry,
)
from research_pipeline.db import connect, init_db
from research_pipeline.iteration_summary import (
    write_iteration_summary, write_optimization_index,
)
from research_pipeline.lifecycle import resolve_hypothesis_refs
from research_pipeline.projects import create_project, upsert_user


def _setup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="test goal",
            archetype_ids=["hypogen", "critic", "replicator"],
        )
        agent_ids = [
            r["id"] for r in conn.execute(
                "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,)
            )
        ]
    return db, pid, agent_ids


def test_write_iteration_summary_produces_markdown_with_transitions(tmp_path: Path):
    db, pid, agent_ids = _setup(tmp_path)
    hypogen, critic, replicator = agent_ids
    project_dir = tmp_path / "projects"
    with connect(db) as conn:
        h1 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="P implies Q", turn=0, agent_id=hypogen)
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"[hyp #{h1}] is unclear",
                  turn=1, agent_id=critic)
        add_entry(conn, project_id=pid, kind=KIND_RESULT,
                  content=f"Replication confirms [hyp #{h1}]",
                  turn=2, agent_id=replicator)
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        resolve_hypothesis_refs(conn, project_id=pid, turn=2)

        path = write_iteration_summary(
            conn,
            project_id=pid,
            iteration_index=0,
            turn_start=0,
            turn_end=2,
            weakest_agent_id=critic,
            weakest_metric="rigor",
            decision_action="lower_temperature",
            decision_rationale="rigor low",
            kpi_before={"rigor": 2.5, "novelty": 3.5},
            kpi_after={"rigor": 3.0, "novelty": 3.3},
            project_dir=project_dir,
        )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    # Header
    assert f"# Iteration 0 — project {pid}" in text
    # Decision context
    assert f"weakest agent: `{critic}`" in text
    assert "lower_temperature" in text
    assert "rigor low" in text
    # KPI table
    assert "rigor" in text
    assert "novelty" in text
    # Hypothesis transitions present
    assert f"[hyp #{h1}]" in text
    assert "supported" in text  # final state
    assert "Hypothesis transitions" in text
    # Blackboard summary
    assert "New blackboard entries" in text


def test_write_iteration_summary_handles_no_transitions(tmp_path: Path):
    db, pid, agent_ids = _setup(tmp_path)
    hypogen = agent_ids[0]
    project_dir = tmp_path / "projects"
    with connect(db) as conn:
        # Only a hypothesis added; no critique/result so no transitions
        add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                  content="Untouched", turn=0, agent_id=hypogen)
        path = write_iteration_summary(
            conn,
            project_id=pid,
            iteration_index=1,
            turn_start=0,
            turn_end=0,
            weakest_agent_id=None,
            weakest_metric=None,
            decision_action=None,
            decision_rationale=None,
            kpi_before={},
            kpi_after={},
            project_dir=project_dir,
        )
    text = path.read_text(encoding="utf-8")
    assert "_(none)_" in text  # transitions section empty
    assert "weakest agent: _none identified_" in text


def test_write_optimization_index_lists_iterations(tmp_path: Path):
    project_dir = tmp_path / "projects"
    iter_dir = project_dir / "project_42" / "iterations"
    iter_dir.mkdir(parents=True)
    p0 = iter_dir / "iter_00.md"
    p1 = iter_dir / "iter_01.md"
    p0.write_text("dummy", encoding="utf-8")
    p1.write_text("dummy", encoding="utf-8")

    idx = write_optimization_index(
        project_id=42,
        iteration_paths=[p0, p1],
        project_dir=project_dir,
    )
    assert idx.exists()
    text = idx.read_text(encoding="utf-8")
    assert "iter_00.md" in text
    assert "iter_01.md" in text
    assert "2 iterations" in text

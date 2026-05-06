"""Integration test: optimize_project orchestration with a mocked simulation.

The real simulation is too heavy for unit tests, so we monkey-patch
run_simulation to just insert per-agent + project KPI rows that mimic what
a real turn would produce. This exercises:
    - trace persistence across iterations
    - decision-tree selection based on weakest rubric dimension
    - apply_adjustment mutates the agent config
    - plateau termination
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from research_pipeline.db import connect, init_db
from research_pipeline.kpi import RUBRIC_METRICS
from research_pipeline.optimize import optimize_project
from research_pipeline.per_agent_rubric import AGENT_RUBRIC_METRICS
from research_pipeline.projects import create_project, get_project_agents, upsert_user


def _seed_project(db: Path) -> tuple[int, int]:
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="optimize integration test",
            archetype_ids=["scout"],
        )
        scout_id = get_project_agents(conn, pid)[0].id
    return pid, scout_id


def _insert_kpi_scores(
    db: Path, *, pid: int, scout_id: int, turn: int,
    per_agent_values: dict[str, float], project_value: float,
) -> None:
    with connect(db) as conn:
        for metric, value in per_agent_values.items():
            conn.execute(
                "INSERT INTO kpi_scores (project_id, agent_id, metric, value, turn) "
                "VALUES (?, ?, ?, ?, ?)",
                (pid, scout_id, metric, value, turn),
            )
        for metric in RUBRIC_METRICS:
            conn.execute(
                "INSERT INTO kpi_scores (project_id, agent_id, metric, value, turn) "
                "VALUES (?, NULL, ?, ?, ?)",
                (pid, metric, project_value, turn),
            )
        conn.commit()


def test_optimize_runs_two_iterations_and_adjusts_for_low_novelty(tmp_path: Path, monkeypatch):
    db = tmp_path / "rp.db"
    pid, scout_id = _seed_project(db)
    work_dir = tmp_path / "runs"
    work_dir.mkdir()

    iteration_counter = {"n": 0}

    async def fake_run_simulation(sim_cfg, *, db_path, work_dir, llm=None, **_):
        iteration_counter["n"] += 1
        # Simulate: novelty stays low (2), others strong (4) — should trigger
        # raise_temperature each iteration
        per_agent = {
            "relevance_to_goal": 4.0,
            "novelty": 2.0,
            "rigor": 4.0,
            "citation_quality": 4.0,
            "role_consistency": 4.0,
            "collaboration_signal": 4.0,
        }
        # Project rubric improves slightly each iteration so first iter passes
        # plateau check, second hits it.
        project_value = 3.0 + 0.4 * iteration_counter["n"]
        _insert_kpi_scores(
            db, pid=pid, scout_id=scout_id,
            turn=iteration_counter["n"],
            per_agent_values=per_agent,
            project_value=project_value,
        )

    monkeypatch.setattr(
        "research_pipeline.simulation.run_simulation", fake_run_simulation
    )

    # This test pins the rubric-path lifecycle (weakest=novelty -> raise_temp).
    # Pass objective="rubric" explicitly so the test stays stable independent
    # of the function's default (flipped to "pgr" in the project-15 findings PR).
    result = asyncio.run(
        optimize_project(
            project_id=pid, iterations=2, turns_per=1,
            db_path=db, work_dir=work_dir, objective="rubric",
        )
    )

    # Two iterations ran
    assert iteration_counter["n"] == 2
    assert result.iterations_run == 2
    assert len(result.trace) == 2

    # First iteration: weakest = novelty -> raise_temperature 0.75 -> 0.85
    first = result.trace[0]
    assert first.weakest_agent_id == scout_id
    assert first.weakest_metric == "novelty"
    assert first.decision is not None
    assert first.decision.action == "raise_temperature"
    assert first.decision.temperature == 0.85

    # Agent config mutated by the decision
    with connect(db) as conn:
        scout_after = get_project_agents(conn, pid)[0]
    # After iter 0 the decision raised temp; iter 1 is the last iteration so
    # no further decision is applied (optimize skips the decision on the
    # final iteration to avoid leaving untested config).
    assert scout_after.temperature == 0.85

    # Second iteration has no decision applied (last iteration guard)
    second = result.trace[1]
    assert second.decision is None

    # Trace persisted to optimization_traces
    with connect(db) as conn:
        rows = conn.execute(
            "SELECT iteration, weakest_agent_id, decision_rationale "
            "FROM optimization_traces WHERE project_id = ? ORDER BY iteration",
            (pid,),
        ).fetchall()
    assert len(rows) == 2
    assert rows[0]["iteration"] == 0
    assert rows[0]["weakest_agent_id"] == scout_id
    assert "novelty" in (rows[0]["decision_rationale"] or "").lower()


def test_optimize_with_pgr_objective_uses_pgr_delta(tmp_path: Path, monkeypatch):
    """With --objective pgr, the plateau check is driven by the pgr_composite
    delta — the rubric can climb arbitrarily without terminating, and PGR can
    plateau even when rubric is changing."""
    db = tmp_path / "rp.db"
    pid, scout_id = _seed_project(db)
    work_dir = tmp_path / "runs"
    work_dir.mkdir()
    project_dir = tmp_path / "projects"

    # Pre-write a claims.md so synthesize doesn't trigger
    claims_dir = project_dir / f"project_{pid}" / "artifacts"
    claims_dir.mkdir(parents=True)
    (claims_dir / "claims.md").write_text(
        "# Claims\n\n## C1: test\n- Status: unverified\n", encoding="utf-8"
    )

    iteration_counter = {"n": 0}

    async def fake_run_simulation(sim_cfg, *, db_path, work_dir, llm=None, **_):
        iteration_counter["n"] += 1
        _insert_kpi_scores(
            db, pid=pid, scout_id=scout_id,
            turn=iteration_counter["n"],
            per_agent_values={m: 4.0 for m in AGENT_RUBRIC_METRICS},
            # Rubric climbs to be a distractor
            project_value=2.0 + 1.0 * iteration_counter["n"],
        )

    # Mock score_project to return a flat PGR composite
    from research_pipeline import optimize as optmod

    class _FakeComposite:
        cite = 0.5
        heldout = 0.5
        adv = 0.5
        composite = 0.5

    def fake_score_project(conn, *, project_id, llm, project_dir, skip_adv=True):
        # Persist matching pgr row so _snapshot_project_rubric picks it up
        with connect(db) as c:
            c.execute(
                "INSERT INTO kpi_scores (project_id, agent_id, metric, value, turn) "
                "VALUES (?, NULL, 'pgr_composite', 0.5, ?)",
                (project_id, iteration_counter["n"]),
            )
            c.commit()
        return _FakeComposite()

    monkeypatch.setattr(
        "research_pipeline.simulation.run_simulation", fake_run_simulation
    )
    monkeypatch.setattr("research_pipeline.pgr.score_project", fake_score_project)

    # Pre-seed a baseline pgr_composite so the first delta is computable
    _insert_kpi_scores(
        db, pid=pid, scout_id=scout_id, turn=0,
        per_agent_values={m: 4.0 for m in AGENT_RUBRIC_METRICS},
        project_value=2.0,
    )
    with connect(db) as c:
        c.execute(
            "INSERT INTO kpi_scores (project_id, agent_id, metric, value, turn) "
            "VALUES (?, NULL, 'pgr_composite', 0.5, 0)",
            (pid,),
        )
        c.commit()

    result = asyncio.run(
        optimize_project(
            project_id=pid, iterations=5, turns_per=1,
            db_path=db, work_dir=work_dir,
            objective="pgr", project_dir=project_dir,
            plateau_patience=2,
        )
    )

    # PGR stays flat -> plateau fires despite rubric climbing
    assert result.terminated_reason == "plateau"
    assert result.iterations_run == 2


def test_optimize_terminates_on_plateau(tmp_path: Path, monkeypatch):
    db = tmp_path / "rp.db"
    pid, scout_id = _seed_project(db)
    work_dir = tmp_path / "runs"
    work_dir.mkdir()

    iteration_counter = {"n": 0}

    async def fake_run_simulation(sim_cfg, *, db_path, work_dir, llm=None, **_):
        iteration_counter["n"] += 1
        # Flat KPI every turn: plateau from the start
        _insert_kpi_scores(
            db, pid=pid, scout_id=scout_id,
            turn=iteration_counter["n"],
            per_agent_values={m: 3.0 for m in AGENT_RUBRIC_METRICS},
            project_value=3.0,  # no change from seed
        )

    monkeypatch.setattr(
        "research_pipeline.simulation.run_simulation", fake_run_simulation
    )

    # Seed baseline so first delta is zero
    _insert_kpi_scores(
        db, pid=pid, scout_id=scout_id, turn=0,
        per_agent_values={m: 3.0 for m in AGENT_RUBRIC_METRICS},
        project_value=3.0,
    )

    result = asyncio.run(
        optimize_project(
            project_id=pid, iterations=10, turns_per=1,
            db_path=db, work_dir=work_dir, plateau_patience=2,
        )
    )

    # Should stop after plateau_patience consecutive flat iterations.
    assert result.terminated_reason == "plateau"
    assert result.iterations_run == 2

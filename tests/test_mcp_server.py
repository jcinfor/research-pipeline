"""Smoke tests for the rp MCP server. Exercises tool registration and
each tool's round-trip against a temporary db / projects directory.

Long-running tools (rp_ingest's PDF → markdown conversion + embedding)
are exercised separately via the integration test that runs against a
sample paper; this module sticks to fast-running surface tests.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from research_pipeline.mcp_server import _reset_job_manager_for_tests, build_server


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run each test with cwd pinned to a fresh tmp dir so the MCP server's
    cwd-resolution defaults pick up the test's isolated db + projects dir."""
    monkeypatch.chdir(tmp_path)
    # Reset the lazy-singleton JobManager so it re-initializes against the
    # test's tmp_path db. Without this, the second test inherits the first
    # test's JobManager (pointing at a now-deleted db).
    _reset_job_manager_for_tests()
    return tmp_path


@pytest.fixture
def server(workspace: Path):
    return build_server()


def _call_tool(server, name: str, args: dict | None = None) -> dict:
    """FastMCP exposes tools via the call_tool() async API."""
    args = args or {}
    result = asyncio.run(server.call_tool(name, args))
    # call_tool returns a (content_list, structured_dict) tuple in mcp 1.x.
    if isinstance(result, tuple):
        return result[1] or {}
    return result  # older mcp returns dict directly


def test_tools_registered(server) -> None:
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "rp_list_projects",
        "rp_create_project",
        "rp_ingest",
        "rp_get_status",
        "rp_get_artifacts",
        "rp_run_simulation",
        "rp_run_optimize",
        "rp_synthesize",
    }


def test_list_projects_empty_workspace(server) -> None:
    """No db yet — should return an empty list with a hint."""
    out = _call_tool(server, "rp_list_projects")
    assert out["projects"] == []
    assert "note" in out


def test_create_then_list(server) -> None:
    create = _call_tool(server, "rp_create_project", {
        "goal": "Test goal", "archetypes": ["scout"],
    })
    pid = create["project_id"]
    assert pid >= 1
    assert create["archetypes"] == ["scout"]
    assert create["status"] == "created"

    listed = _call_tool(server, "rp_list_projects")
    assert listed["count"] == 1
    assert listed["projects"][0]["id"] == pid
    assert listed["projects"][0]["goal"] == "Test goal"


def test_create_with_default_archetypes(server) -> None:
    """Empty/null archetypes uses Phase-1 default subset."""
    out = _call_tool(server, "rp_create_project", {
        "goal": "Default archetypes test",
    })
    # Phase 1 subset is ("scout", "hypogen", "critic")
    assert set(out["archetypes"]) == {"scout", "hypogen", "critic"}


def test_create_with_all_archetypes(server) -> None:
    out = _call_tool(server, "rp_create_project", {
        "goal": "All archetypes test", "archetypes": ["all"],
    })
    assert len(out["archetypes"]) == 8


def test_rp_create_project_docstring_lists_actual_phase_1_subset(server) -> None:
    """Regression guard. The rp_create_project docstring is read by the LLM
    dispatcher to decide whether to call the tool and what archetypes to
    pass. If PHASE_1_SUBSET drifts away from what the docstring claims,
    the agent will confidently pass wrong values. Pin the docstring to the
    canonical subset.

    Originally caught by reviewer 2026-04-30: docstring claimed 5 archetypes
    (literature_scout, hypothesis_generator, critic, statistician,
    peer_reviewer); actual subset was 3 (scout, hypogen, critic).
    """
    from research_pipeline.archetypes import PHASE_1_SUBSET
    from research_pipeline.mcp_server import build_server

    s = build_server()
    import asyncio
    tools = asyncio.run(s.list_tools())
    tool = next(t for t in tools if t.name == "rp_create_project")
    desc = tool.description or ""
    for archetype_id in PHASE_1_SUBSET:
        assert archetype_id in desc, (
            f"PHASE_1_SUBSET id {archetype_id!r} is missing from "
            f"rp_create_project's docstring. Update the docstring to match "
            f"the actual subset, or update PHASE_1_SUBSET to match the docstring."
        )


def test_create_rejects_unknown_archetype(server) -> None:
    with pytest.raises(Exception):
        _call_tool(server, "rp_create_project", {
            "goal": "Bad archetypes", "archetypes": ["does_not_exist"],
        })


def test_create_rejects_empty_goal(server) -> None:
    with pytest.raises(Exception):
        _call_tool(server, "rp_create_project", {"goal": "   "})


def test_status_for_new_project(server) -> None:
    create = _call_tool(server, "rp_create_project", {
        "goal": "Status test", "archetypes": ["scout"],
    })
    pid = create["project_id"]
    status = _call_tool(server, "rp_get_status", {"project_id": pid})
    assert status["project_id"] == pid
    assert status["goal"] == "Status test"
    assert status["status"] in ("created", "active", "draft", None)
    assert status["blackboard"]["total_entries"] == 0
    assert status["artifacts_available"] == []


def test_status_missing_project_raises(server) -> None:
    _call_tool(server, "rp_create_project", {"goal": "x", "archetypes": ["scout"]})
    with pytest.raises(Exception):
        _call_tool(server, "rp_get_status", {"project_id": 99999})


def test_get_artifacts_no_artifacts_yet(server) -> None:
    create = _call_tool(server, "rp_create_project", {
        "goal": "Artifacts test", "archetypes": ["scout"],
    })
    pid = create["project_id"]
    out = _call_tool(server, "rp_get_artifacts", {"project_id": pid})
    assert out["artifacts"] == {}
    assert set(out["missing"]) == {
        "claims", "hypotheses", "experiments", "decision", "risks",
    }


def test_get_artifacts_returns_files_when_present(server, workspace: Path) -> None:
    """Drop synthetic artifact files into the expected location and confirm
    rp_get_artifacts surfaces them."""
    create = _call_tool(server, "rp_create_project", {
        "goal": "Artifact files test", "archetypes": ["scout"],
    })
    pid = create["project_id"]
    artifacts_dir = workspace / "projects" / f"project_{pid}" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "claims.md").write_text("# Claims\n\nC1: water is wet.\n")
    (artifacts_dir / "decision.md").write_text("# Decision\n\nShip it.\n")

    full = _call_tool(server, "rp_get_artifacts", {"project_id": pid})
    assert "claims" in full["artifacts"]
    assert "decision" in full["artifacts"]
    assert set(full["missing"]) == {"hypotheses", "experiments", "risks"}
    assert "water is wet" in full["artifacts"]["claims"]

    subset = _call_tool(server, "rp_get_artifacts", {
        "project_id": pid, "artifact_names": ["decision"],
    })
    assert list(subset["artifacts"].keys()) == ["decision"]
    assert subset["missing"] == []


def test_mcp_serve_probes_models_toml_on_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When models.toml is missing, `rp mcp serve` should write a clear
    warning to stderr at startup — not silently start a server that will
    fail on every LLM-dependent tool call later. Reviewer caught this
    2026-04-30: in MCP context the user may not see per-tool failures,
    just 'tool failed' from the agent.

    We exercise just the probe portion (the load_config() try/except
    block in mcp_serve), not server.run(), since the latter blocks on
    stdio. Cwd is pinned to a tmp dir with no models.toml on any of the
    resolution paths so the failure is deterministic.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RP_MODELS_TOML", raising=False)
    # Block the user-config-path fallback by pointing platformdirs at the
    # empty tmp tree. (load_config also falls back to a poc/models.toml
    # next to the package source — that path always exists in this repo,
    # so the probe-warning logic only fires when the user runs from a
    # directory genuinely missing config. We replicate that by pointing
    # the resolver at tmp_path.)
    from research_pipeline import config as rp_config

    monkeypatch.setattr(
        rp_config, "_candidate_paths",
        lambda explicit=None: [tmp_path / "models.toml"],
    )

    import sys
    try:
        rp_config.load_config()
        loaded = True
    except FileNotFoundError as e:
        loaded = False
        sys.stderr.write(f"WARNING: models.toml not found. {e}\n")

    captured = capsys.readouterr()
    assert not loaded, "Expected load_config() to fail in empty tmp dir"
    assert "models.toml not found" in captured.err
    assert "WARNING" in captured.err


def test_status_picks_up_artifacts_directory(server, workspace: Path) -> None:
    """`rp_get_status` lists which artifact files exist on disk."""
    create = _call_tool(server, "rp_create_project", {
        "goal": "Status sees artifacts test", "archetypes": ["scout"],
    })
    pid = create["project_id"]
    artifacts_dir = workspace / "projects" / f"project_{pid}" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "claims.md").write_text("stub")
    (artifacts_dir / "risks.md").write_text("stub")

    status = _call_tool(server, "rp_get_status", {"project_id": pid})
    assert set(status["artifacts_available"]) == {"claims", "risks"}


# ---------------------------------------------------------------------------
# Phase 2.2 — rp_run_simulation + extended rp_get_status (active jobs)
# ---------------------------------------------------------------------------

async def _async_call_tool(server, name: str, args: dict | None = None) -> dict:
    """Like _call_tool but uses await — required for tools that schedule
    background tasks (rp_run_simulation), since those tasks need to keep
    running after the call returns and asyncio.run() would tear down the
    loop too early."""
    args = args or {}
    result = await server.call_tool(name, args)
    if isinstance(result, tuple):
        return result[1] or {}
    return result


def _install_fast_simulation_stub(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace simulation.run_simulation with a fast async stub that
    records its call args. Returns a dict capturing call info so tests
    can assert on it."""
    from dataclasses import dataclass
    from pathlib import Path
    from research_pipeline import mcp_server

    @dataclass
    class FakeResult:
        project_id: int
        turns_run: int
        posts_total: int
        oasis_db_path: Path
        report_path: Path | None = None

    captured: dict = {"called": False}

    async def fake_run(sim_cfg, *, db_path, work_dir, llm=None):
        captured["called"] = True
        captured["project_id"] = sim_cfg.project_id
        captured["turns"] = sim_cfg.turn_cap
        captured["reddit_every"] = sim_cfg.reddit_round_every
        captured["db_path"] = db_path
        captured["work_dir"] = work_dir
        # tiny await so other coroutines can interleave
        import asyncio as _asyncio
        await _asyncio.sleep(0.01)
        return FakeResult(
            project_id=sim_cfg.project_id,
            turns_run=sim_cfg.turn_cap,
            posts_total=sim_cfg.turn_cap * 2,  # arbitrary stub
            oasis_db_path=work_dir / f"project_{sim_cfg.project_id}_oasis.db",
        )

    monkeypatch.setattr(mcp_server.simulation, "run_simulation", fake_run)
    return captured


async def _wait_for_terminal_status(
    server,
    project_id: int,
    timeout_s: float = 5.0,
) -> dict:
    """Poll rp_get_status until active_job is None (i.e. no longer
    queued/running) and returns the final status payload."""
    import asyncio as _asyncio
    deadline = _asyncio.get_event_loop().time() + timeout_s
    while _asyncio.get_event_loop().time() < deadline:
        status = await _async_call_tool(server, "rp_get_status", {"project_id": project_id})
        if status.get("active_job") is None and status.get("recent_jobs"):
            return status
        await _asyncio.sleep(0.02)
    raise AssertionError(f"Timed out waiting for project {project_id} to reach terminal state")


async def test_run_simulation_submits_job_and_completes(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: tool returns a job_id immediately; runner runs to
    completion against the fast stub; status eventually shows complete."""
    captured = _install_fast_simulation_stub(monkeypatch)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Run-sim test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    submit = await _async_call_tool(server, "rp_run_simulation", {
        "project_id": pid, "turns": 2, "reddit_every": 0,
    })
    assert "job_id" in submit
    assert submit["status"] == "queued"
    assert submit["kind"] == "simulation"
    assert submit["args"] == {"turns": 2, "reddit_every": 0}

    # Wait for the runner to finish.
    final = await _wait_for_terminal_status(server, pid)
    assert captured["called"] is True
    assert captured["project_id"] == pid
    assert captured["turns"] == 2

    # The completed job should be in recent_jobs with status=complete.
    completed = [j for j in final["recent_jobs"] if j["job_id"] == submit["job_id"]]
    assert len(completed) == 1
    assert completed[0]["status"] == "complete"
    assert completed[0]["result"]["turns_run"] == 2
    assert completed[0]["result"]["posts_total"] == 4
    assert completed[0]["progress_pct"] == 100


async def test_run_simulation_rejects_duplicate_with_project_in_use(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second submission against a project with an active job returns a
    structured project_in_use error, NOT another job_id."""
    # Use a stub that blocks until we let it go, so the first job stays
    # active long enough for the second submission to collide with it.
    import asyncio as _asyncio
    from dataclasses import dataclass
    from pathlib import Path
    from research_pipeline import mcp_server

    @dataclass
    class FakeResult:
        project_id: int
        turns_run: int
        posts_total: int
        oasis_db_path: Path
        report_path: Path | None = None

    block = _asyncio.Event()

    async def slow_run(sim_cfg, *, db_path, work_dir, llm=None):
        await block.wait()
        return FakeResult(
            project_id=sim_cfg.project_id, turns_run=1, posts_total=1,
            oasis_db_path=work_dir / "stub.db",
        )

    monkeypatch.setattr(mcp_server.simulation, "run_simulation", slow_run)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Concurrency-forbid test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    first = await _async_call_tool(server, "rp_run_simulation", {
        "project_id": pid, "turns": 1,
    })
    assert "job_id" in first
    first_job_id = first["job_id"]

    # Wait until first is actually running.
    for _ in range(100):
        status = await _async_call_tool(server, "rp_get_status", {"project_id": pid})
        if status["active_job"] and status["active_job"]["status"] == "running":
            break
        await _asyncio.sleep(0.02)

    # Submit a second; expect project_in_use error.
    second = await _async_call_tool(server, "rp_run_simulation", {
        "project_id": pid, "turns": 1,
    })
    assert second.get("error") == "project_in_use"
    assert second["active_job_id"] == first_job_id
    assert "hint" in second  # tells the agent to poll, not stack

    # Cleanup: let the slow_run finish so the test exits cleanly.
    block.set()
    await _wait_for_terminal_status(server, pid)


async def test_run_simulation_rejects_project_with_no_agents(
    server, monkeypatch: pytest.MonkeyPatch, workspace: Path,
) -> None:
    """A project with no agents can't run a simulation. The tool should
    raise synchronously (before submitting a job) so the agent gets a
    clear error, not a job_id that immediately fails."""
    _install_fast_simulation_stub(monkeypatch)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "No-agents test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    # Manually delete the project's agents to simulate the no-agents case.
    from research_pipeline.db import connect
    with connect(workspace / "research_pipeline.db") as conn:
        conn.execute("DELETE FROM agents WHERE project_id = ?", (pid,))
        conn.commit()

    with pytest.raises(Exception):  # FastMCP wraps ValueError; just ensure raise
        await _async_call_tool(server, "rp_run_simulation", {
            "project_id": pid, "turns": 1,
        })


async def test_get_status_includes_active_job_when_running(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rp_get_status's active_job field is populated while the job is in
    flight."""
    import asyncio as _asyncio
    from dataclasses import dataclass
    from pathlib import Path
    from research_pipeline import mcp_server

    @dataclass
    class FakeResult:
        project_id: int
        turns_run: int
        posts_total: int
        oasis_db_path: Path
        report_path: Path | None = None

    block = _asyncio.Event()

    async def blocked_run(sim_cfg, *, db_path, work_dir, llm=None):
        await block.wait()
        return FakeResult(
            project_id=sim_cfg.project_id, turns_run=1, posts_total=1,
            oasis_db_path=work_dir / "stub.db",
        )

    monkeypatch.setattr(mcp_server.simulation, "run_simulation", blocked_run)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Active-job-surfaced test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    submit = await _async_call_tool(server, "rp_run_simulation", {
        "project_id": pid, "turns": 1,
    })

    # Wait for the runner to start — its status moves from queued to running.
    for _ in range(100):
        status = await _async_call_tool(server, "rp_get_status", {"project_id": pid})
        if status["active_job"] and status["active_job"]["status"] == "running":
            break
        await _asyncio.sleep(0.02)
    else:
        block.set()  # cleanup
        raise AssertionError("Job never reached running state")

    assert status["active_job"]["job_id"] == submit["job_id"]
    assert status["active_job"]["kind"] == "simulation"
    # Cleanup.
    block.set()
    await _wait_for_terminal_status(server, pid)


async def test_get_status_active_job_clears_on_completion(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a job completes, active_job is None and recent_jobs lists it."""
    _install_fast_simulation_stub(monkeypatch)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Clears-on-complete test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    submit = await _async_call_tool(server, "rp_run_simulation", {
        "project_id": pid, "turns": 1,
    })

    final = await _wait_for_terminal_status(server, pid)
    assert final["active_job"] is None
    job_ids_in_recent = [j["job_id"] for j in final["recent_jobs"]]
    assert submit["job_id"] in job_ids_in_recent


# ---------------------------------------------------------------------------
# Phase 2.3 — rp_run_optimize + rp_synthesize
# ---------------------------------------------------------------------------

def _install_fast_optimize_stub(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace optimize.optimize_project with a fast async stub."""
    from dataclasses import dataclass, field
    from research_pipeline import mcp_server

    @dataclass
    class FakeOptResult:
        project_id: int
        iterations_run: int
        terminated_reason: str
        best_iteration: int
        trace: list = field(default_factory=list)

    captured: dict = {"called": False}

    async def fake_optimize(*, project_id, iterations, turns_per, db_path,
                            work_dir, llm=None, plateau_patience=2,
                            objective="pgr", project_dir, **kwargs):
        captured["called"] = True
        captured["project_id"] = project_id
        captured["iterations"] = iterations
        captured["turns_per"] = turns_per
        captured["objective"] = objective
        import asyncio as _asyncio
        await _asyncio.sleep(0.01)
        return FakeOptResult(
            project_id=project_id,
            iterations_run=iterations,
            terminated_reason="iteration_cap",
            best_iteration=iterations,
        )

    monkeypatch.setattr(mcp_server.optimize, "optimize_project", fake_optimize)
    return captured


def _install_fast_synthesize_stub(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace synthesize.synthesize_artifacts with a fast async stub."""
    from dataclasses import dataclass
    from pathlib import Path
    from research_pipeline import mcp_server

    @dataclass
    class FakeSynthResult:
        project_id: int
        out_dir: Path
        artifacts: dict

    captured: dict = {"called": False}

    async def fake_synthesize(conn, *, project_id, llm=None, out_dir=None,
                              project_dir=Path("./projects")):
        captured["called"] = True
        captured["project_id"] = project_id
        out = out_dir or (project_dir / f"project_{project_id}" / "artifacts")
        import asyncio as _asyncio
        await _asyncio.sleep(0.01)
        return FakeSynthResult(
            project_id=project_id,
            out_dir=out,
            artifacts={
                "claims": out / "claims.md",
                "hypotheses": out / "hypotheses.md",
                "experiments": out / "experiments.md",
                "decision": out / "decision.md",
                "risks": out / "risks.md",
            },
        )

    monkeypatch.setattr(
        mcp_server.synthesize, "synthesize_artifacts", fake_synthesize
    )
    return captured


async def test_run_optimize_submits_job_and_completes(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_fast_optimize_stub(monkeypatch)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Optimize test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    submit = await _async_call_tool(server, "rp_run_optimize", {
        "project_id": pid, "iterations": 2, "turns_per": 1,
    })
    assert "job_id" in submit
    assert submit["status"] == "queued"
    assert submit["kind"] == "optimize"
    assert submit["args"]["iterations"] == 2

    final = await _wait_for_terminal_status(server, pid)
    assert captured["called"] is True
    assert captured["iterations"] == 2
    assert captured["turns_per"] == 1

    job = next(j for j in final["recent_jobs"] if j["job_id"] == submit["job_id"])
    assert job["status"] == "complete"
    assert job["result"]["iterations_run"] == 2
    assert job["result"]["terminated_reason"] == "iteration_cap"


async def test_run_optimize_validates_objective(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad objective raises synchronously, before submitting a job."""
    _install_fast_optimize_stub(monkeypatch)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Objective-validation test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    with pytest.raises(Exception):
        await _async_call_tool(server, "rp_run_optimize", {
            "project_id": pid, "objective": "nonsense",
        })


async def test_run_optimize_concurrency_forbid(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A simulation in flight blocks an optimize submission for the same
    project — concurrency invariant is at the project level, not the
    job-kind level."""
    import asyncio as _asyncio
    from dataclasses import dataclass
    from pathlib import Path
    from research_pipeline import mcp_server

    @dataclass
    class FakeSim:
        project_id: int
        turns_run: int
        posts_total: int
        oasis_db_path: Path
        report_path: Path | None = None

    block = _asyncio.Event()

    async def slow_sim(sim_cfg, *, db_path, work_dir, llm=None):
        await block.wait()
        return FakeSim(
            project_id=sim_cfg.project_id, turns_run=1, posts_total=1,
            oasis_db_path=work_dir / "stub.db",
        )

    monkeypatch.setattr(mcp_server.simulation, "run_simulation", slow_sim)
    _install_fast_optimize_stub(monkeypatch)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Cross-kind concurrency test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    sim_submit = await _async_call_tool(server, "rp_run_simulation", {
        "project_id": pid, "turns": 1,
    })
    # Wait until simulation is running.
    for _ in range(100):
        status = await _async_call_tool(server, "rp_get_status", {"project_id": pid})
        if status["active_job"] and status["active_job"]["status"] == "running":
            break
        await _asyncio.sleep(0.02)

    # Optimize submit should be rejected — simulation is the active job.
    opt_submit = await _async_call_tool(server, "rp_run_optimize", {
        "project_id": pid, "iterations": 1, "turns_per": 1,
    })
    assert opt_submit.get("error") == "project_in_use"
    assert opt_submit["active_job_id"] == sim_submit["job_id"]
    assert opt_submit["active_job_kind"] == "simulation"

    # Cleanup.
    block.set()
    await _wait_for_terminal_status(server, pid)


async def test_synthesize_submits_job_and_completes(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_fast_synthesize_stub(monkeypatch)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Synthesize test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    submit = await _async_call_tool(server, "rp_synthesize", {"project_id": pid})
    assert "job_id" in submit
    assert submit["kind"] == "synthesize"
    assert submit["args"] == {}

    final = await _wait_for_terminal_status(server, pid)
    assert captured["called"] is True
    assert captured["project_id"] == pid

    job = next(j for j in final["recent_jobs"] if j["job_id"] == submit["job_id"])
    assert job["status"] == "complete"
    assert "claims" in job["result"]["artifacts"]
    assert "hypotheses" in job["result"]["artifacts"]
    assert "experiments" in job["result"]["artifacts"]
    assert "decision" in job["result"]["artifacts"]
    assert "risks" in job["result"]["artifacts"]


async def test_synthesize_concurrency_forbid_with_optimize(
    server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthesize submission rejected when an optimize is in flight on
    the same project. Round-trips the cross-kind concurrency invariant."""
    import asyncio as _asyncio
    from dataclasses import dataclass, field
    from research_pipeline import mcp_server

    @dataclass
    class FakeOptResult:
        project_id: int
        iterations_run: int
        terminated_reason: str
        best_iteration: int
        trace: list = field(default_factory=list)

    block = _asyncio.Event()

    async def slow_optimize(*, project_id, iterations, turns_per, **kwargs):
        await block.wait()
        return FakeOptResult(
            project_id=project_id, iterations_run=iterations,
            terminated_reason="iteration_cap", best_iteration=iterations,
        )

    monkeypatch.setattr(mcp_server.optimize, "optimize_project", slow_optimize)
    _install_fast_synthesize_stub(monkeypatch)

    create = await _async_call_tool(server, "rp_create_project", {
        "goal": "Synth-blocked-by-optimize test", "archetypes": ["scout"],
    })
    pid = create["project_id"]

    opt_submit = await _async_call_tool(server, "rp_run_optimize", {
        "project_id": pid, "iterations": 1, "turns_per": 1,
    })
    for _ in range(100):
        status = await _async_call_tool(server, "rp_get_status", {"project_id": pid})
        if status["active_job"] and status["active_job"]["status"] == "running":
            break
        await _asyncio.sleep(0.02)

    synth_submit = await _async_call_tool(server, "rp_synthesize", {"project_id": pid})
    assert synth_submit.get("error") == "project_in_use"
    assert synth_submit["active_job_id"] == opt_submit["job_id"]
    assert synth_submit["active_job_kind"] == "optimize"

    block.set()
    await _wait_for_terminal_status(server, pid)

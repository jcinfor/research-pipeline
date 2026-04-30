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

from research_pipeline.mcp_server import build_server


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run each test with cwd pinned to a fresh tmp dir so the MCP server's
    cwd-resolution defaults pick up the test's isolated db + projects dir."""
    monkeypatch.chdir(tmp_path)
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

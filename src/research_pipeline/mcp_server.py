"""rp as an MCP skill — exposes the research-pipeline surface to MCP clients.

Phase 1: five synchronous tools that fit comfortably under MCP's 30-60s
client timeouts. Each tool is a thin wrapper over an existing library
function in `projects.py` / `ingest.py` / etc., so the MCP surface stays
in lockstep with the CLI surface and there's no separate code path to
keep up to date.

  rp_list_projects        — list projects with id, goal, state
  rp_create_project       — create a new project with goal + archetypes
  rp_ingest               — ingest a document into a project
  rp_status               — full state for one project (counts + last activity)
  rp_get_artifacts        — fetch the synthesized artifacts (inline content)

Phase 2 adds async/long-running tools (rp_run_simulation, rp_run_optimize,
rp_synthesize) via the job-id pattern.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .archetypes import PHASE_1_SUBSET, ROSTER, by_id
from .db import connect, init_db
from .ingest import ingest_file
from .projects import (
    create_project,
    get_project,
    get_project_agents,
    list_projects,
    upsert_user,
)


def _resolve_db_path() -> Path:
    """Phase 1: single-user-per-server. The DB is wherever the user runs the
    server from (matching the CLI's cwd-based default `research_pipeline.db`)."""
    return Path.cwd() / "research_pipeline.db"


def _resolve_project_dir() -> Path:
    return Path.cwd() / "projects"


def build_server() -> FastMCP:
    mcp = FastMCP("research-pipeline")

    @mcp.tool()
    def rp_list_projects() -> dict[str, Any]:
        """List all projects in the local research-pipeline store. Returns
        each project's id, goal, focus, status, and assigned archetypes."""
        db_path = _resolve_db_path()
        if not db_path.exists():
            return {"projects": [], "note": f"No database found at {db_path}. "
                    "Run `rp init-db` or `rp project create` first."}
        init_db(db_path)
        with connect(db_path) as conn:
            projects = list_projects(conn)
            out = []
            for p in projects:
                agents = get_project_agents(conn, p.id)
                out.append({
                    "id": p.id,
                    "goal": p.goal,
                    "focus": p.focus,
                    "status": p.status,
                    "archetypes": [a.archetype for a in agents],
                })
        return {"projects": out, "count": len(out)}

    @mcp.tool()
    def rp_create_project(
        goal: str,
        archetypes: list[str] | None = None,
        user_email: str = "local@research-pipeline",
        focus: str | None = None,
    ) -> dict[str, Any]:
        """Create a new research project. Returns the new project id.

        archetypes is a list of archetype ids. Pass None or an empty list
        to use the default Phase-1 subset (literature_scout, hypothesis_generator,
        critic, statistician, peer_reviewer). Pass ['all'] for the full 8-agent
        roster. The 'auto' planner mode (LLM-selected archetypes) is not yet
        exposed via MCP; use the CLI for that.
        """
        if not goal.strip():
            raise ValueError("goal must not be empty")
        archetype_list: list[str]
        if not archetypes:
            archetype_list = list(PHASE_1_SUBSET)
        elif archetypes == ["all"]:
            archetype_list = [a.id for a in ROSTER]
        else:
            for aid in archetypes:
                by_id(aid)  # validates against ROSTER, raises if unknown
            archetype_list = archetypes

        db_path = _resolve_db_path()
        init_db(db_path)
        with connect(db_path) as conn:
            uid = upsert_user(conn, user_email)
            pid = create_project(
                conn, user_id=uid, goal=goal,
                archetype_ids=archetype_list, focus=focus,
            )
        return {
            "project_id": pid,
            "goal": goal,
            "archetypes": archetype_list,
            "status": "created",
        }

    @mcp.tool()
    def rp_ingest(
        project_id: int,
        path: str,
    ) -> dict[str, Any]:
        """Ingest a document (PDF, DOCX, PPTX, XLSX, MD) into a project's
        blackboard. The file is converted to markdown, chunked, embedded,
        and added as evidence entries.

        path is an absolute path readable by the server's filesystem. For
        a typical paper this takes 5-30 seconds depending on length and
        embedding-backend latency.
        """
        db_path = _resolve_db_path()
        init_db(db_path)
        target = Path(path).expanduser().resolve()
        if not target.exists():
            raise FileNotFoundError(f"file not found: {target}")
        work_dir = _resolve_project_dir() / f"project_{project_id}"
        work_dir.mkdir(parents=True, exist_ok=True)
        with connect(db_path) as conn:
            get_project(conn, project_id)  # raises if project missing
            result = ingest_file(
                conn,
                project_id=project_id,
                path=target,
                work_dir=work_dir,
            )
        return {
            "project_id": project_id,
            "file": result.file,
            "chunks": result.chunks,
            "added": result.added,
            "echoed": result.echoed,
        }

    @mcp.tool()
    def rp_status(project_id: int) -> dict[str, Any]:
        """Get a project's current state — goal, status, archetypes, plus
        counts of blackboard entries by kind and the latest activity timestamp.
        Use this to check whether a project is ready for `rp_get_artifacts`
        or still needs simulation runs."""
        db_path = _resolve_db_path()
        if not db_path.exists():
            raise FileNotFoundError(f"No database at {db_path}")
        init_db(db_path)
        with connect(db_path) as conn:
            project = get_project(conn, project_id)
            agents = get_project_agents(conn, project_id)
            kind_counts = dict(conn.execute(
                """SELECT kind, COUNT(*) FROM blackboard_entries
                   WHERE project_id = ? GROUP BY kind""",
                (project_id,),
            ).fetchall())
            total_entries = sum(kind_counts.values())
            last = conn.execute(
                """SELECT MAX(created_at) FROM blackboard_entries
                   WHERE project_id = ?""",
                (project_id,),
            ).fetchone()
            last_activity = last[0] if last else None

        artifacts_dir = _resolve_project_dir() / f"project_{project_id}" / "artifacts"
        artifact_names = []
        if artifacts_dir.exists():
            artifact_names = sorted(p.stem for p in artifacts_dir.glob("*.md"))

        return {
            "project_id": project_id,
            "goal": project.goal,
            "focus": project.focus,
            "status": project.status,
            "archetypes": [a.archetype for a in agents],
            "blackboard": {
                "total_entries": total_entries,
                "by_kind": kind_counts,
                "last_activity": last_activity,
            },
            "artifacts_available": artifact_names,
        }

    @mcp.tool()
    def rp_get_artifacts(
        project_id: int,
        artifact_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch synthesized artifacts for a project. Returns the artifact
        body inline (markdown text), keyed by name.

        artifact_names defaults to all five (claims, hypotheses, experiments,
        decision, risks). Pass a subset (e.g. ['decision', 'risks']) to fetch
        just those. Returns a 'missing' list for any artifact that hasn't
        been synthesized yet — call `rp_synthesize` (phase 2) or the CLI's
        `rp project synthesize` first if so.
        """
        artifacts_dir = _resolve_project_dir() / f"project_{project_id}" / "artifacts"
        if not artifacts_dir.exists():
            return {
                "project_id": project_id,
                "artifacts": {},
                "missing": ["claims", "hypotheses", "experiments", "decision", "risks"],
                "note": "No artifacts directory yet. Run synthesis first.",
            }
        wanted = artifact_names or ["claims", "hypotheses", "experiments", "decision", "risks"]
        produced: dict[str, str] = {}
        missing: list[str] = []
        for name in wanted:
            path = artifacts_dir / f"{name}.md"
            if path.exists():
                produced[name] = path.read_text(encoding="utf-8")
            else:
                missing.append(name)
        return {
            "project_id": project_id,
            "artifacts": produced,
            "missing": missing,
        }

    return mcp


# Module-level instance for `mcp dev`-style runners.
mcp = build_server()

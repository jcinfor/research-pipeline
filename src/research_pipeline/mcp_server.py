"""rp as an MCP skill — exposes the research-pipeline surface to MCP clients.

Phase 1: five synchronous tools that fit comfortably under MCP's 30-60s
client timeouts. Each tool is a thin wrapper over an existing library
function in `projects.py` / `ingest.py` / etc., so the MCP surface stays
in lockstep with the CLI surface and there's no separate code path to
keep up to date.

  rp_list_projects        — list projects with id, goal, state
  rp_create_project       — create a new project with goal + archetypes
  rp_ingest               — ingest a document into a project
  rp_get_status           — full state for one project (counts + last activity + active job)
  rp_get_artifacts        — fetch the synthesized artifacts (inline content)

Phase 2 (this commit and following) adds async/long-running tools via
the job-id pattern. The agent submits → polls rp_get_status → receives
result when status='complete'.

  rp_run_simulation       — start a simulation (turns + reddit_every) [phase 2.2]
  rp_run_optimize         — start the optimize loop [phase 2.3]
  rp_synthesize           — produce artifact bundle [phase 2.3]
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import optimize, simulation, synthesize  # module-level for test monkey-patching
from .adapter import LLMClient
from .archetypes import PHASE_1_SUBSET, ROSTER, by_id
from .db import connect, init_db
from .ingest import ingest_file
from .jobs import (
    KIND_OPTIMIZE,
    KIND_SIMULATION,
    KIND_SYNTHESIZE,
    Job,
    JobManager,
    ProgressReporter,
    ProjectInUseError,
)
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


def _resolve_work_dir() -> Path:
    """Where simulation OASIS DBs and CSV agent profiles land. Matches the
    CLI's default."""
    return Path.cwd() / "runs"


# Lazy-singleton JobManager. We don't instantiate at module import because
# that would call init_db() before the cwd is necessarily correct (e.g.
# tests use monkeypatch.chdir before calling build_server). Created on
# first need; reused thereafter.
_job_manager: JobManager | None = None


def _get_job_manager() -> JobManager:
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager(_resolve_db_path())
    return _job_manager


def _reset_job_manager_for_tests() -> None:
    """Tests that fork their cwd between runs need to re-instantiate the
    JobManager so it picks up the new db_path. Production code should
    never call this."""
    global _job_manager
    _job_manager = None


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

        archetypes is a list of archetype ids drawn from this roster of 8:

          scout         — Literature Scout
          hypogen       — Hypothesis Generator
          experimenter  — Experimenter
          critic        — Critic
          replicator    — Replicator
          statistician  — Statistician
          writer        — Writer
          reviewer      — Peer Reviewer

        Pass None or an empty list to use the default Phase-1 subset of 3
        (scout, hypogen, critic) — the lightest team that still produces a
        useful hypothesis matrix. Pass ['all'] for the full 8-agent roster.
        Pass any subset like ['scout', 'critic', 'reviewer'] for a custom team.

        The 'auto' planner mode (LLM-selected archetypes) is not yet exposed
        via MCP; use the CLI's `--archetypes auto` for that.
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
    def rp_get_status(project_id: int) -> dict[str, Any]:
        """Get a project's current state — goal, status, archetypes,
        blackboard counts, latest activity, available artifacts, plus any
        active or recent async jobs (simulation / optimize / synthesize).

        After calling rp_run_simulation (or other async tool), poll this
        endpoint to track progress: when active_job.status == 'complete',
        the simulation is done and artifacts can be fetched. If
        active_job.status == 'failed', the error field holds the message.
        """
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

        # Job state — phase 2.4. The active job (if any) is the queued or
        # running one; recent_jobs is up to 5 most-recent entries (any
        # status) so the agent can reason about prior runs.
        jm = _get_job_manager()
        active = jm.get_active_for_project(project_id)
        recent = jm.list_for_project(project_id, limit=5)

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
            "active_job": active.to_dict() if active else None,
            "recent_jobs": [j.to_dict() for j in recent],
        }

    @mcp.tool()
    def rp_run_simulation(
        project_id: int,
        turns: int = 3,
        reddit_every: int = 0,
    ) -> dict[str, Any]:
        """Start a simulation as a background job. Returns IMMEDIATELY
        with {job_id, status: 'queued'} — the simulation runs in the
        background and typically takes 5-30 minutes depending on the
        user's stack speed and document count.

        Workflow:
          1. Call this. Returns job_id within ~100ms.
          2. Poll rp_get_status(project_id). The active_job field shows
             the running job; check active_job.status until it reaches
             'complete', 'failed', or 'cancelled'.
          3. When status == 'complete', call rp_get_artifacts to fetch
             the synthesized result (if synthesis was part of the run).

        Concurrency: only ONE active job per project. If project_id
        already has a queued or running job, this returns
        {error: 'project_in_use', active_job_id, ...} instead of starting
        a new one. The agent should poll the active job rather than
        stacking submissions.

        Arguments:
          turns: number of simulation turns (default 3). Each turn runs
            the full archetype team for one cycle. 1 is smoke-test fast,
            3 is the substantive default, 5+ is rare.
          reddit_every: 0=off (default), N=run one Reddit thread every
            N Twitter turns. Reddit threads add depth (one archetype
            posts a topic, others reply) but slow each cycle by 2-3x.
        """
        db_path = _resolve_db_path()
        work_dir = _resolve_work_dir()
        jm = _get_job_manager()

        # Pre-check that the project exists and has agents before submitting
        # the job — better to fail synchronously here than have the runner
        # raise during async execution.
        if not db_path.exists():
            raise FileNotFoundError(f"No database at {db_path}")
        init_db(db_path)
        with connect(db_path) as conn:
            get_project(conn, project_id)  # raises if missing
            agents = get_project_agents(conn, project_id)
        if not agents:
            raise ValueError(f"project {project_id} has no agents assigned")

        async def runner(job: Job, reporter: ProgressReporter) -> dict[str, Any]:
            reporter.update(
                current_step=f"running simulation ({turns} turns)",
                progress_pct=5.0,
            )
            cfg = simulation.SimulationConfig(
                project_id=project_id,
                turn_cap=turns,
                reddit_round_every=reddit_every,
            )
            # simulation.run_simulation is the looked-up reference (not
            # `from .simulation import run_simulation`) so test
            # monkey-patches on the module-level symbol take effect.
            result = await simulation.run_simulation(
                cfg,
                db_path=db_path,
                work_dir=work_dir,
                llm=LLMClient(),
            )
            return {
                "project_id": result.project_id,
                "turns_run": result.turns_run,
                "posts_total": result.posts_total,
                "oasis_db_path": str(result.oasis_db_path),
            }

        try:
            job_id = jm.submit(
                kind=KIND_SIMULATION,
                project_id=project_id,
                args={"turns": turns, "reddit_every": reddit_every},
                runner=runner,
            )
        except ProjectInUseError as e:
            return {
                "error": "project_in_use",
                "message": str(e),
                "active_job_id": e.active_job.job_id,
                "active_job_kind": e.active_job.kind,
                "active_job_status": e.active_job.status,
                "hint": "poll rp_get_status(project_id) to track the active job; do not re-submit",
            }

        return {
            "job_id": job_id,
            "project_id": project_id,
            "kind": KIND_SIMULATION,
            "status": "queued",
            "args": {"turns": turns, "reddit_every": reddit_every},
            "hint": "poll rp_get_status(project_id) until active_job.status == 'complete'",
        }

    @mcp.tool()
    def rp_run_optimize(
        project_id: int,
        iterations: int = 3,
        turns_per: int = 2,
        objective: str = "rubric",
        plateau_patience: int = 2,
    ) -> dict[str, Any]:
        """Start the optimization loop as a background job. Each iteration:
        runs a short simulation (`turns_per` turns), scores agents on the
        6-dim rubric, identifies the weakest agent + dimension, applies a
        targeted config adjustment, records the trace.

        Returns IMMEDIATELY with {job_id, status: 'queued'}. Poll
        rp_get_status(project_id) until active_job.status == 'complete'.

        Concurrency: only ONE active job per project. If project_id has a
        queued/running simulation, optimize, or synthesize job, this
        returns {error: 'project_in_use', active_job_id, ...}.

        Arguments:
          iterations: max iterations (default 3). Loop terminates earlier
            on plateau (no rubric improvement above threshold for
            `plateau_patience` consecutive iterations).
          turns_per: simulation turns per iteration (default 2). Lower
            than rp_run_simulation's default because each iteration runs
            a complete simulation; cumulative cost grows fast.
          objective: 'rubric' (default — uses project rubric mean for
            plateau detection) or 'pgr' (uses PGR composite score —
            requires claims.md to exist; run rp_synthesize first).
          plateau_patience: consecutive iterations without single-dim
            improvement before terminating (default 2).
        """
        if objective not in ("rubric", "pgr"):
            raise ValueError(
                f"objective must be 'rubric' or 'pgr', got {objective!r}"
            )

        db_path = _resolve_db_path()
        work_dir = _resolve_work_dir()
        project_dir = _resolve_project_dir()
        jm = _get_job_manager()

        # Synchronous pre-check (same pattern as rp_run_simulation): catch
        # missing-project / no-agents up front rather than via async failure.
        if not db_path.exists():
            raise FileNotFoundError(f"No database at {db_path}")
        init_db(db_path)
        with connect(db_path) as conn:
            get_project(conn, project_id)
            agents = get_project_agents(conn, project_id)
        if not agents:
            raise ValueError(f"project {project_id} has no agents assigned")

        async def runner(job: Job, reporter: ProgressReporter) -> dict[str, Any]:
            reporter.update(
                current_step=f"running optimize ({iterations} iterations × {turns_per} turns)",
                progress_pct=5.0,
            )
            result = await optimize.optimize_project(
                project_id=project_id,
                iterations=iterations,
                turns_per=turns_per,
                db_path=db_path,
                work_dir=work_dir,
                llm=LLMClient(),
                plateau_patience=plateau_patience,
                objective=objective,
                project_dir=project_dir,
            )
            return {
                "project_id": result.project_id,
                "iterations_run": result.iterations_run,
                "terminated_reason": result.terminated_reason,
                "best_iteration": result.best_iteration,
            }

        try:
            job_id = jm.submit(
                kind=KIND_OPTIMIZE,
                project_id=project_id,
                args={
                    "iterations": iterations,
                    "turns_per": turns_per,
                    "objective": objective,
                    "plateau_patience": plateau_patience,
                },
                runner=runner,
            )
        except ProjectInUseError as e:
            return {
                "error": "project_in_use",
                "message": str(e),
                "active_job_id": e.active_job.job_id,
                "active_job_kind": e.active_job.kind,
                "active_job_status": e.active_job.status,
                "hint": "poll rp_get_status(project_id) to track the active job; do not re-submit",
            }

        return {
            "job_id": job_id,
            "project_id": project_id,
            "kind": KIND_OPTIMIZE,
            "status": "queued",
            "args": {
                "iterations": iterations,
                "turns_per": turns_per,
                "objective": objective,
                "plateau_patience": plateau_patience,
            },
            "hint": "poll rp_get_status(project_id) until active_job.status == 'complete'",
        }

    @mcp.tool()
    def rp_synthesize(project_id: int) -> dict[str, Any]:
        """Synthesize the five structured artifacts (claims, hypotheses,
        experiments, decision, risks) from the project's blackboard.
        Submitted as a background job (typical run: 1-3 minutes on a
        local stack).

        Returns IMMEDIATELY with {job_id, status: 'queued'}. Poll
        rp_get_status(project_id) until active_job.status == 'complete',
        then call rp_get_artifacts to fetch the bodies.

        Concurrency: only ONE active job per project. If project_id has a
        queued/running job (any kind), this returns
        {error: 'project_in_use', active_job_id, ...}.

        Synthesis runs against whatever's currently on the blackboard —
        if you haven't run a simulation yet, the artifacts will be sparse
        but still produced (empty hypotheses matrix, etc.). Run
        rp_run_simulation first for substantive output.
        """
        db_path = _resolve_db_path()
        project_dir = _resolve_project_dir()
        jm = _get_job_manager()

        if not db_path.exists():
            raise FileNotFoundError(f"No database at {db_path}")
        init_db(db_path)
        with connect(db_path) as conn:
            get_project(conn, project_id)  # raises if missing

        async def runner(job: Job, reporter: ProgressReporter) -> dict[str, Any]:
            reporter.update(
                current_step="synthesizing artifacts",
                progress_pct=10.0,
            )
            with connect(db_path) as conn:
                result = await synthesize.synthesize_artifacts(
                    conn,
                    project_id=project_id,
                    llm=LLMClient(),
                    project_dir=project_dir,
                )
            return {
                "project_id": result.project_id,
                "out_dir": str(result.out_dir),
                "artifacts": {name: str(path) for name, path in result.artifacts.items()},
            }

        try:
            job_id = jm.submit(
                kind=KIND_SYNTHESIZE,
                project_id=project_id,
                args={},
                runner=runner,
            )
        except ProjectInUseError as e:
            return {
                "error": "project_in_use",
                "message": str(e),
                "active_job_id": e.active_job.job_id,
                "active_job_kind": e.active_job.kind,
                "active_job_status": e.active_job.status,
                "hint": "poll rp_get_status(project_id) to track the active job; do not re-submit",
            }

        return {
            "job_id": job_id,
            "project_id": project_id,
            "kind": KIND_SYNTHESIZE,
            "status": "queued",
            "args": {},
            "hint": "poll rp_get_status(project_id) until active_job.status == 'complete', then call rp_get_artifacts",
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

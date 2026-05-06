"""Async-job tracking for the rp MCP server's long-running tools.

Phase 2.1 of the MCP-server plan. This module is standalone — phase 2.2-2.3
adds the MCP tools (`rp_run_simulation`, `rp_run_optimize`, `rp_synthesize`)
that submit work here.

Lifecycle: queued → running → {complete, failed, cancelled, orphaned}.

The model: in-process asyncio tasks plus SQLite for persistence. Single
process, no cross-process locking, no distributed queue. If the server
crashes mid-job the next startup marks orphaned 'running' rows as
orphaned (the prior process's pid no longer matches), so the
single-active-job-per-project invariant doesn't false-positive on stale
state.

Concurrency invariant: at most one active (queued or running) job per
project. Submitting a second one raises ProjectInUseError carrying the
active job. The MCP tools surface this as a structured error so the
agent can poll the active job via `rp_get_status` instead of stacking
submissions.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .db import connect, init_db


# Status values for a job's lifecycle. Imported by tests + tool wrappers.
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_ORPHANED = "orphaned"

ACTIVE_STATUSES: frozenset[str] = frozenset({STATUS_QUEUED, STATUS_RUNNING})
TERMINAL_STATUSES: frozenset[str] = frozenset({
    STATUS_COMPLETE, STATUS_FAILED, STATUS_CANCELLED, STATUS_ORPHANED,
})

# Kinds we expect — phase 2.2-2.3 will route these to the right runner.
# Strings, not an enum, so callers can use whatever they want — the
# manager doesn't gatekeep.
KIND_SIMULATION = "simulation"
KIND_OPTIMIZE = "optimize"
KIND_SYNTHESIZE = "synthesize"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    """Snapshot of a row in the `jobs` table."""

    job_id: str
    project_id: int
    kind: str
    status: str
    args: dict[str, Any]
    progress_pct: float
    current_step: str | None
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    pid: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        return cls(
            job_id=row["job_id"],
            project_id=row["project_id"],
            kind=row["kind"],
            status=row["status"],
            args=json.loads(row["args_json"] or "{}"),
            progress_pct=row["progress_pct"],
            current_step=row["current_step"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            pid=row["pid"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Stable shape for MCP responses. Excludes pid (internal-only)."""
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "status": self.status,
            "args": self.args,
            "progress_pct": self.progress_pct,
            "current_step": self.current_step,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class ProjectInUseError(Exception):
    """Raised when a job submission targets a project_id that already has
    an active job. The agent should poll the active job's status instead
    of stacking submissions."""

    def __init__(self, active_job: Job):
        self.active_job = active_job
        super().__init__(
            f"project {active_job.project_id} has an active job "
            f"(job_id={active_job.job_id}, kind={active_job.kind}, "
            f"status={active_job.status})"
        )


# A runner is the async work the job actually performs. It receives the
# job snapshot (so it can read its args) plus a ProgressReporter (so it
# can stream progress updates). It returns a JSON-serializable dict
# captured into the job row's result_json.
JobRunner = Callable[["Job", "ProgressReporter"], Awaitable[dict[str, Any]]]


class ProgressReporter:
    """Passed to runners by JobManager. Mutates the job row's
    progress_pct and current_step as the runner makes progress.

    Cheap: each update issues a single short-circuited SQL UPDATE.
    Calling .update() without arguments is a no-op."""

    def __init__(self, manager: JobManager, job_id: str):
        self._manager = manager
        self._job_id = job_id

    def update(
        self,
        *,
        current_step: str | None = None,
        progress_pct: float | None = None,
    ) -> None:
        self._manager._record_progress(self._job_id, current_step, progress_pct)


class JobManager:
    """In-process job tracker with SQLite persistence.

    Lifecycle:
      - On instantiation, init_db() is called and orphan cleanup runs
        (any 'running' rows from a different pid get marked orphaned).
      - submit() inserts a queued row, schedules an asyncio task,
        returns the job_id.
      - The task runs the runner; updates the row's status as it goes.
      - get(), get_active_for_project(), list_for_project() query rows.
      - cancel() sets status=cancelled and cancels the running task.
      - shutdown() cancels all running tasks; marks them orphaned.
    """

    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = str(db_path)
        init_db(self.db_path)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cleanup_orphans_at_startup()

    # ---- internal helpers ----

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def _cleanup_orphans_at_startup(self) -> None:
        """Mark stale 'running' rows from prior process(es) as orphaned.
        We don't probe whether the prior pid is alive — the safer
        invariant is 'a running row owned by a different pid means we
        restarted; mark it orphaned so the project_in_use check doesn't
        false-positive forever.'"""
        my_pid = os.getpid()
        with self._conn() as conn:
            conn.execute(
                """UPDATE jobs SET status = ?, error = ?, completed_at = ?
                   WHERE status = ? AND pid != ?""",
                (STATUS_ORPHANED, "server restarted before job completed",
                 _now_iso(), STATUS_RUNNING, my_pid),
            )
            conn.commit()

    def _record_progress(
        self,
        job_id: str,
        current_step: str | None,
        progress_pct: float | None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if current_step is not None:
            sets.append("current_step = ?")
            params.append(current_step)
        if progress_pct is not None:
            sets.append("progress_pct = ?")
            params.append(max(0.0, min(100.0, progress_pct)))
        if not sets:
            return
        params.append(job_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE jobs SET {', '.join(sets)} WHERE job_id = ?",
                params,
            )
            conn.commit()

    def _record_completion(self, job_id: str, result: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE jobs SET status = ?, result_json = ?,
                                  progress_pct = 100, completed_at = ?
                   WHERE job_id = ? AND status = ?""",
                (STATUS_COMPLETE, json.dumps(result), _now_iso(),
                 job_id, STATUS_RUNNING),
            )
            conn.commit()

    def _record_failure(self, job_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE jobs SET status = ?, error = ?, completed_at = ?
                   WHERE job_id = ? AND status = ?""",
                (STATUS_FAILED, error, _now_iso(), job_id, STATUS_RUNNING),
            )
            conn.commit()

    async def _run(self, job_id: str, runner: JobRunner) -> None:
        """Execute the runner; capture result or error in the row.

        Note: the row's status is mutated to 'cancelled' synchronously
        by cancel() before this task gets cancelled. _record_completion
        and _record_failure both no-op when status != 'running', so
        cancellation racing with completion stays consistent."""
        # Mark started.
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, started_at = ? WHERE job_id = ? AND status = ?",
                (STATUS_RUNNING, _now_iso(), job_id, STATUS_QUEUED),
            )
            conn.commit()

        job = self.get(job_id)
        if job is None:
            return  # row vanished — shouldn't happen
        reporter = ProgressReporter(self, job_id)

        try:
            result = await runner(job, reporter)
        except asyncio.CancelledError:
            # cancel() already wrote status=cancelled. Re-raise so the
            # asyncio.Task ends in cancelled state.
            raise
        except Exception as e:  # noqa: BLE001 — capture-all is the contract
            self._record_failure(job_id, repr(e))
            return

        self._record_completion(job_id, result)

    # ---- public API ----

    def submit(
        self,
        *,
        kind: str,
        project_id: int,
        args: dict[str, Any],
        runner: JobRunner,
    ) -> str:
        """Submit a job. Returns the new job_id.

        Raises ProjectInUseError if `project_id` already has an active
        (queued or running) job. The agent should poll the active job
        via the MCP `rp_get_status` tool instead of stacking submissions.

        Must be called from inside a running asyncio event loop —
        asyncio.create_task() is used to schedule the runner.
        """
        active = self.get_active_for_project(project_id)
        if active is not None:
            raise ProjectInUseError(active)

        job_id = uuid.uuid4().hex[:12]
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO jobs
                   (job_id, project_id, kind, status, args_json,
                    progress_pct, created_at, pid)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
                (job_id, project_id, kind, STATUS_QUEUED,
                 json.dumps(args), _now_iso(), os.getpid()),
            )
            conn.commit()

        task = asyncio.create_task(self._run(job_id, runner))
        self._tasks[job_id] = task
        # Drop the task entry once it completes so _tasks doesn't grow
        # unboundedly. (The row stays in the db; only the in-memory
        # handle goes away.)
        task.add_done_callback(lambda _t, jid=job_id: self._tasks.pop(jid, None))
        return job_id

    def get(self, job_id: str) -> Job | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return Job.from_row(row) if row else None

    def get_active_for_project(self, project_id: int) -> Job | None:
        """Return the queued-or-running job for project_id, or None."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM jobs
                   WHERE project_id = ? AND status IN (?, ?)
                   ORDER BY created_at DESC LIMIT 1""",
                (project_id, STATUS_QUEUED, STATUS_RUNNING),
            ).fetchone()
        return Job.from_row(row) if row else None

    def list_for_project(self, project_id: int, limit: int = 20) -> list[Job]:
        """Return up to `limit` jobs for project_id, most recent first."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM jobs WHERE project_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (project_id, limit),
            ).fetchall()
        return [Job.from_row(r) for r in rows]

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running or queued job. Returns True if the job was
        active and got cancelled, False if it was already terminal or
        unknown."""
        job = self.get(job_id)
        if job is None or job.is_terminal:
            return False

        # Set status FIRST so any in-flight progress updates from the
        # runner don't overwrite the cancelled marker.
        with self._conn() as conn:
            conn.execute(
                """UPDATE jobs SET status = ?, completed_at = ?
                   WHERE job_id = ? AND status IN (?, ?)""",
                (STATUS_CANCELLED, _now_iso(), job_id,
                 STATUS_QUEUED, STATUS_RUNNING),
            )
            conn.commit()

        task = self._tasks.pop(job_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        return True

    async def shutdown(self) -> None:
        """Cancel all in-flight tasks and mark them orphaned. Call from
        the MCP server's shutdown hook so we don't leave dangling
        running rows that the next startup has to clean up."""
        for job_id, task in list(self._tasks.items()):
            if task.done():
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            with self._conn() as conn:
                conn.execute(
                    """UPDATE jobs SET status = ?, error = ?, completed_at = ?
                       WHERE job_id = ? AND status NOT IN (?, ?, ?, ?)""",
                    (STATUS_ORPHANED, "server shutdown", _now_iso(), job_id,
                     STATUS_COMPLETE, STATUS_FAILED, STATUS_CANCELLED, STATUS_ORPHANED),
                )
                conn.commit()
        self._tasks.clear()

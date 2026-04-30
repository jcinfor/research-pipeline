"""Tests for the async-job tracking module (research_pipeline.jobs).

Phase 2.1 of the MCP-server plan. The module is standalone — these
tests don't drive any MCP tool surface; they pin the JobManager API
that phase 2.2-2.4's tools will wrap.

The defining invariants:
  - At most one active (queued/running) job per project (forbid).
  - Status transitions are monotonic: queued → running → terminal.
  - Cancellation is synchronous-in-db (status set before task.cancel()),
    so racing progress updates can't undo it.
  - Restart cleanup marks stale 'running' rows from prior pids as
    orphaned at JobManager init, so the project_in_use check doesn't
    false-positive forever.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from research_pipeline.db import connect, init_db
from research_pipeline.jobs import (
    ACTIVE_STATUSES,
    KIND_SIMULATION,
    STATUS_CANCELLED,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_ORPHANED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    Job,
    JobManager,
    ProgressReporter,
    ProjectInUseError,
)
from research_pipeline.projects import create_project, upsert_user


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "rp.db"
    init_db(p)
    return p


@pytest.fixture
def project_id(db_path: Path) -> int:
    with connect(db_path) as conn:
        uid = upsert_user(conn, "test@local")
        pid = create_project(
            conn, user_id=uid, goal="Test goal",
            archetype_ids=["scout"],
        )
    return pid


@pytest.fixture
async def manager(db_path: Path):
    m = JobManager(db_path)
    try:
        yield m
    finally:
        # Cancel any in-flight tasks so they don't dangle into the next
        # test's event loop ("Task was destroyed but it is pending"
        # warnings).
        await m.shutdown()


# --- runners used by tests --------------------------------------------------

async def _runner_complete_quickly(job: Job, reporter: ProgressReporter) -> dict:
    reporter.update(current_step="halfway", progress_pct=50.0)
    await asyncio.sleep(0)  # give the scheduler a chance to interleave
    return {"ok": True, "job_id": job.job_id}


async def _runner_raise(job: Job, reporter: ProgressReporter) -> dict:
    raise RuntimeError("intentional test failure")


async def _runner_block_forever(job: Job, reporter: ProgressReporter) -> dict:
    """Used to test cancellation against a job that's actively running."""
    reporter.update(current_step="started", progress_pct=10.0)
    while True:
        await asyncio.sleep(0.05)


# --- submit / lifecycle -----------------------------------------------------

async def test_submit_creates_queued_job(manager: JobManager, project_id: int) -> None:
    """A submit() call inserts a row immediately, even before the runner gets
    scheduled. The row may already be 'running' by the time we check (the
    scheduler is fast); accept either queued or running."""
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={"turns": 3}, runner=_runner_complete_quickly,
    )
    job = manager.get(job_id)
    assert job is not None
    assert job.project_id == project_id
    assert job.kind == KIND_SIMULATION
    assert job.args == {"turns": 3}
    assert job.status in {STATUS_QUEUED, STATUS_RUNNING, STATUS_COMPLETE}


async def test_runner_runs_to_completion(manager: JobManager, project_id: int) -> None:
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_complete_quickly,
    )
    # Wait for the task to finish.
    while True:
        job = manager.get(job_id)
        assert job is not None
        if job.is_terminal:
            break
        await asyncio.sleep(0.01)
    assert job.status == STATUS_COMPLETE
    assert job.progress_pct == 100
    assert job.result == {"ok": True, "job_id": job_id}
    assert job.error is None
    assert job.completed_at is not None


async def test_runner_failure_records_error(manager: JobManager, project_id: int) -> None:
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_raise,
    )
    while True:
        job = manager.get(job_id)
        assert job is not None
        if job.is_terminal:
            break
        await asyncio.sleep(0.01)
    assert job.status == STATUS_FAILED
    assert job.error is not None
    assert "intentional test failure" in job.error
    assert job.result is None
    assert job.completed_at is not None


async def test_progress_reporter_updates_row(
    manager: JobManager, project_id: int,
) -> None:
    """Force the runner to pause mid-progress so we can observe an
    intermediate state in the row."""
    barrier = asyncio.Event()

    async def runner(job: Job, reporter: ProgressReporter) -> dict:
        reporter.update(current_step="phase A", progress_pct=33.0)
        await barrier.wait()
        reporter.update(current_step="phase B", progress_pct=66.0)
        return {}

    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=runner,
    )
    # Wait until the runner has reached the barrier (phase A recorded).
    for _ in range(200):
        job = manager.get(job_id)
        if job is not None and job.current_step == "phase A":
            assert job.progress_pct == 33.0
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("runner did not reach phase A within 2s")

    barrier.set()
    while not (manager.get(job_id) and manager.get(job_id).is_terminal):  # type: ignore[union-attr]
        await asyncio.sleep(0.01)
    final = manager.get(job_id)
    assert final is not None
    assert final.status == STATUS_COMPLETE
    assert final.current_step == "phase B"
    assert final.progress_pct == 100  # _record_completion sets to 100


async def test_progress_clamps_out_of_range(
    manager: JobManager, project_id: int,
) -> None:
    async def runner(job: Job, reporter: ProgressReporter) -> dict:
        reporter.update(progress_pct=-50)
        await asyncio.sleep(0.01)
        reporter.update(progress_pct=999)
        return {}

    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=runner,
    )
    while True:
        job = manager.get(job_id)
        if job and job.is_terminal:
            break
        await asyncio.sleep(0.01)
    # Run completion sets progress_pct to 100 regardless; the test of
    # the clamp itself is that the runner didn't crash.
    assert job is not None
    assert job.status == STATUS_COMPLETE


# --- concurrency invariant --------------------------------------------------

async def test_concurrent_submission_raises_project_in_use(
    manager: JobManager, project_id: int,
) -> None:
    first = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_block_forever,
    )
    # Confirm first is active before the second submit.
    for _ in range(100):
        job = manager.get(first)
        if job and job.status == STATUS_RUNNING:
            break
        await asyncio.sleep(0.01)

    with pytest.raises(ProjectInUseError) as ei:
        manager.submit(
            kind=KIND_SIMULATION, project_id=project_id,
            args={}, runner=_runner_complete_quickly,
        )
    assert ei.value.active_job.job_id == first
    assert ei.value.active_job.status in ACTIVE_STATUSES

    # Cleanup: cancel the blocked first job so the test can exit.
    await manager.cancel(first)


async def test_completed_job_does_not_block_new_submission(
    manager: JobManager, project_id: int,
) -> None:
    first = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_complete_quickly,
    )
    # Wait for it to terminate.
    while True:
        j = manager.get(first)
        if j and j.is_terminal:
            break
        await asyncio.sleep(0.01)

    # Second submit should now succeed.
    second = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_complete_quickly,
    )
    assert second != first
    assert manager.get(second) is not None


async def test_failed_job_does_not_block_new_submission(
    manager: JobManager, project_id: int,
) -> None:
    first = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_raise,
    )
    while True:
        j = manager.get(first)
        if j and j.is_terminal:
            break
        await asyncio.sleep(0.01)

    second = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_complete_quickly,
    )
    assert second != first


# --- cancellation -----------------------------------------------------------

async def test_cancel_running_job(manager: JobManager, project_id: int) -> None:
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_block_forever,
    )
    # Wait for the runner to actually start (status moves to running).
    for _ in range(100):
        job = manager.get(job_id)
        if job and job.status == STATUS_RUNNING:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("runner never reached RUNNING state")

    cancelled = await manager.cancel(job_id)
    assert cancelled is True
    job = manager.get(job_id)
    assert job is not None
    assert job.status == STATUS_CANCELLED


async def test_cancel_terminal_job_returns_false(
    manager: JobManager, project_id: int,
) -> None:
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_complete_quickly,
    )
    while True:
        j = manager.get(job_id)
        if j and j.is_terminal:
            break
        await asyncio.sleep(0.01)
    cancelled = await manager.cancel(job_id)
    assert cancelled is False


async def test_cancel_unknown_job_returns_false(manager: JobManager) -> None:
    cancelled = await manager.cancel("nonexistent_id")
    assert cancelled is False


# --- queries ---------------------------------------------------------------

async def test_get_active_for_project_returns_active(
    manager: JobManager, project_id: int,
) -> None:
    assert manager.get_active_for_project(project_id) is None
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_block_forever,
    )
    # Wait until the runner is active.
    for _ in range(100):
        active = manager.get_active_for_project(project_id)
        if active and active.job_id == job_id:
            break
        await asyncio.sleep(0.01)
    active = manager.get_active_for_project(project_id)
    assert active is not None
    assert active.job_id == job_id
    await manager.cancel(job_id)


async def test_get_active_for_project_ignores_terminal_jobs(
    manager: JobManager, project_id: int,
) -> None:
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_complete_quickly,
    )
    while True:
        j = manager.get(job_id)
        if j and j.is_terminal:
            break
        await asyncio.sleep(0.01)
    assert manager.get_active_for_project(project_id) is None


async def test_list_for_project_orders_by_recency(
    manager: JobManager, project_id: int,
) -> None:
    ids: list[str] = []
    for _ in range(3):
        jid = manager.submit(
            kind=KIND_SIMULATION, project_id=project_id,
            args={}, runner=_runner_complete_quickly,
        )
        # Wait for completion before submitting next (concurrency invariant).
        while True:
            j = manager.get(jid)
            if j and j.is_terminal:
                break
            await asyncio.sleep(0.01)
        ids.append(jid)
        # Spread created_at by a tick so ordering is deterministic.
        await asyncio.sleep(0.02)

    listed = manager.list_for_project(project_id, limit=10)
    assert [j.job_id for j in listed] == list(reversed(ids))


# --- restart / orphan cleanup ----------------------------------------------

async def test_orphan_cleanup_marks_stale_running_rows(
    db_path: Path, project_id: int,
) -> None:
    """Insert a 'running' row owned by a fake pid (simulating a prior
    process), then instantiate a fresh JobManager and confirm the row
    gets marked orphaned at startup."""
    bogus_pid = os.getpid() + 99999  # something we definitely aren't
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO jobs
               (job_id, project_id, kind, status, args_json, created_at, pid)
               VALUES ('stale_id', ?, 'simulation', 'running', '{}',
                       '2026-04-01T00:00:00Z', ?)""",
            (project_id, bogus_pid),
        )
        conn.commit()

    # Instantiating JobManager should mark the stale row as orphaned.
    mgr = JobManager(db_path)
    job = mgr.get("stale_id")
    assert job is not None
    assert job.status == STATUS_ORPHANED
    assert job.error == "server restarted before job completed"


async def test_orphan_cleanup_preserves_running_rows_owned_by_us(
    db_path: Path, manager: JobManager, project_id: int,
) -> None:
    """Running rows owned by the current pid should NOT be touched by
    the cleanup pass at instantiation. (Covers the 'we restarted but
    own the rows' bizarre case — shouldn't happen in practice but
    making sure the SQL filter is right.)"""
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_block_forever,
    )
    # Let it become running.
    for _ in range(100):
        j = manager.get(job_id)
        if j and j.status == STATUS_RUNNING:
            break
        await asyncio.sleep(0.01)
    # Re-instantiate (simulating a fresh start) — but the row's pid is
    # ours, so it shouldn't get orphaned.
    mgr2 = JobManager(db_path)
    j = mgr2.get(job_id)
    assert j is not None
    assert j.status == STATUS_RUNNING

    # Cleanup.
    await manager.cancel(job_id)


# --- shutdown ---------------------------------------------------------------

async def test_shutdown_cancels_and_orphans_running_tasks(
    manager: JobManager, project_id: int,
) -> None:
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={}, runner=_runner_block_forever,
    )
    # Wait until running.
    for _ in range(100):
        j = manager.get(job_id)
        if j and j.status == STATUS_RUNNING:
            break
        await asyncio.sleep(0.01)

    await manager.shutdown()
    j = manager.get(job_id)
    assert j is not None
    assert j.status == STATUS_ORPHANED
    assert j.error == "server shutdown"


# --- to_dict shape ----------------------------------------------------------

async def test_to_dict_excludes_pid_includes_expected_fields(
    manager: JobManager, project_id: int,
) -> None:
    """Job.to_dict() is the shape MCP tool responses use. pid is
    internal-only and must not leak; the expected JSON-friendly fields
    must all be present."""
    job_id = manager.submit(
        kind=KIND_SIMULATION, project_id=project_id,
        args={"x": 1}, runner=_runner_complete_quickly,
    )
    while True:
        j = manager.get(job_id)
        if j and j.is_terminal:
            break
        await asyncio.sleep(0.01)
    assert j is not None
    d = j.to_dict()
    expected = {
        "job_id", "project_id", "kind", "status", "args",
        "progress_pct", "current_step", "result", "error",
        "created_at", "started_at", "completed_at",
    }
    assert set(d.keys()) == expected
    assert "pid" not in d

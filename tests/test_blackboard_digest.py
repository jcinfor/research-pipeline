"""Tests for `blackboard_digest.render_digest` (Roadmap 2.5)."""
from pathlib import Path

from research_pipeline.blackboard import (
    CONF_AMBIGUOUS,
    CONF_EXTRACTED,
    CONF_INFERRED,
    KIND_CRITIQUE,
    KIND_EVIDENCE,
    KIND_HYPOTHESIS,
    KIND_RESULT,
    add_entry,
)
from research_pipeline.blackboard_digest import render_digest
from research_pipeline.db import connect, init_db
from research_pipeline.projects import create_project, upsert_user


def _setup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="g",
            archetype_ids=["scout", "hypogen", "critic", "replicator"],
        )
    return db, pid


def test_digest_empty_blackboard(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        out = render_digest(conn, project_id=pid)
    assert "blackboard empty" in out
    assert "Project digest" in out


def test_digest_has_state_matrix_and_confidence_mix(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        # Mix of confidences + states
        add_entry(
            conn, project_id=pid, kind=KIND_EVIDENCE,
            content="paper X says Y", turn=0,
            confidence=CONF_EXTRACTED,
        )
        h1 = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="maybe Y", turn=0, confidence=CONF_INFERRED,
        )
        add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="probably not Z", turn=0, confidence=CONF_AMBIGUOUS,
        )
        # Bring h1 into supported state via direct SQL (lifecycle is exercised
        # in its own tests; here we just need the column populated)
        conn.execute(
            "UPDATE blackboard_entries SET state = 'supported' WHERE id = ?",
            (h1,),
        )
        conn.commit()
        out = render_digest(conn, project_id=pid)
    assert "Hypothesis state matrix" in out
    assert "supported=1" in out
    assert "proposed=1" in out
    assert "Confidence mix" in out
    assert "EXTRACTED=1" in out
    assert "INFERRED=1" in out
    assert "AMBIGUOUS=1" in out


def test_digest_top_hypotheses_by_inbound_refs(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        h1 = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="popular hypothesis", turn=0,
        )
        h2 = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="orphan hypothesis", turn=0,
        )
        # Two critiques + one result reference h1; nothing references h2
        for _ in range(2):
            add_entry(
                conn, project_id=pid, kind=KIND_CRITIQUE,
                content=f"Doubts about [hyp #{h1}]", turn=1,
            )
        add_entry(
            conn, project_id=pid, kind=KIND_RESULT,
            content=f"Replicated [hyp #{h1}] on test data", turn=1,
        )
        out = render_digest(conn, project_id=pid)
    # Both hypotheses listed; popular one shows ref count 3.
    assert f"#{h1}" in out
    assert "3 refs" in out
    # Orphan listed too with 0 refs
    assert f"#{h2}" in out
    assert "0 refs" in out


def test_digest_recent_results_listed(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        for i in range(3):
            add_entry(
                conn, project_id=pid, kind=KIND_RESULT,
                content=f"result number {i}", turn=i,
                confidence=CONF_EXTRACTED,
            )
        out = render_digest(conn, project_id=pid)
    assert "Recent" in out and "results" in out
    assert "result number 0" in out
    assert "result number 2" in out


def test_digest_open_disagreements_section_present_when_empty(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        # One hypothesis, no critiques
        add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="lonely hypothesis", turn=0,
        )
        out = render_digest(conn, project_id=pid)
    assert "Open disagreements" in out
    assert "no surviving refute critiques" in out

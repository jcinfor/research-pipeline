from pathlib import Path

import pytest

from research_pipeline.blackboard import (
    CONF_AMBIGUOUS,
    CONF_EXTRACTED,
    CONF_INFERRED,
    KIND_EVIDENCE,
    KIND_HYPOTHESIS,
    add_entry,
    list_entries,
    lowest_confidence,
    render_markdown,
)
from research_pipeline.db import connect, init_db
from research_pipeline.projects import create_project, upsert_user


def _setup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "test@rp")
        pid = create_project(conn, user_id=uid, goal="g", archetype_ids=["scout"])
    return db, pid


def test_add_and_list(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE, content="paper X says Y",
                  turn=1, agent_id=1, refs=["arxiv:1234.5678"])
        add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS, content="maybe Y implies Z",
                  turn=1, agent_id=1)
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE, content="more supporting data",
                  turn=2, agent_id=1)
        all_entries = list_entries(conn, pid)
        assert len(all_entries) == 3
        evidence_only = list_entries(conn, pid, kind=KIND_EVIDENCE)
        assert len(evidence_only) == 2
        md = render_markdown(conn, pid)
    assert "## evidence (2)" in md
    assert "## hypothesis (1)" in md
    assert "arxiv:1234.5678" in md


def test_unknown_kind_rejected(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        try:
            add_entry(conn, project_id=pid, kind="bogus", content="x", turn=1)
        except ValueError:
            return
    raise AssertionError("unknown kind should have raised")


# Roadmap 2.4 — confidence labels
# -------------------------------------------------------------------


def test_add_entry_default_confidence(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE, content="x", turn=1)
        entries = list_entries(conn, pid)
        assert len(entries) == 1
        assert entries[0].confidence == CONF_EXTRACTED


def test_add_entry_explicit_confidence(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="maybe Y", turn=1, confidence=CONF_INFERRED,
        )
        add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="probably not Z", turn=1, confidence=CONF_AMBIGUOUS,
        )
        entries = list_entries(conn, pid, kind=KIND_HYPOTHESIS)
        confs = sorted(e.confidence for e in entries)
        assert confs == [CONF_AMBIGUOUS, CONF_INFERRED]


def test_unknown_confidence_rejected(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        with pytest.raises(ValueError, match="confidence"):
            add_entry(
                conn, project_id=pid, kind=KIND_EVIDENCE,
                content="x", turn=1, confidence="MAYBE",
            )


def test_lowest_confidence_helper():
    # Empty cited set defaults to EXTRACTED — chain-of-reasoning over
    # zero sources is vacuously strong.
    assert lowest_confidence([]) == CONF_EXTRACTED
    assert lowest_confidence([CONF_EXTRACTED]) == CONF_EXTRACTED
    assert lowest_confidence([CONF_EXTRACTED, CONF_INFERRED]) == CONF_INFERRED
    assert lowest_confidence(
        [CONF_EXTRACTED, CONF_AMBIGUOUS, CONF_INFERRED]
    ) == CONF_AMBIGUOUS

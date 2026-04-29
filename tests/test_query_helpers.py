"""Tests for the structured query helpers used by writer/reviewer agents."""
from pathlib import Path

from research_pipeline.blackboard import (
    KIND_CRITIQUE, KIND_EVIDENCE, KIND_EXPERIMENT, KIND_HYPOTHESIS, KIND_RESULT,
    add_entry,
)
from research_pipeline.db import connect, init_db
from research_pipeline.lifecycle import resolve_hypothesis_refs
from research_pipeline.projects import create_project, upsert_user
from research_pipeline.query_helpers import (
    get_critiques_for, get_disagreements, get_experiments_for,
    get_hypothesis_arc, get_results_for, get_supporting_evidence,
)


def _setup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="test",
            archetype_ids=["scout", "hypogen", "experimenter", "critic", "replicator", "writer"],
        )
        agent_ids = [
            r["id"] for r in conn.execute(
                "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,)
            )
        ]
    scout, hypogen, experimenter, critic, replicator, writer = agent_ids
    return db, pid, scout, hypogen, experimenter, critic, replicator, writer


def test_get_critiques_for_targets_a_specific_hypothesis(tmp_path: Path):
    db, pid, scout, hypogen, _, critic, _, _ = _setup(tmp_path)
    with connect(db) as conn:
        h1 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="Claim A", turn=0, agent_id=hypogen)
        h2 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="Claim B", turn=0, agent_id=hypogen)
        # Critique targets h1 only
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"[hyp #{h1}] is unfounded.", turn=1, agent_id=critic)
        # Critique targets h2 only
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"[hyp #{h2}] is overstated.", turn=1, agent_id=critic)
        # Critique targets both
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"Both [hyp #{h1}] and [hyp #{h2}] need work.",
                  turn=1, agent_id=critic)

        crits_h1 = get_critiques_for(conn, project_id=pid, hypothesis_id=h1)
        crits_h2 = get_critiques_for(conn, project_id=pid, hypothesis_id=h2)
    assert len(crits_h1) == 2  # h1-only critique + the both-critique
    assert len(crits_h2) == 2


def test_get_results_and_experiments_for(tmp_path: Path):
    db, pid, _, hypogen, experimenter, _, replicator, _ = _setup(tmp_path)
    with connect(db) as conn:
        h1 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="P implies Q", turn=0, agent_id=hypogen)
        add_entry(conn, project_id=pid, kind=KIND_EXPERIMENT,
                  content=f"Test [hyp #{h1}] by inducing P.",
                  turn=1, agent_id=experimenter)
        add_entry(conn, project_id=pid, kind=KIND_RESULT,
                  content=f"Replication confirms [hyp #{h1}].",
                  turn=2, agent_id=replicator)

        exps = get_experiments_for(conn, project_id=pid, hypothesis_id=h1)
        results = get_results_for(conn, project_id=pid, hypothesis_id=h1)
    assert len(exps) == 1
    assert len(results) == 1


def test_get_supporting_evidence_via_results(tmp_path: Path):
    db, pid, scout, hypogen, _, _, replicator, _ = _setup(tmp_path)
    with connect(db) as conn:
        e1 = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                       content="data point A", turn=0, agent_id=scout)
        e2 = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                       content="data point B", turn=0, agent_id=scout)
        h1 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content=f"Claim grounded in [src #{e1}].",
                       turn=0, agent_id=hypogen)
        # Result confirms h1, citing e2 as backing evidence
        add_entry(conn, project_id=pid, kind=KIND_RESULT,
                  content=f"Replication confirms [hyp #{h1}] using [src #{e2}].",
                  turn=1, agent_id=replicator)
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)

        ev = get_supporting_evidence(conn, project_id=pid, hypothesis_id=h1)
    ev_ids = {e.id for e in ev}
    assert e1 in ev_ids  # direct ref from hypothesis
    assert e2 in ev_ids  # indirect via supporting result


def test_get_disagreements_finds_surviving_refutes(tmp_path: Path):
    db, pid, _, hypogen, _, critic, replicator, _ = _setup(tmp_path)
    with connect(db) as conn:
        # h1: refuted then confirmed (refute should NOT regress; this tests
        # the no-regress rule). Since terminal supported is reached first
        # in this flow, refute won't actually stick. We use a different
        # scenario:
        # h2: refute critique posted, then a confirming result also posted
        # in same turn — verdict ordering means terminal state may end at
        # 'supported'. The refute critique is still "surviving" in the sense
        # it raised a refute that didn't stick.
        h2 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="Survives critique", turn=0, agent_id=hypogen)
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"[hyp #{h2}] is refuted by my reading.",
                  turn=1, agent_id=critic)
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        # Now hypothesis is refuted. To make the disagreement detector fire
        # we need a case where state ENDS non-refuted but a refute critique
        # was logged. Use a fresh hypothesis with critique that doesn't
        # match refute keywords (left at proposed/under_test).
        h3 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="Disputed but unresolved", turn=0, agent_id=hypogen)
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"[hyp #{h3}] is contradicted by setup.",
                  turn=2, agent_id=critic)
        # Override with a stronger support
        add_entry(conn, project_id=pid, kind=KIND_RESULT,
                  content=f"Re-running confirms [hyp #{h3}] holds up.",
                  turn=3, agent_id=replicator)
        resolve_hypothesis_refs(conn, project_id=pid, turn=2)
        resolve_hypothesis_refs(conn, project_id=pid, turn=3)

        disagreements = get_disagreements(conn, project_id=pid)
    # h3 was refuted, then supported. The refute critique is in resolutions
    # but state ended supported -> it's a productive disagreement.
    disputed_ids = {d["hypothesis"].id for d in disagreements}
    assert h3 in disputed_ids


def test_get_hypothesis_arc_is_a_full_view(tmp_path: Path):
    db, pid, scout, hypogen, experimenter, critic, replicator, _ = _setup(tmp_path)
    with connect(db) as conn:
        e1 = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                       content="evidence chunk", turn=0, agent_id=scout)
        h1 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content=f"P based on [src #{e1}]",
                       turn=0, agent_id=hypogen)
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"[hyp #{h1}] needs more data",
                  turn=1, agent_id=critic)
        add_entry(conn, project_id=pid, kind=KIND_EXPERIMENT,
                  content=f"Test [hyp #{h1}] empirically",
                  turn=1, agent_id=experimenter)
        add_entry(conn, project_id=pid, kind=KIND_RESULT,
                  content=f"Replication confirms [hyp #{h1}]",
                  turn=2, agent_id=replicator)
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        resolve_hypothesis_refs(conn, project_id=pid, turn=2)

        arc = get_hypothesis_arc(conn, project_id=pid, hypothesis_id=h1)
    assert arc["hypothesis"].id == h1
    assert len(arc["critiques"]) == 1
    assert len(arc["results"]) == 1
    assert len(arc["experiments"]) == 1
    assert len(arc["supporting_evidence"]) >= 1
    assert len(arc["state_history"]) >= 1


def test_get_hypothesis_arc_for_nonexistent_returns_none(tmp_path: Path):
    db, pid, *_ = _setup(tmp_path)
    with connect(db) as conn:
        arc = get_hypothesis_arc(conn, project_id=pid, hypothesis_id=99999)
    assert arc["hypothesis"] is None

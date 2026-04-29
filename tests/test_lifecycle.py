from pathlib import Path

from research_pipeline.blackboard import (
    KIND_CRITIQUE, KIND_HYPOTHESIS, KIND_RESULT, add_entry, list_entries,
)
from research_pipeline.db import connect, init_db
from research_pipeline.lifecycle import (
    classify_verdict, extract_hypothesis_refs, get_state_history,
    hypotheses_in_play, resolve_hypothesis_refs,
)
from research_pipeline.projects import create_project, upsert_user


def test_classify_verdict_support():
    assert classify_verdict("My replication confirms the hypothesis.") == "support"
    assert classify_verdict("This result validates [hyp #7].") == "support"


def test_classify_verdict_refute():
    assert classify_verdict("The hypothesis is refuted by turn 2 data.") == "refute"
    assert classify_verdict("The assay does not replicate.") == "refute"
    assert classify_verdict("This claim is flawed.") == "refute"


def test_classify_verdict_neutral():
    assert classify_verdict("We are testing whether this holds.") == "neutral"
    # Both signals -> neutral (comparative text)
    assert classify_verdict("X confirms one part but refutes another.") == "neutral"


def test_extract_hypothesis_refs():
    assert extract_hypothesis_refs("See [hyp #3] and [HYP #7]") == [3, 7]
    assert extract_hypothesis_refs("no refs here") == []


def _setup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="test", archetype_ids=["hypogen", "replicator", "critic"],
        )
        hypogen_id, replicator_id, critic_id = [
            r["id"] for r in conn.execute(
                "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,)
            )
        ]
    return db, pid, hypogen_id, replicator_id, critic_id


def test_resolve_supports_hypothesis(tmp_path: Path):
    db, pid, hypogen_id, replicator_id, _ = _setup(tmp_path)
    with connect(db) as conn:
        hyp_id = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="X causes Y", turn=0, agent_id=hypogen_id,
        )
        add_entry(
            conn, project_id=pid, kind=KIND_RESULT,
            content=f"My replication confirms [hyp #{hyp_id}] holds up.",
            turn=1, agent_id=replicator_id,
        )
        counts = resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        hyp = list_entries(conn, pid, kind=KIND_HYPOTHESIS)[0]
    assert counts["support"] == 1
    assert hyp.state == "supported"
    assert len(hyp.resolutions) == 1
    assert hyp.resolutions[0]["verdict"] == "support"


def test_resolve_refutes_hypothesis(tmp_path: Path):
    db, pid, hypogen_id, _, critic_id = _setup(tmp_path)
    with connect(db) as conn:
        hyp_id = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="Z causes W", turn=0, agent_id=hypogen_id,
        )
        add_entry(
            conn, project_id=pid, kind=KIND_CRITIQUE,
            content=f"[hyp #{hyp_id}] is refuted by the assay variance.",
            turn=1, agent_id=critic_id,
        )
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        hyp = list_entries(conn, pid, kind=KIND_HYPOTHESIS)[0]
    assert hyp.state == "refuted"


def test_resolve_does_not_regress_terminal_state(tmp_path: Path):
    db, pid, hypogen_id, replicator_id, critic_id = _setup(tmp_path)
    with connect(db) as conn:
        hyp_id = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="A implies B", turn=0, agent_id=hypogen_id,
        )
        # First: supported
        add_entry(
            conn, project_id=pid, kind=KIND_RESULT,
            content=f"Replication confirms [hyp #{hyp_id}].",
            turn=1, agent_id=replicator_id,
        )
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        # Then: a neutral comment — must NOT flip it back to under_test
        add_entry(
            conn, project_id=pid, kind=KIND_CRITIQUE,
            content=f"Still looking at [hyp #{hyp_id}].",
            turn=2, agent_id=critic_id,
        )
        resolve_hypothesis_refs(conn, project_id=pid, turn=2)
        hyp = list_entries(conn, pid, kind=KIND_HYPOTHESIS)[0]
    assert hyp.state == "supported"


def test_resolutions_capture_prev_and_new_state(tmp_path: Path):
    """Each transition appends a resolution with prev_state and new_state."""
    db, pid, hypogen_id, replicator_id, critic_id = _setup(tmp_path)
    with connect(db) as conn:
        hyp_id = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="P implies Q", turn=0, agent_id=hypogen_id,
        )
        # Critic marks under_test (neutral with no prior support)
        add_entry(
            conn, project_id=pid, kind=KIND_CRITIQUE,
            content=f"[hyp #{hyp_id}] is unclear and we are testing it.",
            turn=1, agent_id=critic_id,
        )
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        # Replicator confirms — supported
        add_entry(
            conn, project_id=pid, kind=KIND_RESULT,
            content=f"Replication confirms [hyp #{hyp_id}].",
            turn=2, agent_id=replicator_id,
        )
        resolve_hypothesis_refs(conn, project_id=pid, turn=2)
        history = get_state_history(conn, project_id=pid, hypothesis_id=hyp_id)
    assert len(history) == 2
    assert history[0]["prev_state"] == "proposed"
    assert history[0]["new_state"] == "under_test"
    assert history[0]["turn"] == 1
    assert history[1]["prev_state"] == "under_test"
    assert history[1]["new_state"] == "supported"
    assert history[1]["turn"] == 2


def test_no_op_transitions_are_skipped(tmp_path: Path):
    """If two critiques in the same turn both classify as 'refute',
    only ONE transition row should be appended (proposed -> refuted),
    not two no-op refuted->refuted entries."""
    db, pid, hypogen_id, _, critic_id = _setup(tmp_path)
    with connect(db) as conn:
        hyp_id = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="Refutable claim", turn=0, agent_id=hypogen_id,
        )
        add_entry(
            conn, project_id=pid, kind=KIND_CRITIQUE,
            content=f"[hyp #{hyp_id}] is refuted by data A.",
            turn=1, agent_id=critic_id,
        )
        add_entry(
            conn, project_id=pid, kind=KIND_CRITIQUE,
            content=f"[hyp #{hyp_id}] is refuted by data B too.",
            turn=1, agent_id=critic_id,
        )
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        history = get_state_history(conn, project_id=pid, hypothesis_id=hyp_id)
    assert len(history) == 1  # second refute is a no-op transition
    assert history[0]["new_state"] == "refuted"


def test_get_state_history_for_unresolved_hypothesis(tmp_path: Path):
    db, pid, hypogen_id, *_ = _setup(tmp_path)
    with connect(db) as conn:
        hyp_id = add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="Untouched", turn=0, agent_id=hypogen_id,
        )
        history = get_state_history(conn, project_id=pid, hypothesis_id=hyp_id)
    assert history == []


def test_hypotheses_in_play_excludes_terminal(tmp_path: Path):
    db, pid, hypogen_id, replicator_id, critic_id = _setup(tmp_path)
    with connect(db) as conn:
        h1 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="open hypo", turn=0, agent_id=hypogen_id)
        h2 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="will be supported", turn=0, agent_id=hypogen_id)
        h3 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="will be refuted", turn=0, agent_id=hypogen_id)
        add_entry(conn, project_id=pid, kind=KIND_RESULT,
                  content=f"Replication confirms [hyp #{h2}]",
                  turn=1, agent_id=replicator_id)
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"[hyp #{h3}] is refuted",
                  turn=1, agent_id=critic_id)
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
        in_play = hypotheses_in_play(conn, project_id=pid)
    in_play_ids = [i for i, _, _ in in_play]
    assert h1 in in_play_ids
    assert h2 not in in_play_ids  # supported -> terminal
    assert h3 not in in_play_ids  # refuted -> terminal

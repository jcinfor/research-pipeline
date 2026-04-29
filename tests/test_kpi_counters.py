from pathlib import Path

from research_pipeline.blackboard import (
    KIND_EVIDENCE,
    KIND_HYPOTHESIS,
    add_entry,
)
from research_pipeline.db import connect, init_db
from research_pipeline.kpi import (
    M_COVERAGE,
    M_EVIDENCE_DENSITY,
    M_EVIDENCE_FILED,
    M_HYPOTHESES_GENERATED,
    M_POSTS_PUBLISHED,
    latest_snapshot,
    snapshot_counters,
)
from research_pipeline.projects import create_project, upsert_user


def test_counters_count_correctly(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="g",
                             archetype_ids=["scout", "hypogen"])

        # Two posts by agent 1, one by agent 2
        conn.execute(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, 'twitter', 1, 'a', 1), (?, 'twitter', 1, 'b', 1), "
            "(?, 'twitter', 2, 'c', 1)",
            (pid, pid, pid),
        )
        # 2 evidence, 1 hypothesis
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE, content="e1", turn=1, agent_id=1)
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE, content="e2", turn=1, agent_id=2)
        add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS, content="h1", turn=1, agent_id=2)

        rows = snapshot_counters(conn, project_id=pid, turn=1)
        by = {(r.agent_id, r.metric): r.value for r in rows}
        assert by[(1, M_POSTS_PUBLISHED)] == 2
        assert by[(2, M_POSTS_PUBLISHED)] == 1
        assert by[(1, M_EVIDENCE_FILED)] == 1
        assert by[(2, M_EVIDENCE_FILED)] == 1
        assert by[(2, M_HYPOTHESES_GENERATED)] == 1
        assert by[(None, M_EVIDENCE_DENSITY)] == 2.0  # 2 evidence / 1 hypothesis
        assert by[(None, M_COVERAGE)] == 2            # agents 1 and 2

        snap = latest_snapshot(conn, project_id=pid, metrics=[M_COVERAGE])
        assert snap[0]["value"] == 2

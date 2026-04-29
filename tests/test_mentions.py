from pathlib import Path

from research_pipeline.db import connect, init_db
from research_pipeline.mentions import link_mentions
from research_pipeline.projects import create_project, upsert_user


def test_link_mentions(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="g", archetype_ids=["scout", "hypogen", "critic"]
        )
        scout_id, hypogen_id, critic_id = [
            r["id"] for r in conn.execute(
                "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,)
            )
        ]
        # Turn 0: scout posts, then hypogen posts, then critic posts referencing both.
        conn.executemany(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, 'twitter', ?, ?, 0)",
            [
                (pid, scout_id, "Kozlowski et al. 2022 says X"),
                (pid, hypogen_id, "Hypothesis Y"),
                (pid, critic_id, "@agent_1 your claim ignores the assay specificity"),
                (pid, scout_id, "Replying to [t0 agent_2]: let me cite Z"),
                (pid, hypogen_id, "self-ref agent_2 should not link"),
            ],
        )
        conn.commit()
        n = link_mentions(conn, project_id=pid, turn=0)
        assert n == 2

        rows = list(
            conn.execute(
                "SELECT content, agent_id, parent_id FROM channel_posts "
                "WHERE project_id=? ORDER BY id",
                (pid,),
            )
        )
        # Rows: [scout first, hypogen first, critic ref scout_1, scout ref hypogen_2, hypogen self-ref]
        assert rows[0]["parent_id"] is None
        assert rows[1]["parent_id"] is None
        assert rows[2]["parent_id"] == 1  # critic -> scout's first post
        assert rows[3]["parent_id"] == 2  # scout -> hypogen's first post
        assert rows[4]["parent_id"] is None  # self-ref doesn't link

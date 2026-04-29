from pathlib import Path

from research_pipeline.blackboard import (
    CONF_EXTRACTED,
    CONF_INFERRED,
    KIND_EVIDENCE,
    KIND_HYPOTHESIS,
    KIND_RESULT,
    list_entries,
)
from research_pipeline.db import connect, init_db
from research_pipeline.projects import create_project, upsert_user
from research_pipeline.promote import (
    confidence_for, extract_refs, promote_project_posts,
)


def test_extract_refs():
    text = (
        "Per Kozlowski et al. in Nature 2022 and Smith et al. 2019, "
        "see doi:10.1038/s41586-022-05123-4 and arxiv: 2403.12345."
    )
    refs = extract_refs(text)
    assert any(r.startswith("10.1038") for r in refs)
    assert any("Kozlowski" in r for r in refs)
    assert "2022" in refs
    assert any("2403.12345" in r for r in refs)


def test_promote_maps_archetype_to_kind(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="g", archetype_ids=["scout", "hypogen"]
        )
        # Look up concrete agent ids for this project
        scout_id, hypogen_id = [
            r["id"] for r in conn.execute(
                "SELECT id FROM agents WHERE project_id = ? ORDER BY id", (pid,)
            )
        ]

        conn.executemany(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, 'twitter', ?, ?, 0)",
            [
                (pid, scout_id, "Kozlowski et al. 2022 says non-covalent binding works."),
                (pid, hypogen_id, "Hypothesis: target the allosteric pocket via PROTACs."),
            ],
        )
        conn.commit()

        res = promote_project_posts(conn, project_id=pid, turn=0)
        assert res == {"added": 2, "echoed": 0, "skipped": 0}

        ev = list_entries(conn, pid, kind=KIND_EVIDENCE)
        hy = list_entries(conn, pid, kind=KIND_HYPOTHESIS)
        assert len(ev) == 1 and len(hy) == 1
        assert "Kozlowski" in ev[0].refs[0] or "2022" in ev[0].refs
        # Second call is idempotent: exact content already present -> skipped
        res2 = promote_project_posts(conn, project_id=pid, turn=0)
        assert res2 == {"added": 0, "echoed": 0, "skipped": 2}


# Roadmap 2.4 — per-archetype confidence defaults
# -------------------------------------------------------------------


def test_confidence_for_static_archetypes():
    """Most archetypes have a fixed default that doesn't depend on refs."""
    assert confidence_for("scout", []) == CONF_EXTRACTED
    assert confidence_for("scout", ["arxiv:2403.12345"]) == CONF_EXTRACTED
    assert confidence_for("hypogen", []) == CONF_INFERRED
    assert confidence_for("critic", ["10.1038/x"]) == CONF_INFERRED
    assert confidence_for("writer", []) == CONF_INFERRED
    assert confidence_for("reviewer", []) == CONF_INFERRED
    # Unknown archetype falls back to INFERRED (safer default than EXTRACTED).
    assert confidence_for("unknown_archetype", []) == CONF_INFERRED


def test_confidence_for_replicator_with_strong_citation():
    """Replicator's default depends on whether the post cites a real source."""
    assert confidence_for("replicator", []) == CONF_INFERRED
    assert confidence_for("replicator", ["2022"]) == CONF_INFERRED  # bare year only
    assert confidence_for("replicator", ["10.1038/s41586-022"]) == CONF_EXTRACTED
    assert confidence_for("replicator", ["arxiv: 2403.12345"]) == CONF_EXTRACTED
    assert confidence_for("replicator", ["Smith et al."]) == CONF_EXTRACTED


def test_promote_assigns_correct_confidence(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="g",
            archetype_ids=["scout", "hypogen", "replicator"],
        )
        scout_id, hypogen_id, replicator_id = [
            r["id"] for r in conn.execute(
                "SELECT id FROM agents WHERE project_id = ? ORDER BY id", (pid,)
            )
        ]
        conn.executemany(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, 'twitter', ?, ?, 0)",
            [
                # scout always EXTRACTED
                (pid, scout_id, "Kozlowski et al. 2022 say binding works."),
                # hypogen always INFERRED
                (pid, hypogen_id, "Hypothesis: target the allosteric pocket."),
                # replicator with no strong citation → INFERRED
                (pid, replicator_id, "Replicated successfully on test data."),
            ],
        )
        conn.commit()
        promote_project_posts(conn, project_id=pid, turn=0)

        ev = list_entries(conn, pid, kind=KIND_EVIDENCE)
        hy = list_entries(conn, pid, kind=KIND_HYPOTHESIS)
        rs = list_entries(conn, pid, kind=KIND_RESULT)
        assert ev[0].confidence == CONF_EXTRACTED
        assert hy[0].confidence == CONF_INFERRED
        # No DOI/arxiv/author-et-al → INFERRED
        assert rs[0].confidence == CONF_INFERRED

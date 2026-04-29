from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, KIND_HYPOTHESIS, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.projects import create_project, upsert_user
from research_pipeline.report import _format_artifacts, _gather_artifacts


def test_gather_and_format(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="test goal for KRAS", archetype_ids=["scout", "hypogen"]
        )
        agents = list(
            conn.execute("SELECT id FROM agents WHERE project_id = ?", (pid,))
        )
        add_entry(
            conn, project_id=pid, kind=KIND_EVIDENCE,
            content="Soni et al. 2022 demonstrates non-covalent binding",
            turn=0, agent_id=agents[0]["id"], refs=["Soni et al.", "2022"],
        )
        add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="Targeting SOS1 interface may bypass covalent dependency",
            turn=1, agent_id=agents[1]["id"],
        )
        ctx = _gather_artifacts(conn, pid)

    assert ctx["project"].goal == "test goal for KRAS"
    assert len(ctx["agents"]) == 2
    assert len(ctx["kinds"][KIND_EVIDENCE]) == 1
    assert len(ctx["kinds"][KIND_HYPOTHESIS]) == 1

    text = _format_artifacts(ctx)
    assert "GOAL: test goal for KRAS" in text
    assert "EVIDENCE" in text
    assert "HYPOTHESIS" in text
    assert "Soni et al." in text
    assert "2022" in text

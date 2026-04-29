import json
import zipfile
from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.export import export_project
from research_pipeline.projects import create_project, upsert_user


def test_export_zip_contains_summary_and_blackboard(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="export test goal",
            archetype_ids=["scout", "hypogen"],
        )
        agents = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM agents WHERE project_id=?", (pid,)
            )
        ]
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                  content="Soni et al. 2022", turn=0,
                  agent_id=agents[0], refs=["Soni et al.", "2022"])
        # Fake a rubric snapshot
        conn.execute(
            "INSERT INTO kpi_scores (project_id, agent_id, metric, value, turn) "
            "VALUES (?, NULL, 'novelty', 4.0, 1)",
            (pid,),
        )
        conn.commit()

        # Seed a raw/ file to confirm the exporter includes project assets
        project_dir = tmp_path / "projects"
        (project_dir / f"project_{pid}" / "raw").mkdir(parents=True, exist_ok=True)
        raw_file = project_dir / f"project_{pid}" / "raw" / "paper.md"
        raw_file.write_text("# Sample paper\n\nContent.", encoding="utf-8")

        out = export_project(
            conn, project_id=pid,
            out_path=tmp_path / f"project_{pid}.zip",
            project_dir=project_dir, runs_dir=tmp_path / "runs",
        )

    assert out.exists() and out.stat().st_size > 0
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        assert "summary.json" in names
        assert "blackboard.md" in names
        assert f"project_{pid}/raw/paper.md" in names

        with z.open("summary.json") as f:
            meta = json.loads(f.read().decode("utf-8"))
        assert meta["project_id"] == pid
        assert meta["goal"] == "export test goal"
        assert "novelty" in meta["kpi_latest_rubric"]
        assert meta["kpi_latest_rubric"]["novelty"] == 4.0
        assert "evidence" in meta["blackboard_kind_counts"]

        with z.open("blackboard.md") as f:
            bb = f.read().decode("utf-8")
        assert "Soni et al." in bb

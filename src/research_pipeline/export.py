"""Bundle a project's artifacts into a shareable zip.

Contents:
    summary.json              metadata, agent list, KPI trajectory, counts
    blackboard.md             rendered blackboard
    project_{id}/raw/...      ingested sources (MarkItDown output)
    project_{id}/report.md    writer+reviewer synthesis
    project_{id}/kg/...       Graphify outputs (if generated)
    runs/project_{id}_oasis.db  OASIS state (if preserved)
"""
from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from .blackboard import render_markdown
from .kpi import PROJECT_COUNTERS, RUBRIC_METRICS
from .projects import get_project, get_project_agents


def export_project(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    out_path: Path | None = None,
    project_dir: Path = Path("./projects"),
    runs_dir: Path = Path("./runs"),
) -> Path:
    """Zip the project's artifacts. Returns the output path."""
    project = get_project(conn, project_id)
    agents = get_project_agents(conn, project_id)

    if out_path is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = Path("exports") / f"project_{project_id}_{stamp}.zip"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "project_id": project.id,
        "goal": project.goal,
        "focus": project.focus,
        "status": project.status,
        "agents": [
            {"id": a.id, "archetype": a.archetype, "weight": a.weight}
            for a in agents
        ],
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "kpi_trajectory": _kpi_trajectory(conn, project_id),
        "kpi_latest_rubric": _latest_values(conn, project_id, RUBRIC_METRICS),
        "kpi_latest_counters": _latest_values(conn, project_id, PROJECT_COUNTERS),
        "post_counts": dict(
            conn.execute(
                "SELECT channel, COUNT(*) FROM channel_posts "
                "WHERE project_id = ? GROUP BY channel",
                (project_id,),
            ).fetchall()
        ),
        "blackboard_kind_counts": dict(
            conn.execute(
                "SELECT kind, COUNT(*) FROM blackboard_entries "
                "WHERE project_id = ? GROUP BY kind",
                (project_id,),
            ).fetchall()
        ),
    }

    blackboard_md = render_markdown(conn, project_id)
    assets_dir = project_dir / f"project_{project_id}"
    oasis_db = runs_dir / f"project_{project_id}_oasis.db"

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "summary.json", json.dumps(summary, indent=2, default=str)
        )
        z.writestr("blackboard.md", blackboard_md)
        if assets_dir.exists():
            for f in assets_dir.rglob("*"):
                if f.is_file():
                    # Store as project_{id}/... inside the zip
                    arcname = f.relative_to(project_dir)
                    z.write(f, arcname=str(arcname).replace("\\", "/"))
        if oasis_db.exists():
            z.write(oasis_db, arcname=f"runs/{oasis_db.name}")

    return out_path


def _kpi_trajectory(conn: sqlite3.Connection, project_id: int) -> dict[str, list]:
    metrics = RUBRIC_METRICS + PROJECT_COUNTERS
    placeholders = ",".join("?" * len(metrics))
    rows = conn.execute(
        f"SELECT turn, metric, value FROM kpi_scores "
        f"WHERE project_id = ? AND agent_id IS NULL AND metric IN ({placeholders}) "
        f"ORDER BY turn, metric",
        (project_id, *metrics),
    ).fetchall()
    series: dict[str, list] = {}
    for r in rows:
        series.setdefault(r["metric"], []).append(
            {"turn": int(r["turn"]), "value": float(r["value"])}
        )
    return series


def _latest_values(
    conn: sqlite3.Connection, project_id: int, metrics: tuple[str, ...]
) -> dict[str, float]:
    placeholders = ",".join("?" * len(metrics))
    rows = conn.execute(
        f"""
        SELECT metric, value FROM kpi_scores
        WHERE project_id = ? AND agent_id IS NULL AND metric IN ({placeholders})
        AND turn = (
            SELECT MAX(turn) FROM kpi_scores
            WHERE project_id = ? AND agent_id IS NULL AND metric = kpi_scores.metric
        )
        """,
        (project_id, *metrics, project_id),
    ).fetchall()
    return {r["metric"]: float(r["value"]) for r in rows}

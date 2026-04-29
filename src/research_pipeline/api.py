"""FastAPI app for the research-pipeline dashboard.

Routes:
    GET /                              HTML dashboard (single-page)
    GET /health                        status + resolved config
    GET /api/archetypes                archetype roster
    GET /api/projects                  list projects
    GET /api/projects/{pid}            project detail
    GET /api/projects/{pid}/agents     agents in the project
    GET /api/projects/{pid}/posts      channel posts (paginated)
    GET /api/projects/{pid}/blackboard blackboard entries (grouped by kind)
    GET /api/projects/{pid}/kpi        latest rubric scores
    GET /api/projects/{pid}/stream     SSE stream of new posts (polls DB)
    POST /api/projects/{pid}/pi-post   inject a PI-actor post

DB path comes from $RP_DB_PATH (default: ./research_pipeline.db).
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from .archetypes import ROSTER
from .blackboard import list_entries
from .config import load_config
from .db import connect, init_db
from .kpi import PGR_METRICS, PROJECT_COUNTERS, RUBRIC_METRICS
from .projects import (
    create_project,
    get_channel_posts,
    get_project,
    get_project_agents,
    list_projects,
    upsert_user,
)


def _db_path() -> Path:
    return Path(os.environ.get("RP_DB_PATH", "research_pipeline.db"))


app = FastAPI(title="research-pipeline", version="0.0.1")


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


class Health(BaseModel):
    status: str
    config_source: str
    roles: list[str]
    db_path: str


@app.get("/health", response_model=Health)
def health() -> Health:
    cfg = load_config()
    return Health(
        status="ok",
        config_source=str(cfg.source),
        roles=sorted(cfg.roles),
        db_path=str(_db_path().resolve()),
    )


@app.get("/api/archetypes")
def api_archetypes() -> list[dict]:
    return [
        {
            "id": a.id,
            "name": a.name,
            "role_hint": a.role_hint,
            "twitter_posts_per_turn": a.twitter_posts_per_turn,
            "reddit_posts_per_turn": a.reddit_posts_per_turn,
        }
        for a in ROSTER
    ]


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@app.get("/api/projects")
def api_projects() -> list[dict]:
    init_db(_db_path())
    with connect(_db_path()) as conn:
        return [
            {"id": p.id, "user_id": p.user_id, "goal": p.goal, "status": p.status}
            for p in list_projects(conn)
        ]


@app.get("/api/projects/{pid}")
def api_project(pid: int) -> dict:
    init_db(_db_path())
    with connect(_db_path()) as conn:
        try:
            p = get_project(conn, pid)
        except LookupError:
            raise HTTPException(404)
        agents = get_project_agents(conn, pid)
    return {
        "id": p.id,
        "user_id": p.user_id,
        "goal": p.goal,
        "focus": p.focus,
        "status": p.status,
        "agents": [
            {"id": a.id, "archetype": a.archetype, "weight": a.weight}
            for a in agents
        ],
    }


@app.get("/api/projects/{pid}/agents")
def api_project_agents(pid: int) -> list[dict]:
    init_db(_db_path())
    with connect(_db_path()) as conn:
        return [
            {
                "id": a.id,
                "archetype": a.archetype,
                "weight": a.weight,
                "temperature": a.temperature,
                "max_tokens": a.max_tokens,
                "specialty_focus": a.specialty_focus,
                "token_budget": a.token_budget,
            }
            for a in get_project_agents(conn, pid)
        ]


@app.get("/api/projects/{pid}/pgr-config")
def api_get_pgr_config(pid: int) -> dict:
    """Return current pgr_config + the recommender's proposal so the
    dashboard can show both 'what's active' and 'what we'd recommend'."""
    from .pgr_planner import plan_to_config, recommend_pgr_plan
    from .projects import get_project

    init_db(_db_path())
    with connect(_db_path()) as conn:
        try:
            project = get_project(conn, pid)
        except LookupError:
            raise HTTPException(404)
        plan = recommend_pgr_plan(conn, pid)
    return {
        "current": project.pgr_config or {},
        "recommended": plan_to_config(plan),
        "recommendation": [
            {
                "id": p.id,
                "name": p.name,
                "enabled": p.enabled,
                "weight": p.weight,
                "rationale": p.rationale,
                "requirements_met": p.requirements_met,
            }
            for p in plan.proxies
        ],
        "notes": plan.notes,
    }


class PGRConfigBody(BaseModel):
    proxies: dict


@app.put("/api/projects/{pid}/pgr-config")
def api_put_pgr_config(pid: int, body: PGRConfigBody) -> dict:
    """Persist a user-edited PGR config. Body shape:
    {"proxies": {"pgr_cite": {"weight": 0.5, "enabled": true}, ...}}"""
    from .projects import update_pgr_config

    init_db(_db_path())
    config = {"proxies": body.proxies or {}}
    with connect(_db_path()) as conn:
        update_pgr_config(conn, project_id=pid, config=config)
    return {"ok": True, "saved": config}


@app.get("/api/projects/{pid}/kpi/per-agent")
def api_project_kpi_per_agent(pid: int) -> dict[str, dict[str, float]]:
    """Latest per-agent rubric scores. Shape: {agent_id: {metric: value}}."""
    from .per_agent_rubric import latest_per_agent_scores

    init_db(_db_path())
    with connect(_db_path()) as conn:
        scores = latest_per_agent_scores(conn, project_id=pid)
    return {str(aid): metrics for aid, metrics in scores.items()}


@app.get("/api/projects/{pid}/posts")
def api_project_posts(pid: int, channel: str = "twitter", limit: int = 500) -> list[dict]:
    init_db(_db_path())
    with connect(_db_path()) as conn:
        rows = conn.execute(
            "SELECT id, turn, agent_id, parent_id, title, content, created_at "
            "FROM channel_posts WHERE project_id = ? AND channel = ? "
            "ORDER BY id LIMIT ?",
            (pid, channel, limit),
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/projects/{pid}/blackboard")
def api_project_blackboard(pid: int) -> list[dict]:
    init_db(_db_path())
    with connect(_db_path()) as conn:
        entries = list_entries(conn, pid)
    return [
        {
            "id": e.id,
            "agent_id": e.agent_id,
            "kind": e.kind,
            "content": e.content,
            "refs": e.refs,
            "turn": e.turn,
            "echo_count": e.echo_count,
            "echo_refs": list(e.echo_refs),
            "state": e.state,
            "resolutions": list(e.resolutions),
        }
        for e in entries
    ]


@app.get("/api/projects/{pid}/kpi/trajectory")
def api_project_kpi_trajectory(pid: int) -> dict[str, dict]:
    """Per-turn project-level KPI timeseries, split by category."""
    metrics = RUBRIC_METRICS + PROJECT_COUNTERS + PGR_METRICS
    init_db(_db_path())
    with connect(_db_path()) as conn:
        placeholders = ",".join("?" * len(metrics))
        rows = conn.execute(
            f"SELECT turn, metric, value FROM kpi_scores "
            f"WHERE project_id = ? AND agent_id IS NULL AND metric IN ({placeholders}) "
            f"ORDER BY turn, metric",
            (pid, *metrics),
        ).fetchall()
    series: dict[str, list[dict[str, float]]] = {}
    for r in rows:
        series.setdefault(r["metric"], []).append(
            {"turn": int(r["turn"]), "value": float(r["value"])}
        )
    return {
        "rubric": {m: series[m] for m in RUBRIC_METRICS if m in series},
        "counters": {m: series[m] for m in PROJECT_COUNTERS if m in series},
        "pgr": {m: series[m] for m in PGR_METRICS if m in series},
    }


@app.get("/api/projects/{pid}/kpi")
def api_project_kpi(pid: int) -> dict[str, dict[str, float]]:
    """Latest project-level values, split by category.

    Shape: {"rubric": {metric: value}, "counters": {metric: value}}
    Rubric metrics live on a 1-5 scale (LLM-judged). Counters are raw scalars.
    """
    metrics = RUBRIC_METRICS + PROJECT_COUNTERS
    init_db(_db_path())
    with connect(_db_path()) as conn:
        placeholders = ",".join("?" * len(metrics))
        rows = conn.execute(
            f"""
            SELECT metric, value FROM kpi_scores
            WHERE project_id = ? AND agent_id IS NULL
              AND metric IN ({placeholders})
              AND turn = (
                SELECT MAX(turn) FROM kpi_scores
                WHERE project_id = ? AND agent_id IS NULL
                  AND metric = kpi_scores.metric
              )
            """,
            (pid, *metrics, pid),
        ).fetchall()
    flat = {r["metric"]: float(r["value"]) for r in rows}
    return {
        "rubric": {m: flat[m] for m in RUBRIC_METRICS if m in flat},
        "counters": {m: flat[m] for m in PROJECT_COUNTERS if m in flat},
    }


class PIPostBody(BaseModel):
    message: str
    channel: str = "twitter"


@app.post("/api/projects/{pid}/pi-post")
def api_project_pi_post(pid: int, body: PIPostBody) -> dict:
    init_db(_db_path())
    with connect(_db_path()) as conn:
        next_turn = conn.execute(
            "SELECT COALESCE(MAX(turn), -1) + 1 AS t FROM channel_posts WHERE project_id = ?",
            (pid,),
        ).fetchone()["t"]
        cur = conn.execute(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, ?, NULL, ?, ?)",
            (pid, body.channel, body.message, next_turn),
        )
        conn.commit()
    return {"id": cur.lastrowid, "turn": next_turn}


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


async def _stream_posts(pid: int, channel: str = "twitter") -> AsyncIterator[str]:
    last_id = 0
    while True:
        try:
            with connect(_db_path()) as conn:
                rows = conn.execute(
                    "SELECT id, turn, agent_id, parent_id, title, content, created_at "
                    "FROM channel_posts WHERE project_id = ? AND channel = ? AND id > ? "
                    "ORDER BY id",
                    (pid, channel, last_id),
                ).fetchall()
            for r in rows:
                last_id = r["id"]
                yield f"data: {json.dumps(dict(r))}\n\n"
        except sqlite3.OperationalError:
            pass  # DB briefly locked during a sim turn commit — just retry
        await asyncio.sleep(1.0)


@app.get("/api/projects/{pid}/stream")
async def api_project_stream(pid: int, channel: str = "twitter") -> StreamingResponse:
    return StreamingResponse(
        _stream_posts(pid, channel=channel),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Dashboard (single-page HTML)
# ---------------------------------------------------------------------------


DASHBOARD_HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>research-pipeline</title>
<style>
  :root {
    /* Typography scale — minor third (1.2x) starting from 13px base */
    --text-xs: 11px; --text-sm: 12px; --text-base: 13px;
    --text-md: 14px; --text-lg: 16px; --text-xl: 19px;
    /* 4pt spacing grid */
    --s-1: 4px; --s-2: 8px; --s-3: 12px; --s-4: 16px;
    --s-5: 20px; --s-6: 24px;
    /* Color — neutral grays + single accent */
    --fg: #111827; --muted: #6b7280; --subtle: #9ca3af;
    --bg: #ffffff; --panel: #f9fafb; --border: #e5e7eb;
    --accent: #2563eb; --accent-soft: rgba(37, 99, 235, 0.08);
    --success: #059669; --warning: #d97706; --danger: #dc2626;
    --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04);
  }
  * { box-sizing: border-box; }
  body {
    font-family: "Inter", -apple-system, system-ui, "Segoe UI", sans-serif;
    font-feature-settings: "cv11", "ss01", "ss03";
    max-width: 1320px; margin: var(--s-4) auto; padding: 0 var(--s-5);
    color: var(--fg); line-height: 1.5; font-size: var(--text-base);
    background: #fafafa;
  }
  header {
    display: flex; align-items: center; gap: var(--s-4);
    margin-bottom: var(--s-3); flex-wrap: wrap;
    padding: var(--s-3) var(--s-4); background: var(--bg);
    border: 1px solid var(--border); border-radius: 8px;
    box-shadow: var(--shadow-sm);
  }
  header h1 { font-size: var(--text-xl); margin: 0; font-weight: 600; letter-spacing: -0.01em; }
  header .muted { color: var(--muted); font-size: var(--text-sm); }
  /* Connection status dot */
  .status-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: var(--subtle); margin-right: var(--s-2); vertical-align: middle;
    transition: background 0.2s ease;
  }
  .status-dot.connected { background: var(--success); box-shadow: 0 0 0 3px rgba(5, 150, 105, 0.15); }
  .status-dot.streaming { background: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
  .status-dot.error { background: var(--danger); }
  @keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }
    50% { box-shadow: 0 0 0 6px rgba(37, 99, 235, 0); }
  }
  select, button, input[type=text] {
    font-family: inherit; font-size: var(--text-md);
    padding: 6px 10px; border: 1px solid var(--border);
    border-radius: 6px; background: #fff; color: var(--fg);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  select:focus, input[type=text]:focus, button:focus-visible {
    outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }
  button { cursor: pointer; }
  button:hover:not(:disabled) { border-color: var(--subtle); }
  button.primary {
    background: var(--accent); color: white; border-color: var(--accent);
  }
  button.primary:hover { background: #1d4ed8; border-color: #1d4ed8; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  main { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr) 340px; gap: var(--s-3); align-items: start; }
  section.panel {
    border: 1px solid var(--border); border-radius: 8px;
    background: var(--bg); padding: var(--s-3) var(--s-4);
    box-shadow: var(--shadow-sm);
  }
  section.panel h2 {
    font-size: var(--text-xs); text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--muted); font-weight: 600;
    margin: 0 0 var(--s-3); display: flex;
    justify-content: space-between; align-items: baseline;
  }
  section.panel h2 .count { font-size: 12px; color: var(--muted); text-transform: none; letter-spacing: 0; }
  .feed, .board { max-height: 78vh; overflow-y: auto; padding-right: 4px; }
  .post {
    padding: 10px 6px 10px 12px;
    margin-bottom: 2px;
    border-left: 3px solid transparent;
    border-bottom: 1px solid var(--border);
    transition: background-color 0.15s ease;
    border-radius: 0 4px 4px 0;
  }
  .post:last-child { border-bottom: none; }
  .post:hover { background: rgba(15, 23, 42, 0.02); }
  .post .meta {
    font-size: var(--text-xs); color: var(--muted);
    margin-bottom: var(--s-1);
    display: flex; align-items: baseline; gap: var(--s-2);
  }
  .post .who {
    font-weight: 600; color: var(--fg);
    font-size: var(--text-sm); letter-spacing: 0.01em;
  }
  .post .post-id { font-family: "SF Mono", Menlo, monospace; color: var(--subtle); }
  .post .reply { font-style: italic; }
  .post.pi {
    background: #fff8d6; border-left-color: #e0a800;
    padding: 10px 6px 10px 14px; margin: 6px 0;
    border-radius: 4px;
  }
  .post .content {
    white-space: pre-wrap; word-break: break-word;
    font-size: var(--text-base); line-height: 1.55;
  }
  .channel-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
  .channel-tabs button { padding: 4px 12px; border: 1px solid var(--border); background: var(--bg); border-radius: 4px; cursor: pointer; font-size: 13px; }
  .channel-tabs button.active { background: var(--accent); color: white; border-color: var(--accent); }
  .reddit-thread { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; background: var(--panel); }
  .reddit-root h3 { margin: 0 0 6px; font-size: 15px; line-height: 1.3; }
  .reddit-root .meta, .reddit-reply .meta { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  .reddit-root .content, .reddit-reply .content { white-space: pre-wrap; word-break: break-word; font-size: 14px; }
  .reddit-replies { margin-top: 10px; padding-left: 14px; border-left: 3px solid var(--border); }
  .reddit-reply { padding: 6px 0; border-bottom: 1px dotted var(--border); }
  .reddit-reply:last-child { border-bottom: none; }
  .reddit-reply-count { font-size: 12px; color: var(--muted); margin-top: 6px; }
  .kpi-row { display: flex; justify-content: space-between; font-family: "SF Mono", Menlo, monospace; font-size: 13px; padding: 2px 0; }
  .kpi-bar { height: 6px; background: var(--panel); border-radius: 3px; overflow: hidden; margin: 2px 0 8px; }
  .kpi-fill { height: 100%; background: var(--accent); transition: width .3s ease; }
  .bb-group h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin: 14px 0 6px; padding-bottom: 3px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; }
  .bb-group:first-child h3 { margin-top: 0; }
  .bb-entry {
    padding: 8px 6px; border-bottom: 1px solid var(--border);
    border-radius: 4px; transition: background-color 0.15s ease;
  }
  .bb-entry:last-child { border-bottom: none; }
  .bb-entry:hover { background: rgba(15, 23, 42, 0.02); }
  .bb-entry .meta { font-size: var(--text-xs); color: var(--muted); margin-bottom: 3px; }
  .bb-entry .content {
    white-space: pre-wrap; word-break: break-word;
    font-size: var(--text-base); line-height: 1.55;
    max-height: 240px; overflow-y: auto;
    /* fade-out indicator only when content overflows */
    mask-image: linear-gradient(to bottom, black calc(100% - 24px), transparent);
    -webkit-mask-image: linear-gradient(to bottom, black calc(100% - 24px), transparent);
  }
  .bb-entry .content:hover {
    /* clear the fade-mask on hover so the user can read the full tail */
    mask-image: none; -webkit-mask-image: none;
  }
  .bb-entry .refs { margin-top: 3px; font-size: 11px; color: var(--accent); }
  .bb-entry .refs code { background: var(--panel); padding: 1px 4px; border-radius: 3px; margin-right: 4px; }
  .bb-entry .echoes { margin-top: 4px; font-size: 11px; color: var(--muted); }
  .bb-entry .echo-badge { display: inline-block; background: #e0a800; color: #000; font-weight: 600; padding: 1px 6px; border-radius: 10px; margin-left: 6px; font-size: 11px; }
  .state-badge { display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-left: 6px; }
  .state-supported { background: #d1ecda; color: #155724; }
  .state-refuted { background: #f8d7da; color: #721c24; }
  .state-under_test { background: #d6e7f3; color: #0c5460; }
  .per-agent-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 6px; }
  .per-agent-table th, .per-agent-table td {
    padding: 4px 6px; text-align: right;
    border-bottom: 1px solid var(--border);
    font-family: "SF Mono", Menlo, monospace;
    color: var(--fg);
  }
  .per-agent-table th {
    text-align: left; color: var(--muted); font-weight: 600;
    font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
    border-bottom-color: var(--subtle);
  }
  .per-agent-table td:first-child, .per-agent-table th:first-child { text-align: left; }
  .per-agent-table tr:last-child td { border-bottom: none; }
  /* Only flag *problem* values — treat normal scores as normal so the
     panel doesn't read as "everything is alarmingly green". The single
     red cell remains the meaningful attention signal. */
  .per-agent-table td.weak { color: var(--danger); }
  .per-agent-table td.strong { /* no special styling — high scores are expected */ }
  .pgr-row { display: grid; grid-template-columns: 18px 90px 1fr 38px; gap: 6px; align-items: center; padding: 3px 0; font-size: 12px; }
  .pgr-row .pid { font-family: "SF Mono", Menlo, monospace; color: var(--muted); font-size: 11px; }
  .pgr-row .w { font-family: "SF Mono", Menlo, monospace; text-align: right; font-size: 11px; }
  .pgr-row input[type=range] { width: 100%; height: 3px; accent-color: var(--accent); }
  .pgr-actions { display: flex; gap: 6px; margin-top: 10px; }
  .pgr-actions button { font-size: 11px; padding: 3px 8px; border: 1px solid var(--border); background: var(--bg); border-radius: 3px; cursor: pointer; }
  .pgr-actions button.primary { background: var(--accent); color: white; border-color: var(--accent); }
  .pgr-formula { font-family: "SF Mono", Menlo, monospace; font-size: 10px; color: var(--muted); margin-top: 8px; padding-top: 8px; border-top: 1px dotted var(--border); word-break: break-word; }
  .pgr-notes { font-size: 10px; color: var(--muted); margin-top: 6px; line-height: 1.4; }
  .pgr-notes li { margin-bottom: 2px; }
  a.src-cite { color: var(--accent); text-decoration: none; background: var(--accent-soft); padding: 1px 4px; border-radius: 3px; font-size: 92%; cursor: help; }
  a.src-cite:hover { background: rgba(37, 99, 235, 0.18); }
  /* Hover popover for citation links — shows the cited entry's content */
  .cite-tooltip {
    position: absolute; z-index: 1000; max-width: 380px;
    background: #111827; color: #f9fafb; font-size: var(--text-sm);
    padding: var(--s-2) var(--s-3); border-radius: 6px; line-height: 1.5;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18);
    display: none; pointer-events: none;
    font-family: inherit;
  }
  .cite-tooltip .cite-meta {
    font-size: var(--text-xs); color: #9ca3af;
    margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em;
  }
  .bb-entry.hl { outline: 2px solid var(--accent); background: rgba(13,110,253,0.06); transition: background .4s ease; }
  .spark {
    /* DOM order is [svg, label, val] — match it: 90px sparkline,
       flexible label that fills remaining space, fixed value column. */
    display: grid; grid-template-columns: 90px minmax(0, 1fr) 48px;
    align-items: center; gap: 8px; margin: 2px 0;
    font-size: 11px; font-family: "SF Mono", Menlo, monospace;
  }
  .spark svg { width: 90px; height: 22px; }
  .spark .label {
    color: var(--muted); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; min-width: 0;
  }
  .spark .val { text-align: right; color: var(--fg); }
  .spark-header { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin: 8px 0 3px; }
  .kind-evidence h3 { color: #1976d2; }
  .kind-hypothesis h3 { color: #388e3c; }
  .kind-critique h3 { color: #d32f2f; }
  .kind-experiment h3 { color: #7b1fa2; }
  .kind-result h3 { color: #0097a7; }
  .kind-draft h3 { color: #455a64; }
  .kind-review h3 { color: #6a1b9a; }
  .pi-row { display: flex; gap: 8px; margin-top: 8px; }
  .pi-row input { flex: 1; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
  .empty { color: var(--muted); font-size: 13px; padding: 8px 0; }
  @media (max-width: 1024px) {
    main { grid-template-columns: 1fr; }
    .feed, .board { max-height: 60vh; }
  }
</style>
</head>
<body>
<header>
  <h1>research-pipeline</h1>
  <select id="project-picker" style="min-width: 320px"></select>
  <span id="status" class="muted"><span id="status-dot" class="status-dot"></span><span id="status-text">connecting</span></span>
</header>

<main>
  <section class="panel feed">
    <h2>
      <span><span id="channel-title">Twitter</span> channel <span class="count" id="posts-count"></span></span>
      <span class="channel-tabs">
        <button id="tab-twitter" class="active" data-channel="twitter">Twitter</button>
        <button id="tab-reddit" data-channel="reddit">Reddit</button>
      </span>
    </h2>
    <div id="posts"></div>
    <div class="pi-row">
      <input id="pi-input" type="text" placeholder="Post as PI (directive that agents see next turn)">
      <button class="primary" id="pi-send">Post as PI</button>
    </div>
  </section>

  <section class="panel board">
    <h2>Blackboard <span class="count" id="bb-count"></span></h2>
    <div id="blackboard"></div>
  </section>

  <aside>
    <section class="panel">
      <h2>KPI</h2>
      <div id="kpi"></div>
      <div id="kpi-trend" style="margin-top: 12px;"></div>
    </section>
    <section class="panel" style="margin-top: 12px;">
      <h2>Per-agent rubric</h2>
      <div id="per-agent-kpi"></div>
    </section>
    <section class="panel" style="margin-top: 12px;">
      <h2>PGR proxies</h2>
      <div id="pgr-config"></div>
    </section>
  </aside>
</main>

<script>
const ARCH_COLOR = {
  scout:'#1976d2', hypogen:'#388e3c', experimenter:'#7b1fa2',
  critic:'#d32f2f', replicator:'#0097a7', statistician:'#f57c00',
  writer:'#455a64', reviewer:'#6a1b9a'
};
const KPI_LABELS = ['relevance_to_goal','novelty','rigor','citation_quality'];

let currentProject = null;
let currentChannel = 'twitter';
let agentsById = {};
let postsById = {};
let evt = null;

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

function linkifyCitations(htmlSafe) {
  // Turn [src #42] into a link that scrolls to the matching blackboard entry.
  return htmlSafe.replace(
    /\[\s*src\s*#(\d+)\s*\]/gi,
    (m, id) => `<a href="#bb-${id}" class="src-cite" data-bb-id="${id}">[src #${id}]</a>`
  );
}

function flashBlackboardEntry(id) {
  const el = document.getElementById(`bb-${id}`);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('hl');
  setTimeout(() => el.classList.remove('hl'), 1800);
}

// Delegate clicks on citation links to the flash/scroll handler.
document.addEventListener('click', e => {
  const a = e.target.closest('a.src-cite');
  if (!a) return;
  e.preventDefault();
  flashBlackboardEntry(a.dataset.bbId);
});

// Citation hover cards — show the cited entry's content as a popover.
let _citeTooltip = null;
function _ensureCiteTooltip() {
  if (!_citeTooltip) {
    _citeTooltip = document.createElement('div');
    _citeTooltip.className = 'cite-tooltip';
    document.body.appendChild(_citeTooltip);
  }
  return _citeTooltip;
}
function showCiteTooltip(target) {
  const id = target.dataset.bbId;
  const bbEntry = document.getElementById('bb-' + id);
  if (!bbEntry) return;
  const contentEl = bbEntry.querySelector('.content');
  if (!contentEl) return;
  const content = (contentEl.textContent || '').trim();
  if (!content) return;
  const metaEl = bbEntry.querySelector('.meta');
  const meta = metaEl ? (metaEl.textContent || '').trim() : '';
  const tip = _ensureCiteTooltip();
  tip.innerHTML = (meta ? `<div class="cite-meta">${escapeHtml(meta.slice(0, 80))}</div>` : '')
    + escapeHtml(content.slice(0, 360))
    + (content.length > 360 ? '…' : '');
  const r = target.getBoundingClientRect();
  // Position below the link by default; flip up if there's no room.
  const tipH = 120, gap = 6;
  const top = (r.bottom + tipH + gap > window.innerHeight)
    ? window.scrollY + r.top - tipH - gap
    : window.scrollY + r.bottom + gap;
  const left = window.scrollX + Math.min(r.left, window.innerWidth - 400);
  tip.style.top = top + 'px';
  tip.style.left = Math.max(8, left) + 'px';
  tip.style.display = 'block';
}
function hideCiteTooltip() {
  if (_citeTooltip) _citeTooltip.style.display = 'none';
}
document.addEventListener('mouseover', e => {
  const a = e.target.closest('a.src-cite');
  if (a) showCiteTooltip(a);
});
document.addEventListener('mouseout', e => {
  const a = e.target.closest('a.src-cite');
  if (a) hideCiteTooltip();
});

function renderEmptyState() {
  // Replace the main grid with a centered call-to-action when there are no projects yet.
  const main = document.querySelector('main');
  if (!main) return;
  main.style.display = 'block';
  main.innerHTML = `
    <section class="panel" style="max-width: 640px; margin: 48px auto; padding: 32px;">
      <h2 style="font-size: var(--text-md); text-transform: none; letter-spacing: 0; color: var(--fg); margin-bottom: var(--s-3);">No projects yet</h2>
      <p style="color: var(--muted); margin-bottom: var(--s-4); line-height: 1.6;">
        The dashboard streams from a project's blackboard. Create one from the CLI to get started:
      </p>
      <pre style="background: var(--panel); padding: var(--s-3) var(--s-4); border-radius: 6px; font-size: var(--text-sm); overflow-x: auto; border: 1px solid var(--border); margin: 0 0 var(--s-4); font-family: 'SF Mono', Menlo, monospace;">$ rp project create --goal "your research question" --archetypes auto
$ rp project ingest 1 paper.pdf
$ rp project run 1 --turns 3 --reddit-every 2</pre>
      <p style="color: var(--muted); font-size: var(--text-sm); margin: 0;">
        Or try <code style="background: var(--panel); padding: 1px 5px; border-radius: 3px;">rp demo</code> to run end-to-end on a bundled sample.
      </p>
    </section>`;
}

async function loadProjects() {
  setStatus('connecting', 'loading projects…');
  const r = await fetch('/api/projects');
  const projects = await r.json();
  const sel = document.getElementById('project-picker');
  if (projects.length === 0) {
    sel.innerHTML = '<option>(no projects)</option>';
    sel.disabled = true;
    setStatus('connected', 'no projects yet');
    renderEmptyState();
    return;
  }
  sel.innerHTML = projects.map(p =>
    `<option value="${p.id}">#${p.id} [${p.status}] ${escapeHtml(p.goal.slice(0, 80))}</option>`
  ).join('');
  sel.onchange = e => selectProject(parseInt(e.target.value, 10));
  selectProject(projects[0].id);
}

function setStatus(state, text) {
  // state: 'connecting' | 'connected' | 'streaming' | 'error'
  const dot = document.getElementById('status-dot');
  const t = document.getElementById('status-text');
  if (dot) dot.className = 'status-dot ' + state;
  if (t) t.textContent = text;
}

async function selectProject(pid) {
  currentProject = pid;
  setStatus('connected', `project ${pid}`);
  const ags = await (await fetch(`/api/projects/${pid}/agents`)).json();
  agentsById = Object.fromEntries(ags.map(a => [a.id, a]));
  await loadChannel(currentChannel);
  refreshKpi();
  refreshBlackboard();
}

async function loadChannel(channel) {
  currentChannel = channel;
  document.getElementById('channel-title').textContent =
    channel === 'twitter' ? 'Twitter' : 'Reddit';
  document.querySelectorAll('.channel-tabs button').forEach(b => {
    b.classList.toggle('active', b.dataset.channel === channel);
  });
  if (evt) evt.close();
  postsById = {};
  const feed = document.getElementById('posts');
  feed.innerHTML = '';
  if (!currentProject) return;

  const posts = await (
    await fetch(`/api/projects/${currentProject}/posts?channel=${channel}`)
  ).json();
  if (channel === 'twitter') {
    posts.forEach(renderPost);
  } else {
    renderRedditThreads(posts);
  }
  document.getElementById('posts-count').textContent = `${posts.length} posts`;

  evt = new EventSource(`/api/projects/${currentProject}/stream?channel=${channel}`);
  evt.onopen = () => setStatus('connected', `project ${currentProject} · live`);
  evt.onerror = () => setStatus('error', 'reconnecting…');
  evt.onmessage = e => {
    const p = JSON.parse(e.data);
    if (postsById[p.id]) return;
    if (channel === 'twitter') {
      renderPost(p);
    } else {
      // Re-render Reddit on each new post — cheap at this scale.
      appendRedditPost(p);
    }
    refreshKpi();
    refreshBlackboard();
    document.getElementById('posts-count').textContent =
      `${Object.keys(postsById).length} posts`;
    setStatus('streaming', `project ${currentProject} · ${Object.keys(postsById).length} posts`);
  };
}

// Twitter: flat feed (existing behavior preserved below via renderPost)

function renderRedditThreads(posts) {
  posts.forEach(p => postsById[p.id] = p);
  const roots = posts.filter(p => p.parent_id == null);
  const byParent = {};
  posts.filter(p => p.parent_id != null).forEach(p => {
    (byParent[p.parent_id] = byParent[p.parent_id] || []).push(p);
  });
  const feed = document.getElementById('posts');
  feed.innerHTML = '';
  if (roots.length === 0) {
    feed.innerHTML = `
      <div class="empty" style="padding: var(--s-5) var(--s-3); text-align: center; line-height: 1.6;">
        No Reddit threads yet for this project.<br>
        <span style="font-size: var(--text-xs); color: var(--subtle);">
          Reddit threads are auto-spawned during simulation runs with
          <code style="background: var(--panel); padding: 1px 5px; border-radius: 3px; font-family: 'SF Mono', Menlo, monospace;">--reddit-every N</code>,
          or trigger one manually with
          <code style="background: var(--panel); padding: 1px 5px; border-radius: 3px; font-family: 'SF Mono', Menlo, monospace;">rp project reddit-round &lt;id&gt; --topic "..."</code>.
        </span>
      </div>`;
    return;
  }
  for (const root of roots) {
    feed.appendChild(renderRedditThread(root, byParent[root.id] || []));
  }
}

function appendRedditPost(p) {
  postsById[p.id] = p;
  const feed = document.getElementById('posts');
  if (p.parent_id == null) {
    feed.appendChild(renderRedditThread(p, []));
  } else {
    const threadEl = feed.querySelector(`[data-thread-id="${p.parent_id}"]`);
    if (threadEl) {
      const repliesEl = threadEl.querySelector('.reddit-replies');
      repliesEl.appendChild(renderRedditReply(p));
      const countEl = threadEl.querySelector('.reddit-reply-count');
      const n = repliesEl.querySelectorAll('.reddit-reply').length;
      countEl.textContent = `${n} repl${n === 1 ? 'y' : 'ies'}`;
    }
  }
}

function renderRedditThread(root, replies) {
  const arch = root.agent_id != null ? (agentsById[root.agent_id]?.archetype || `agent ${root.agent_id}`) : 'PI';
  const color = root.agent_id == null ? '#e0a800' : (ARCH_COLOR[arch] || '#555');
  const wrapper = document.createElement('div');
  wrapper.className = 'reddit-thread';
  wrapper.dataset.threadId = root.id;
  wrapper.innerHTML = `
    <div class="reddit-root">
      <div class="meta">
        <span class="dot" style="background:${color}"></span>
        <span class="who">${escapeHtml(arch)}</span>
        <span>· turn ${root.turn} · #${root.id}</span>
      </div>
      <h3>${escapeHtml(root.title || '(untitled)')}</h3>
      <div class="content">${linkifyCitations(escapeHtml(root.content))}</div>
      <div class="reddit-reply-count">${replies.length} repl${replies.length === 1 ? 'y' : 'ies'}</div>
    </div>
    <div class="reddit-replies"></div>`;
  const repliesEl = wrapper.querySelector('.reddit-replies');
  for (const r of replies) {
    repliesEl.appendChild(renderRedditReply(r));
  }
  return wrapper;
}

function renderRedditReply(p) {
  const arch = p.agent_id != null ? (agentsById[p.agent_id]?.archetype || `agent ${p.agent_id}`) : 'PI';
  const color = p.agent_id == null ? '#e0a800' : (ARCH_COLOR[arch] || '#555');
  const div = document.createElement('div');
  div.className = 'reddit-reply';
  div.innerHTML = `
    <div class="meta">
      <span class="dot" style="background:${color}"></span>
      <span class="who">${escapeHtml(arch)}</span>
      <span>· #${p.id} · turn ${p.turn}</span>
    </div>
    <div class="content">${linkifyCitations(escapeHtml(p.content))}</div>`;
  return div;
}

document.querySelectorAll('.channel-tabs button').forEach(btn => {
  btn.onclick = () => loadChannel(btn.dataset.channel);
});

function renderPost(p) {
  postsById[p.id] = p;
  const feed = document.getElementById('posts');
  const arch = p.agent_id == null ? null : (agentsById[p.agent_id]?.archetype || null);
  const isPI = p.agent_id == null;
  const color = isPI ? '#e0a800' : (ARCH_COLOR[arch] || '#555');
  const who = isPI ? 'PI' : (arch || `agent ${p.agent_id}`);
  const replyMeta = p.parent_id
    ? `<span class="reply">&nbsp;reply to #${p.parent_id}</span>`
    : '';
  const div = document.createElement('div');
  div.className = 'post' + (isPI ? ' pi' : '');
  // Archetype accent: colored left-edge stripe matching the agent role.
  // PI directives use the existing yellow stripe styling via the .pi class.
  if (!isPI) div.style.borderLeftColor = color;
  div.innerHTML = `
    <div class="meta">
      <span class="who">${escapeHtml(who)}</span>
      <span class="post-id">#${p.id}</span>
      <span>turn ${p.turn}</span>
      ${replyMeta}
    </div>
    <div class="content">${linkifyCitations(escapeHtml(p.content))}</div>`;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

async function refreshKpi() {
  if (!currentProject) return;
  const kpi = await (await fetch(`/api/projects/${currentProject}/kpi`)).json();
  const rubric = kpi.rubric || {};
  const counters = kpi.counters || {};
  const box = document.getElementById('kpi');
  refreshKpiTrend();
  refreshPerAgentKpi();
  refreshPgrConfig();
  if (Object.keys(rubric).length === 0 && Object.keys(counters).length === 0) {
    // Don't say "no scores yet" if trajectory has historical scores —
    // refreshKpiTrend will populate the sparklines below. Hide the
    // current-scores box entirely in that case.
    box.innerHTML = '';
    return;
  }
  const rubricHtml = KPI_LABELS.map(k => {
    const v = rubric[k] ?? 0;
    const pct = Math.max(0, Math.min(100, (v / 5) * 100));
    return `
      <div class="kpi-row"><span>${k}</span><span>${v.toFixed(1)}</span></div>
      <div class="kpi-bar"><div class="kpi-fill" style="width:${pct}%"></div></div>`;
  }).join('');
  const counterOrder = ['coverage','evidence_density','idea_diversity','echo_rate'];
  const countersHtml = counterOrder
    .filter(k => k in counters)
    .map(k => `<div class="kpi-row"><span>${k}</span><span>${counters[k].toFixed(2)}</span></div>`)
    .join('');
  box.innerHTML = `
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;">Rubric (1-5)</div>
    ${rubricHtml || '<div class="empty">no rubric yet</div>'}
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:12px 0 4px;">Counters</div>
    ${countersHtml || '<div class="empty">no counters yet</div>'}`;
}

async function refreshKpiTrend() {
  if (!currentProject) return;
  const t = await (await fetch(`/api/projects/${currentProject}/kpi/trajectory`)).json();
  const rubric = t.rubric || {};
  const counters = t.counters || {};
  const box = document.getElementById('kpi-trend');
  if (Object.keys(rubric).length === 0 && Object.keys(counters).length === 0) {
    box.innerHTML = ''; return;
  }
  const pgr = t.pgr || {};
  const rubricHtml = KPI_LABELS
    .filter(m => rubric[m] && rubric[m].length > 0)
    .map(m => sparkline(m, rubric[m], 0, 5))
    .join('');
  const counterOrder = ['idea_diversity','echo_rate','evidence_density','coverage'];
  const countersHtml = counterOrder
    .filter(m => counters[m] && counters[m].length > 0)
    .map(m => sparkline(m, counters[m], 0, null))
    .join('');
  const pgrOrder = ['pgr_composite','pgr_cite','pgr_heldout','pgr_adv'];
  const pgrHtml = pgrOrder
    .filter(m => pgr[m] && pgr[m].length > 0)
    .map(m => sparkline(m, pgr[m], 0, 1))
    .join('');
  box.innerHTML = `
    ${rubricHtml ? `<div class="spark-header">Rubric trajectory</div>${rubricHtml}` : ''}
    ${countersHtml ? `<div class="spark-header">Counter trajectory</div>${countersHtml}` : ''}
    ${pgrHtml ? `<div class="spark-header">PGR (research quality)</div>${pgrHtml}` : ''}`;
}

function sparkline(metric, series, yMinFloor, yMaxCap) {
  const w = 90, h = 22, pad = 2;
  const xs = series.map(d => d.turn);
  const ys = series.map(d => d.value);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = yMinFloor != null ? yMinFloor : Math.min(...ys);
  const yMax = yMaxCap != null ? yMaxCap : Math.max(1e-9, Math.max(...ys));
  const dx = xMax === xMin ? 1 : (xMax - xMin);
  const dy = yMax === yMin ? 1 : (yMax - yMin);
  const pts = series.map(d => {
    const x = pad + ((d.turn - xMin) / dx) * (w - 2 * pad);
    const y = h - pad - ((d.value - yMin) / dy) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const lastPt = series[series.length - 1];
  const lastXY = pts.split(' ').pop();
  const [lx, ly] = lastXY.split(',');
  return `
    <div class="spark" title="${metric}: ${series.length} turns, latest ${lastPt.value.toFixed(2)}">
      <svg width="${w}" height="${h}">
        <polyline fill="none" stroke="var(--accent)" stroke-width="1.4" points="${pts}" />
        <circle cx="${lx}" cy="${ly}" r="2" fill="var(--accent)" />
      </svg>
      <span class="label">${metric}</span>
      <span class="val">${lastPt.value.toFixed(2)}</span>
    </div>`;
}

const AGENT_RUBRIC_COLS = [
  {k: 'relevance_to_goal', label: 'rel'},
  {k: 'novelty', label: 'nov'},
  {k: 'rigor', label: 'rig'},
  {k: 'citation_quality', label: 'cit'},
  {k: 'role_consistency', label: 'role'},
  {k: 'collaboration_signal', label: 'coll'},
];

async function refreshPgrConfig() {
  if (!currentProject) return;
  let data;
  try {
    data = await (await fetch(`/api/projects/${currentProject}/pgr-config`)).json();
  } catch (e) {
    return;
  }
  const box = document.getElementById('pgr-config');
  const current = (data.current && data.current.proxies) || {};
  const rec = data.recommendation || [];
  // If current is empty, use recommendation as effective weights for display
  const effective = {};
  for (const p of rec) {
    const c = current[p.id];
    effective[p.id] = {
      enabled: c ? !!c.enabled : p.enabled,
      weight: c ? Number(c.weight || 0) : p.weight,
      rationale: p.rationale,
    };
  }
  const rowsHtml = rec.map(p => {
    const cur = effective[p.id];
    const enabled = cur.enabled;
    const weight = cur.weight;
    return `
      <div class="pgr-row" title="${escapeHtml(p.rationale)}">
        <input type="checkbox" data-pid="${p.id}" class="pgr-en" ${enabled ? 'checked' : ''}>
        <span class="pid">${p.id.replace('pgr_','')}</span>
        <input type="range" min="0" max="1" step="0.05" data-pid="${p.id}"
               class="pgr-w" value="${weight}" ${enabled ? '' : 'disabled'}>
        <span class="w" data-pid="${p.id}-val">${weight.toFixed(2)}</span>
      </div>`;
  }).join('');
  const formula = Object.entries(effective)
    .filter(([, v]) => v.enabled && v.weight > 0)
    .map(([k, v]) => `${v.weight.toFixed(2)}×${k.replace('pgr_','')}`)
    .join(' + ') || '(no enabled proxies)';
  const notesHtml = (data.notes || []).map(n => `<li>${escapeHtml(n)}</li>`).join('');
  box.innerHTML = `
    ${rowsHtml}
    <div class="pgr-actions">
      <button id="pgr-save" class="primary">Save</button>
      <button id="pgr-apply-rec">Apply recommended</button>
    </div>
    <div class="pgr-formula">${formula}</div>
    ${notesHtml ? `<ul class="pgr-notes">${notesHtml}</ul>` : ''}`;

  // Wire handlers
  box.querySelectorAll('.pgr-w').forEach(el => {
    el.oninput = e => {
      const pid = e.target.dataset.pid;
      const v = Number(e.target.value);
      box.querySelector(`[data-pid="${pid}-val"]`).textContent = v.toFixed(2);
    };
  });
  box.querySelectorAll('.pgr-en').forEach(el => {
    el.onchange = e => {
      const pid = e.target.dataset.pid;
      const sliderEl = box.querySelector(`.pgr-w[data-pid="${pid}"]`);
      if (sliderEl) sliderEl.disabled = !e.target.checked;
    };
  });
  document.getElementById('pgr-save').onclick = async () => {
    const proxies = {};
    box.querySelectorAll('.pgr-en').forEach(el => {
      const pid = el.dataset.pid;
      const enabled = el.checked;
      const w = Number(box.querySelector(`.pgr-w[data-pid="${pid}"]`).value);
      proxies[pid] = { enabled, weight: enabled ? w : 0 };
    });
    // Renormalize enabled weights to sum to 1
    const total = Object.values(proxies)
      .filter(p => p.enabled).reduce((s, p) => s + p.weight, 0);
    if (total > 0) {
      for (const p of Object.values(proxies)) {
        if (p.enabled) p.weight = p.weight / total;
      }
    }
    await fetch(`/api/projects/${currentProject}/pgr-config`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ proxies }),
    });
    refreshPgrConfig();
  };
  document.getElementById('pgr-apply-rec').onclick = async () => {
    await fetch(`/api/projects/${currentProject}/pgr-config`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data.recommended || { proxies: {} }),
    });
    refreshPgrConfig();
  };
}


async function refreshPerAgentKpi() {
  if (!currentProject) return;
  const scores = await (await fetch(`/api/projects/${currentProject}/kpi/per-agent`)).json();
  const box = document.getElementById('per-agent-kpi');
  if (!scores || Object.keys(scores).length === 0) {
    box.innerHTML = '<div class="empty">no per-agent rubric yet</div>'; return;
  }
  const header = ['<tr><th>agent</th>']
    .concat(AGENT_RUBRIC_COLS.map(c => `<th title="${c.k}">${c.label}</th>`))
    .concat(['</tr>']).join('');
  const rows = Object.entries(scores).map(([aid, ms]) => {
    const arch = (agentsById[aid]?.archetype || `a${aid}`);
    const cells = AGENT_RUBRIC_COLS.map(c => {
      const v = ms[c.k];
      if (v == null) return '<td>—</td>';
      const cls = v >= 4 ? 'strong' : (v <= 2 ? 'weak' : '');
      return `<td class="${cls}">${v.toFixed(1)}</td>`;
    }).join('');
    return `<tr><td>${escapeHtml(arch)}</td>${cells}</tr>`;
  }).join('');
  box.innerHTML = `<table class="per-agent-table"><thead>${header}</thead><tbody>${rows}</tbody></table>`;
}

async function refreshBlackboard() {
  if (!currentProject) return;
  const entries = await (await fetch(`/api/projects/${currentProject}/blackboard`)).json();
  document.getElementById('bb-count').textContent = entries.length ? `${entries.length} entries` : '';
  const byKind = {};
  for (const e of entries) (byKind[e.kind] = byKind[e.kind] || []).push(e);
  const order = ['evidence','hypothesis','experiment','result','critique','draft','review'];
  const box = document.getElementById('blackboard');
  if (entries.length === 0) {
    box.innerHTML = '<div class="empty">empty — agents have not yet filed anything</div>';
    return;
  }
  box.innerHTML = order
    .filter(k => byKind[k])
    .map(k => {
      const items = byKind[k].map(e => {
        const arch = e.agent_id != null ? (agentsById[e.agent_id]?.archetype || `agent ${e.agent_id}`) : 'system';
        const refs = (e.refs && e.refs.length)
          ? `<div class="refs">${e.refs.map(r => `<code>${escapeHtml(String(r))}</code>`).join('')}</div>`
          : '';
        const echoes = (e.echo_count && e.echo_count > 0)
          ? `<div class="echoes">echoed by ${(e.echo_refs||[]).map(r => {
              const eArch = r.agent_id != null ? (agentsById[r.agent_id]?.archetype || `agent ${r.agent_id}`) : 'PI';
              return `${escapeHtml(eArch)}@t${r.turn}(${r.similarity})`;
            }).join(', ')}</div>`
          : '';
        const badge = (e.echo_count && e.echo_count > 0)
          ? `<span class="echo-badge" title="echoed by ${e.echo_count} agents">×${e.echo_count + 1}</span>`
          : '';
        const stateBadge = (e.kind === 'hypothesis' && e.state && e.state !== 'proposed')
          ? `<span class="state-badge state-${e.state}" title="${e.resolutions?.length || 0} resolution(s)">${e.state}</span>`
          : '';
        return `
          <div class="bb-entry" id="bb-${e.id}">
            <div class="meta">t${e.turn} · ${escapeHtml(arch)} · #${e.id}${badge}${stateBadge}</div>
            <div class="content">${escapeHtml(e.content)}</div>
            ${refs}
            ${echoes}
          </div>`;
      }).join('');
      return `<div class="bb-group kind-${k}">
        <h3><span>${k}</span><span>${byKind[k].length}</span></h3>
        ${items}
      </div>`;
    })
    .join('');
}

document.getElementById('pi-send').onclick = async () => {
  if (!currentProject) return;
  const inp = document.getElementById('pi-input');
  const message = inp.value.trim();
  if (!message) return;
  inp.disabled = true;
  await fetch(`/api/projects/${currentProject}/pi-post`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ message }),
  });
  inp.value = '';
  inp.disabled = false;
};

loadProjects();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)

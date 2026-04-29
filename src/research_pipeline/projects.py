"""Project + agent persistence.

Thin sqlite3 helpers — no ORM, no session objects. Safe to use from both sync
code paths (CLI) and async ones (FastAPI, simulation loop).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from .archetypes import by_id


@dataclass(frozen=True)
class Project:
    id: int
    user_id: int
    goal: str
    focus: str | None
    status: str
    pgr_config: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectAgent:
    id: int
    project_id: int
    archetype: str
    weight: float
    temperature: float = 0.75
    max_tokens: int = 300
    specialty_focus: str | None = None
    token_budget: int = 20000


def upsert_user(conn: sqlite3.Connection, email: str) -> int:
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO users (email) VALUES (?)", (email,))
    conn.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


def create_project(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    goal: str,
    archetype_ids: list[str],
    focus: str | None = None,
) -> int:
    for aid in archetype_ids:
        by_id(aid)  # raises if unknown
    cur = conn.execute(
        "INSERT INTO projects (user_id, goal, focus) VALUES (?, ?, ?)",
        (user_id, goal, focus),
    )
    project_id = cur.lastrowid
    assert project_id is not None
    for aid in archetype_ids:
        conn.execute(
            "INSERT INTO agents (project_id, archetype, weight) VALUES (?, ?, 1.0)",
            (project_id, aid),
        )
    conn.commit()
    return project_id


_PROJECT_COLS = (
    "id, user_id, goal, focus, status, "
    "COALESCE(pgr_config_json, '{}') AS pgr_config_json"
)


def _row_to_project(r: sqlite3.Row) -> Project:
    try:
        cfg = json.loads(r["pgr_config_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        cfg = {}
    return Project(
        id=r["id"],
        user_id=r["user_id"],
        goal=r["goal"],
        focus=r["focus"],
        status=r["status"],
        pgr_config=cfg,
    )


def list_projects(conn: sqlite3.Connection) -> list[Project]:
    rows = conn.execute(
        f"SELECT {_PROJECT_COLS} FROM projects ORDER BY id"
    ).fetchall()
    return [_row_to_project(r) for r in rows]


def get_project(conn: sqlite3.Connection, project_id: int) -> Project:
    r = conn.execute(
        f"SELECT {_PROJECT_COLS} FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if not r:
        raise LookupError(f"project {project_id} not found")
    return _row_to_project(r)


def update_pgr_config(
    conn: sqlite3.Connection, *, project_id: int, config: dict
) -> None:
    """Persist the PGR proxy configuration for a project."""
    conn.execute(
        "UPDATE projects SET pgr_config_json = ? WHERE id = ?",
        (json.dumps(config), project_id),
    )
    conn.commit()


def get_project_agents(conn: sqlite3.Connection, project_id: int) -> list[ProjectAgent]:
    rows = conn.execute(
        """
        SELECT id, project_id, archetype, weight,
               COALESCE(temperature, 0.75) AS temperature,
               COALESCE(max_tokens, 300) AS max_tokens,
               specialty_focus,
               COALESCE(token_budget, 20000) AS token_budget
        FROM agents WHERE project_id = ? ORDER BY id
        """,
        (project_id,),
    ).fetchall()
    return [
        ProjectAgent(
            id=r["id"],
            project_id=r["project_id"],
            archetype=r["archetype"],
            weight=r["weight"],
            temperature=float(r["temperature"]),
            max_tokens=int(r["max_tokens"]),
            specialty_focus=r["specialty_focus"],
            token_budget=int(r["token_budget"]),
        )
        for r in rows
    ]


def update_agent_config(
    conn: sqlite3.Connection,
    *,
    agent_id: int,
    temperature: float | None = None,
    max_tokens: int | None = None,
    specialty_focus: str | None = None,
    token_budget: int | None = None,
) -> None:
    """Patch per-agent config fields. Only non-None fields are written."""
    sets: list[str] = []
    params: list = []
    if temperature is not None:
        sets.append("temperature = ?")
        params.append(float(temperature))
    if max_tokens is not None:
        sets.append("max_tokens = ?")
        params.append(int(max_tokens))
    if specialty_focus is not None:
        sets.append("specialty_focus = ?")
        params.append(specialty_focus)
    if token_budget is not None:
        sets.append("token_budget = ?")
        params.append(int(token_budget))
    if not sets:
        return
    params.append(agent_id)
    conn.execute(f"UPDATE agents SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()


def get_channel_posts(
    conn: sqlite3.Connection, project_id: int, channel: str = "twitter"
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, turn, agent_id, content, created_at FROM channel_posts "
        "WHERE project_id = ? AND channel = ? ORDER BY id",
        (project_id, channel),
    ).fetchall()


def set_project_status(conn: sqlite3.Connection, project_id: int, status: str) -> None:
    conn.execute("UPDATE projects SET status = ? WHERE id = ?", (status, project_id))
    conn.commit()

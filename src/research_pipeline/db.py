"""SQLite schema. Thin; no ORM yet."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    goal TEXT NOT NULL,
    focus TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    archetype TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    kpi_config_json TEXT
);

CREATE TABLE IF NOT EXISTS channel_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    channel TEXT NOT NULL,
    parent_id INTEGER,
    agent_id INTEGER,
    content TEXT NOT NULL,
    turn INTEGER NOT NULL,
    likes INTEGER NOT NULL DEFAULT 0,
    upvotes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS blackboard_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    agent_id INTEGER,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    refs_json TEXT,
    turn INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS kpi_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    agent_id INTEGER,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    turn INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    turn_cap INTEGER NOT NULL,
    token_budget INTEGER NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    verdict TEXT
);

CREATE TABLE IF NOT EXISTS user_wiki_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    refs_json TEXT NOT NULL DEFAULT '[]',
    embedding_json TEXT,
    source_project_id INTEGER,
    promoted_score REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_user_wiki_user_kind ON user_wiki_entries(user_id, kind);

CREATE TABLE IF NOT EXISTS oasis_post_map (
    project_id INTEGER NOT NULL,
    oasis_post_id INTEGER NOT NULL,
    channel_post_id INTEGER NOT NULL REFERENCES channel_posts(id),
    PRIMARY KEY (project_id, oasis_post_id)
);

CREATE INDEX IF NOT EXISTS ix_channel_posts_project_channel ON channel_posts(project_id, channel, turn);
CREATE INDEX IF NOT EXISTS ix_blackboard_project_kind ON blackboard_entries(project_id, kind);
CREATE INDEX IF NOT EXISTS ix_kpi_scores_project ON kpi_scores(project_id, metric, turn);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


_MIGRATIONS = (
    "ALTER TABLE blackboard_entries ADD COLUMN embedding_json TEXT",
    "ALTER TABLE blackboard_entries ADD COLUMN echo_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE blackboard_entries ADD COLUMN echo_refs_json TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE blackboard_entries ADD COLUMN state TEXT NOT NULL DEFAULT 'proposed'",
    "ALTER TABLE blackboard_entries ADD COLUMN resolutions_json TEXT NOT NULL DEFAULT '[]'",
    # Phase 3 — visibility partition for held-out evidence (PGR Proxy 2)
    "ALTER TABLE blackboard_entries ADD COLUMN visibility TEXT NOT NULL DEFAULT 'visible'",
    # Phase 3 — per-project PGR proxy configuration (weights + enable flags)
    "ALTER TABLE projects ADD COLUMN pgr_config_json TEXT NOT NULL DEFAULT '{}'",
    # Phase 3.5 — Karpathy+Zep hybrid: temporal anchor on wiki entries
    # (when the claim/fact is TRUE, not when ingested). ISO date string or NULL.
    "ALTER TABLE user_wiki_entries ADD COLUMN t_ref TEXT",
    "ALTER TABLE channel_posts ADD COLUMN title TEXT",
    # Phase 2 Track A — per-agent configuration
    "ALTER TABLE agents ADD COLUMN temperature REAL NOT NULL DEFAULT 0.75",
    "ALTER TABLE agents ADD COLUMN max_tokens INTEGER NOT NULL DEFAULT 300",
    "ALTER TABLE agents ADD COLUMN specialty_focus TEXT",
    "ALTER TABLE agents ADD COLUMN token_budget INTEGER NOT NULL DEFAULT 20000",
    # Phase 2 Track B — optimization traces
    """
    CREATE TABLE IF NOT EXISTS optimization_traces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        iteration INTEGER NOT NULL,
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at TEXT,
        weakest_agent_id INTEGER,
        config_delta_json TEXT NOT NULL DEFAULT '{}',
        kpi_before_json TEXT NOT NULL DEFAULT '{}',
        kpi_after_json TEXT NOT NULL DEFAULT '{}',
        decision_rationale TEXT,
        tokens_spent INTEGER NOT NULL DEFAULT 0
    )
    """,
    # Roadmap 2.4 — per-entry confidence label.
    # Values: 'EXTRACTED' (pulled from a source), 'INFERRED' (synthesised
    # by an agent from facts), 'AMBIGUOUS' (e.g. critique that survives
    # doubt). Default keeps existing rows defensibly EXTRACTED so the
    # field is non-NULL and code can assume a value is always present.
    "ALTER TABLE blackboard_entries ADD COLUMN confidence TEXT NOT NULL DEFAULT 'EXTRACTED'",
)


def init_db(db_path: Path | str) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
    finally:
        conn.close()

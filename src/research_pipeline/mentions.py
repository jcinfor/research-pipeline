"""Backfill `channel_posts.parent_id` from @agent_N mentions in post text.

Agents write prose like "@agent_2 Re:..." or "Replying to [t1 agent_2]...".
We detect any `agent_N` token and, if N is a real project agent, link the
post's parent_id to the most recent prior post by that agent.
"""
from __future__ import annotations

import re
import sqlite3

_AGENT_REF_RE = re.compile(r"@?agent[_ ](\d+)", re.IGNORECASE)


def link_mentions(
    conn: sqlite3.Connection, *, project_id: int, turn: int
) -> int:
    """Scan posts at `turn` that still lack parent_id and wire them up."""
    agent_ids = {
        r["id"]
        for r in conn.execute(
            "SELECT id FROM agents WHERE project_id = ?", (project_id,)
        )
    }
    if not agent_ids:
        return 0

    linked = 0
    for post in conn.execute(
        "SELECT id, agent_id, content FROM channel_posts "
        "WHERE project_id = ? AND turn = ? AND parent_id IS NULL",
        (project_id, turn),
    ).fetchall():
        content = post["content"] or ""
        mentioned = [int(m.group(1)) for m in _AGENT_REF_RE.finditer(content)]
        # Prefer the first mention that is a real agent and not the author.
        for ref in mentioned:
            if ref == post["agent_id"] or ref not in agent_ids:
                continue
            parent = conn.execute(
                "SELECT id FROM channel_posts "
                "WHERE project_id = ? AND agent_id = ? AND id < ? "
                "ORDER BY id DESC LIMIT 1",
                (project_id, ref, post["id"]),
            ).fetchone()
            if parent:
                conn.execute(
                    "UPDATE channel_posts SET parent_id = ? WHERE id = ?",
                    (parent["id"], post["id"]),
                )
                linked += 1
                break
    conn.commit()
    return linked

"""Tests for Reddit channel persistence + topic picking."""
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from research_pipeline.archetypes import by_id
from research_pipeline.blackboard import KIND_HYPOTHESIS, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.projects import create_project, upsert_user
from research_pipeline.simulation import _pick_reddit_topic, _run_reddit_round


def test_pick_reddit_topic_uses_latest_hypothesis(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="original goal",
                             archetype_ids=["scout", "hypogen"])
        add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                  content="hypothesis A", turn=0, agent_id=1)
        add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                  content="hypothesis B (latest)", turn=1, agent_id=1)
        topic = _pick_reddit_topic(conn, pid, fallback="fallback")
    assert "hypothesis B" in topic


def test_pick_reddit_topic_falls_back_to_goal(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="the original goal",
                             archetype_ids=["scout"])
        topic = _pick_reddit_topic(conn, pid, fallback="the original goal")
    assert topic == "the original goal"


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _FakeLLM:
    """Scripted responses: root is JSON, replies are plain text."""

    def __init__(self, root_json: str, reply_texts: list[str]):
        self._root = root_json
        self._replies = list(reply_texts)

    async def achat(self, role, messages, **kwargs):
        rf = kwargs.get("response_format")
        if rf and rf.get("type") == "json_object":
            return _Resp(choices=[_Choice(message=_Msg(content=self._root))])
        text = self._replies.pop(0) if self._replies else ""
        return _Resp(choices=[_Choice(message=_Msg(content=text))])


def test_run_reddit_round_persists_root_and_replies(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="topic goal",
                             archetype_ids=["scout", "hypogen", "critic"])
        archetypes = [by_id("scout"), by_id("hypogen"), by_id("critic")]
        llm = _FakeLLM(
            root_json=json.dumps({
                "title": "Does X outperform Y?",
                "body": "Here's why it matters: detailed argument...",
            }),
            reply_texts=[
                "Reply from scout: citing Soni et al. 2022...",
                "Reply from critic: you're ignoring the assay variance...",
            ],
        )
        root_id = asyncio.run(
            _run_reddit_round(
                conn, project_id=pid, llm=llm,
                project_goal="topic goal", archetypes=archetypes,
                evidence_pool=[], turn=1,
            )
        )
        posts = list(conn.execute(
            "SELECT title, content, parent_id, channel FROM channel_posts "
            "WHERE project_id = ? ORDER BY id",
            (pid,),
        ))

    assert root_id > 0
    assert len(posts) == 3
    root = posts[0]
    assert root["channel"] == "reddit"
    assert root["title"] == "Does X outperform Y?"
    assert root["parent_id"] is None
    assert all(p["parent_id"] == root_id for p in posts[1:])
    assert all(p["channel"] == "reddit" for p in posts)

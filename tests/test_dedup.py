from pathlib import Path

import pytest

from research_pipeline.blackboard import KIND_HYPOTHESIS, list_entries
from research_pipeline.db import connect, init_db
from research_pipeline.dedup import add_entry_with_dedup, cosine
from research_pipeline.projects import create_project, upsert_user


class _FakeLLM:
    """Deterministic embedder: identical text -> identical vector.
    Different first word -> different axis (nearly orthogonal)."""

    def embed(self, role: str, texts):
        if isinstance(texts, str):
            texts = [texts]
        vecs = []
        for t in texts:
            v = [0.0] * 32
            words = t.strip().lower().split()
            first = words[0] if words else ""
            v[hash(first) % 32] = 1.0
            vecs.append(v)
        return vecs


def test_cosine_basics():
    assert cosine([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
    assert cosine([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)
    assert cosine([1, 0], [0, 0]) == 0.0


def test_identical_content_deduped(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="g", archetype_ids=["hypogen"])
        agent_id = conn.execute(
            "SELECT id FROM agents WHERE project_id = ?", (pid,)
        ).fetchone()["id"]

        fake = _FakeLLM()
        id1, dup1, _ = add_entry_with_dedup(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="hypothesis about adaptive resistance", turn=0,
            agent_id=agent_id, llm=fake, threshold=0.85,
        )
        id2, dup2, sim2 = add_entry_with_dedup(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="hypothesis about adaptive resistance", turn=1,
            agent_id=agent_id, llm=fake, threshold=0.85,
        )
        id3, dup3, _ = add_entry_with_dedup(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="kinase covalent trapping mechanism", turn=1,
            agent_id=agent_id, llm=fake, threshold=0.85,
        )

        assert dup1 is False
        assert dup2 is True and id2 == id1 and sim2 == pytest.approx(1.0)
        assert dup3 is False and id3 != id1

        entries = list_entries(conn, pid)
        assert len(entries) == 2

        canonical = next(e for e in entries if e.id == id1)
        assert canonical.echo_count == 1
        assert len(canonical.echo_refs) == 1
        assert canonical.echo_refs[0]["turn"] == 1


def test_without_llm_skips_dedup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="g", archetype_ids=["hypogen"])
        agent_id = conn.execute(
            "SELECT id FROM agents WHERE project_id = ?", (pid,)
        ).fetchone()["id"]

        add_entry_with_dedup(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="same text", turn=0, agent_id=agent_id, llm=None,
        )
        add_entry_with_dedup(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="same text", turn=1, agent_id=agent_id, llm=None,
        )
        assert len(list_entries(conn, pid)) == 2

from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, KIND_HYPOTHESIS, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.projects import create_project, upsert_user
from research_pipeline.wiki import (
    list_wiki,
    promote_project_to_wiki,
    render_wiki_markdown,
    search_wiki,
    seed_project_from_wiki,
)


class _FakeLLM:
    """First-word axis embedder: strings sharing a first token map to the same
    axis (so query 'kras foo' matches content 'kras resistance')."""

    def __init__(self):
        self._axes: dict[str, int] = {}

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        vecs = []
        for t in texts:
            first = (t.strip().lower().split() or [""])[0]
            if first not in self._axes:
                self._axes[first] = len(self._axes)
            v = [0.0] * 64
            v[self._axes[first]] = 1.0
            vecs.append(v)
        return vecs


def _seed_project(tmp_path: Path, goal: str, archetypes=("scout", "hypogen", "critic")):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal=goal,
                             archetype_ids=list(archetypes))
        agents = list(conn.execute("SELECT id FROM agents WHERE project_id=?", (pid,)))
    return db, uid, pid, [r["id"] for r in agents]


def test_promote_copies_top_k_per_kind(tmp_path: Path):
    db, uid, pid, agents = _seed_project(tmp_path, "test goal")
    with connect(db) as conn:
        # 5 evidence, 2 hypothesis
        for i in range(5):
            add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                      content=f"evidence chunk number {i}", turn=0,
                      agent_id=agents[0])
        for i in range(2):
            add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                      content=f"hypothesis chunk number {i}", turn=0,
                      agent_id=agents[1])
        counts = promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=3)
    assert counts == {KIND_EVIDENCE: 3, KIND_HYPOTHESIS: 2}

    with connect(db) as conn:
        entries = list_wiki(conn, user_id=uid)
    kinds = [e.kind for e in entries]
    assert kinds.count(KIND_EVIDENCE) == 3
    assert kinds.count(KIND_HYPOTHESIS) == 2


def test_promote_is_idempotent(tmp_path: Path):
    db, uid, pid, agents = _seed_project(tmp_path, "test goal")
    with connect(db) as conn:
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                  content="unique evidence item", turn=0, agent_id=agents[0])
        promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=3)
        second = promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=3)
    assert second == {}
    with connect(db) as conn:
        assert len(list_wiki(conn, user_id=uid)) == 1


def test_search_ranks_by_cosine(tmp_path: Path):
    db, uid, pid, agents = _seed_project(tmp_path, "test goal")
    llm = _FakeLLM()
    with connect(db) as conn:
        for content in ["kras resistance", "protac scaffold", "allosteric pocket"]:
            add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                      content=content, turn=0, agent_id=agents[0])
        # populate embeddings directly since add_entry doesn't embed
        import json
        for content in ["kras resistance", "protac scaffold", "allosteric pocket"]:
            emb = llm.embed("embedding", content)[0]
            conn.execute(
                "UPDATE blackboard_entries SET embedding_json = ? WHERE content = ?",
                (json.dumps(emb), content),
            )
        conn.commit()
        promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=3)

        hits = search_wiki(conn, user_id=uid, query="kras foo bar",
                           llm=llm, top_k=3)
    assert hits
    assert hits[0][0].content.startswith("kras")
    assert hits[0][1] == 1.0


def test_render_empty_and_populated(tmp_path: Path):
    db, uid, pid, agents = _seed_project(tmp_path, "test goal")
    with connect(db) as conn:
        empty = render_wiki_markdown(conn, user_id=uid)
    assert "empty" in empty.lower()

    with connect(db) as conn:
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                  content="Soni et al. 2022 says X", turn=0,
                  agent_id=agents[0], refs=["Soni et al.", "2022"])
        promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=3)
        md = render_wiki_markdown(conn, user_id=uid)
    assert "evidence (1)" in md
    assert "Soni et al." in md


def test_seed_project_from_wiki(tmp_path: Path):
    # Set up a project, promote to wiki, then create a second project and seed from wiki.
    db, uid, pid1, agents1 = _seed_project(tmp_path, "first project goal")
    llm = _FakeLLM()
    import json
    with connect(db) as conn:
        for content in ["kras alpha", "protac beta", "allosteric gamma"]:
            add_entry(conn, project_id=pid1, kind=KIND_EVIDENCE,
                      content=content, turn=0, agent_id=agents1[0])
            emb = llm.embed("embedding", content)[0]
            conn.execute(
                "UPDATE blackboard_entries SET embedding_json = ? WHERE content = ?",
                (json.dumps(emb), content),
            )
        conn.commit()
        promote_project_to_wiki(conn, project_id=pid1, top_k_per_kind=3)

        # Second project, goal shares first-word "kras"
        pid2 = create_project(conn, user_id=uid, goal="kras new direction",
                              archetype_ids=["scout"])
        n = seed_project_from_wiki(conn, project_id=pid2, llm=llm, top_k=5)
        assert n >= 1  # at least the "kras alpha" entry seeded

        # The seeded entry should appear in the new project's blackboard
        entries = list(conn.execute(
            "SELECT content, refs_json FROM blackboard_entries WHERE project_id = ?",
            (pid2,),
        ))
        assert any("kras alpha" == r["content"] for r in entries)
        assert any("user_wiki#" in (r["refs_json"] or "") for r in entries)

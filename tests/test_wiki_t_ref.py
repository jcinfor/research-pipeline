"""Tests for the Karpathy + Zep hybrid: t_ref temporal anchor on wiki entries."""
from __future__ import annotations

import json
from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, KIND_HYPOTHESIS, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.projects import create_project, upsert_user
from research_pipeline.wiki import (
    _extract_t_ref,
    list_wiki,
    promote_project_to_wiki,
    render_wiki_markdown,
    search_wiki,
)


# ---------------------------------------------------------------------------
# _extract_t_ref
# ---------------------------------------------------------------------------


def test_extract_t_ref_picks_max_year():
    assert _extract_t_ref(["Smith 2020", "Jones et al. 2022", "x 2018"]) == "2022-01-01"


def test_extract_t_ref_from_mixed_ref_types():
    refs = ["source=paper.pdf", "arxiv:2023.01234", "Soni et al.", "2019"]
    # Picks 2023 as max (the arxiv id contains 2023 per the regex)
    assert _extract_t_ref(refs) == "2023-01-01"


def test_extract_t_ref_none_when_no_years():
    assert _extract_t_ref(["foo", "bar", "baz"]) is None


def test_extract_t_ref_rejects_out_of_range_numbers():
    # 1850 and 2150 are outside [1900, 2099] bounds
    assert _extract_t_ref(["year 1850", "year 2150"]) is None


def test_extract_t_ref_none_for_empty():
    assert _extract_t_ref([]) is None
    assert _extract_t_ref(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Wiki promotion populates t_ref
# ---------------------------------------------------------------------------


class _FakeLLM:
    def __init__(self):
        self._axes: dict[str, int] = {}

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            first = (t.strip().lower().split() or [""])[0]
            if first not in self._axes:
                self._axes[first] = len(self._axes)
            v = [0.0] * 64
            v[self._axes[first]] = 1.0
            out.append(v)
        return out


def _seed(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="t_ref test",
            archetype_ids=["scout", "hypogen"],
        )
    return db, uid, pid


def test_promotion_sets_t_ref_from_refs(tmp_path: Path):
    db, uid, pid = _seed(tmp_path)
    with connect(db) as conn:
        agents = list(conn.execute(
            "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,),
        ))
        # Entry with a year in refs -> t_ref set
        add_entry(
            conn, project_id=pid, kind=KIND_EVIDENCE,
            content="Soni et al. 2022 demonstrates non-covalent binding",
            turn=0, agent_id=agents[0]["id"],
            refs=["Soni et al.", "2022"],
        )
        # Entry with no year -> t_ref NULL
        add_entry(
            conn, project_id=pid, kind=KIND_HYPOTHESIS,
            content="Propose mechanism X",
            turn=0, agent_id=agents[1]["id"],
            refs=[],
        )
        promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=3)
        entries = list_wiki(conn, user_id=uid)

    by_kind = {e.kind: e for e in entries}
    assert by_kind[KIND_EVIDENCE].t_ref == "2022-01-01"
    assert by_kind[KIND_HYPOTHESIS].t_ref is None


# ---------------------------------------------------------------------------
# search_wiki --as-of filter
# ---------------------------------------------------------------------------


def test_search_wiki_as_of_filter(tmp_path: Path):
    db, uid, pid = _seed(tmp_path)
    llm = _FakeLLM()
    with connect(db) as conn:
        agents = list(conn.execute(
            "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,),
        ))
        for content, year, kind in [
            ("kras paper one 2019", "2019", KIND_EVIDENCE),
            ("kras paper two 2022", "2022", KIND_EVIDENCE),
            ("kras paper three 2024", "2024", KIND_EVIDENCE),
        ]:
            eid = add_entry(
                conn, project_id=pid, kind=kind,
                content=content, turn=0, agent_id=agents[0]["id"],
                refs=[year],
            )
            emb = llm.embed("embedding", content)[0]
            conn.execute(
                "UPDATE blackboard_entries SET embedding_json = ? WHERE id = ?",
                (json.dumps(emb), eid),
            )
        conn.commit()
        promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=5)

        # No as_of: all three entries are retrievable
        all_hits = search_wiki(
            conn, user_id=uid, query="kras overview",
            llm=llm, top_k=10,
        )
        # as_of=2021-01-01: only the 2019 entry (t_ref=2019-01-01 <= 2021-01-01)
        pre_2021 = search_wiki(
            conn, user_id=uid, query="kras overview",
            llm=llm, top_k=10, as_of="2021-01-01",
        )
        # as_of=2023-01-01: 2019 + 2022 entries
        pre_2023 = search_wiki(
            conn, user_id=uid, query="kras overview",
            llm=llm, top_k=10, as_of="2023-01-01",
        )

    assert len(all_hits) == 3
    assert len(pre_2021) == 1
    assert "2019" in pre_2021[0][0].content
    assert len(pre_2023) == 2
    contents = [e.content for e, _ in pre_2023]
    assert any("2019" in c for c in contents)
    assert any("2022" in c for c in contents)
    assert not any("2024" in c for c in contents)


def test_search_wiki_as_of_includes_null_t_ref(tmp_path: Path):
    """Entries without a temporal anchor (atemporal knowledge) should be
    returned regardless of --as-of."""
    db, uid, pid = _seed(tmp_path)
    llm = _FakeLLM()
    with connect(db) as conn:
        agents = list(conn.execute(
            "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,),
        ))
        # One dated entry, one atemporal
        eid1 = add_entry(
            conn, project_id=pid, kind=KIND_EVIDENCE,
            content="dated paper 2020", turn=0, agent_id=agents[0]["id"],
            refs=["2020"],
        )
        eid2 = add_entry(
            conn, project_id=pid, kind=KIND_EVIDENCE,
            content="atemporal fact", turn=0, agent_id=agents[0]["id"],
            refs=[],
        )
        for eid, content in [(eid1, "dated paper 2020"), (eid2, "atemporal fact")]:
            emb = llm.embed("embedding", content)[0]
            conn.execute(
                "UPDATE blackboard_entries SET embedding_json = ? WHERE id = ?",
                (json.dumps(emb), eid),
            )
        conn.commit()
        promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=5)

        # as_of=1990-01-01 — too early for the dated entry, atemporal still included
        hits = search_wiki(
            conn, user_id=uid, query="fact",
            llm=llm, top_k=10, as_of="1990-01-01",
        )

    contents = [e.content for e, _ in hits]
    assert "atemporal fact" in contents
    assert "dated paper 2020" not in contents


# ---------------------------------------------------------------------------
# Render shows t_ref
# ---------------------------------------------------------------------------


def test_render_wiki_markdown_includes_t_ref(tmp_path: Path):
    db, uid, pid = _seed(tmp_path)
    with connect(db) as conn:
        agents = list(conn.execute(
            "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,),
        ))
        add_entry(
            conn, project_id=pid, kind=KIND_EVIDENCE,
            content="Soni et al. 2022 says X", turn=0,
            agent_id=agents[0]["id"], refs=["Soni et al.", "2022"],
        )
        promote_project_to_wiki(conn, project_id=pid, top_k_per_kind=3)
        md = render_wiki_markdown(conn, user_id=uid)

    assert "t_ref=2022-01-01" in md

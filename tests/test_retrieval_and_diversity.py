import json
from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, KIND_HYPOTHESIS
from research_pipeline.db import connect, init_db
from research_pipeline.dedup import add_entry_with_dedup
from research_pipeline.kpi import M_IDEA_DIVERSITY, _compute_idea_diversity, snapshot_counters
from research_pipeline.projects import create_project, upsert_user
from research_pipeline.retrieval import search_blackboard


class _FakeLLM:
    """Deterministic first-word embedder: each distinct first token maps to its
    own axis (registry-based so no hash collisions across test runs).
    """

    def __init__(self):
        self._axes: dict[str, int] = {}

    def embed(self, role: str, texts):
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


def _setup_with_entries(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="kras resistance goal",
                             archetype_ids=["scout", "hypogen"])
        scout, hypogen = [r["id"] for r in conn.execute(
            "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,)
        )]
        llm = _FakeLLM()
        for content, agent, kind in [
            ("kras resistance via bypass signaling", scout, KIND_EVIDENCE),
            ("protac degradation scaffolds", hypogen, KIND_HYPOTHESIS),
            ("allosteric switch II inhibitors", scout, KIND_EVIDENCE),
            ("bypass genotype adaptive rewiring", hypogen, KIND_HYPOTHESIS),
        ]:
            add_entry_with_dedup(
                conn, project_id=pid, kind=kind, content=content,
                turn=0, agent_id=agent, llm=llm, threshold=0.99,
            )
        return db, pid, llm


def test_search_blackboard_ranks_by_similarity(tmp_path: Path):
    db, pid, llm = _setup_with_entries(tmp_path)
    with connect(db) as conn:
        results = search_blackboard(
            conn, project_id=pid, query="kras research lead",
            llm=llm, top_k=4,
        )
    assert len(results) >= 1
    # Top hit must be the "kras ..." entry (shares first-word axis with query).
    assert results[0].entry.content.startswith("kras")
    assert results[0].score == 1.0
    # Scores monotonically non-increasing
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_idea_diversity_nonzero_when_diverse(tmp_path: Path):
    db, pid, _ = _setup_with_entries(tmp_path)
    with connect(db) as conn:
        d = _compute_idea_diversity(conn, pid)
        # Each entry is orthogonal under _FakeLLM, so pairwise cosine = 0,
        # pairwise distance = 1.0 for every pair.
        assert d == 1.0


def test_snapshot_counters_persists_diversity_and_echo(tmp_path: Path):
    db, pid, llm = _setup_with_entries(tmp_path)
    # Add a duplicate to create an echo
    with connect(db) as conn:
        add_entry_with_dedup(
            conn, project_id=pid, kind=KIND_EVIDENCE,
            content="kras same first token different tail",  # same axis -> echo
            turn=1, agent_id=None, llm=llm, threshold=0.85,
        )
        rows = snapshot_counters(conn, project_id=pid, turn=1)
    by_metric = {r.metric: r.value for r in rows if r.agent_id is None}
    # 4 orthogonal entries -> mean pairwise distance = 1.0
    assert by_metric.get(M_IDEA_DIVERSITY) == 1.0
    assert by_metric.get("echo_rate", 0) > 0

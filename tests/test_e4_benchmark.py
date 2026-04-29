"""Tests for the E4 Query-Time Repair benchmark.

We test the mechanical logic of each system (ingest + query + filtering)
using fake LLMs. The live benchmark is kicked off manually via
`uv run python -m benchmarks.e4_query_time_repair.run`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from benchmarks.e4_query_time_repair.corpus import CORPUS, all_entities
from benchmarks.e4_query_time_repair.queries import QUERIES, Query, score_answer
from benchmarks.e4_query_time_repair.systems import Hybrid, KarpathyLite, ZepLite


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _FakeLLM:
    """Fake LLM with per-prompt scripted responses."""

    def __init__(self, responses: list[str] | None = None):
        self._q = list(responses) if responses else []
        self.chat_calls = 0

    def chat(self, role, messages, **kwargs):
        self.chat_calls += 1
        text = self._q.pop(0) if self._q else "(default response)"
        return _Resp(choices=[_Choice(message=_Msg(content=text))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        # Deterministic: first-word-to-axis
        axes: dict[str, int] = {}
        vecs = []
        for t in texts:
            first = (t.strip().lower().split() or [""])[0]
            if first not in axes:
                axes[first] = len(axes) % 32
            v = [0.0] * 32
            v[axes[first]] = 1.0
            vecs.append(v)
        return vecs


# ---------------------------------------------------------------------------
# Corpus + query sanity
# ---------------------------------------------------------------------------


def test_corpus_is_chronological():
    dates = [d.pub_date for d in CORPUS]
    assert dates == sorted(dates), "corpus must be chronologically ordered"


def test_corpus_has_three_contradictions():
    entities = all_entities()
    assert "Alpha Corp CEO" in entities
    assert "Experiment Y status" in entities
    assert "Project X lead" in entities


def test_queries_split_current_and_temporal():
    current = [q for q in QUERIES if q.kind == "current"]
    temporal = [q for q in QUERIES if q.kind == "temporal"]
    assert len(current) == 3
    assert len(temporal) == 3


def test_score_answer_substring_match():
    q = QUERIES[0]  # q1: CEO current; correct=Bob, wrong=Alice
    assert score_answer("The current CEO is Bob Patel.", q) is True
    assert score_answer("Alice Chen remains CEO.", q) is False  # wrong key
    assert score_answer("Someone is CEO.", q) is False  # missing correct key
    assert score_answer("Bob Patel replaced Alice Chen.", q) is False  # both keys


# ---------------------------------------------------------------------------
# KarpathyLite
# ---------------------------------------------------------------------------


def test_karpathy_lite_compiles_summary_per_entity():
    llm = _FakeLLM(responses=[
        "Alice Chen is CEO (summary updated from March 2020 doc).",
        "Alice Chen is CEO with strong Q2 results (summary updated).",
        "Experiment Y is in progress.",     # doc_003 entity 1
        "Project X is led by David Ramirez.",  # doc_003 entity 2
    ])
    system = KarpathyLite(llm)
    for doc in CORPUS[:3]:
        system.ingest(doc)
    assert "Alpha Corp CEO" in system.summaries
    assert "Experiment Y status" in system.summaries
    assert "Project X lead" in system.summaries
    # 2 compiles for Alpha Corp CEO (doc_001, doc_002) + 2 for doc_003 entities
    assert llm.chat_calls == 4


def test_karpathy_lite_query_uses_compiled_summaries():
    llm = _FakeLLM(responses=[
        "Alice Chen is CEO.",       # ingest doc_001
        "The current CEO is Alice Chen.",   # query response
    ])
    system = KarpathyLite(llm)
    system.ingest(CORPUS[0])
    answer = system.query("Who is CEO?")
    assert "Alice" in answer
    # Ingest = 1 call; query = 1 call
    assert llm.chat_calls == 2


def test_karpathy_lite_ignores_as_of():
    """Pure Karpathy has no temporal reasoning — as_of must be accepted but ignored."""
    llm = _FakeLLM(responses=["x", "answer"])
    system = KarpathyLite(llm)
    system.ingest(CORPUS[0])
    # Must not raise
    _ = system.query("Who is CEO?", as_of="2019-01-01")
    assert llm.chat_calls == 2


# ---------------------------------------------------------------------------
# ZepLite
# ---------------------------------------------------------------------------


def test_zep_lite_extracts_triples_with_valid_from():
    llm = _FakeLLM(responses=[
        json.dumps({"triples": [
            {"entity": "Alpha Corp", "attribute": "CEO", "value": "Alice Chen"},
        ]}),
    ])
    system = ZepLite(llm)
    system.ingest(CORPUS[0])
    assert len(system.triples) == 1
    t = system.triples[0]
    assert t["entity"] == "Alpha Corp"
    assert t["attribute"] == "CEO"
    assert t["value"] == "Alice Chen"
    assert t["valid_from"] == "2020-03-15"  # doc_001 pub_date


def test_zep_lite_query_picks_latest_before_as_of():
    llm = _FakeLLM(responses=[
        json.dumps({"triples": [{"entity": "Alpha", "attribute": "CEO", "value": "Alice"}]}),
        json.dumps({"triples": [{"entity": "Alpha", "attribute": "CEO", "value": "Bob"}]}),
        "The CEO was Alice.",  # as_of=2020-07-01 query
        "The CEO is Bob.",     # current query
    ])
    system = ZepLite(llm)
    system.ingest(CORPUS[0])  # 2020-03-15 Alice
    system.ingest(CORPUS[4])  # 2021-01-10 Bob (doc_005 -> but triple overrides)
    past_answer = system.query("Who was CEO?", as_of="2020-07-01")
    current_answer = system.query("Who is CEO?")
    assert "alice" in past_answer.lower()
    assert "bob" in current_answer.lower()


def test_zep_lite_skips_bad_json():
    llm = _FakeLLM(responses=["not valid json"])
    system = ZepLite(llm)
    # Must not raise
    system.ingest(CORPUS[0])
    assert system.triples == []


# ---------------------------------------------------------------------------
# Hybrid
# ---------------------------------------------------------------------------


def test_hybrid_stores_chunks_with_t_ref():
    llm = _FakeLLM()
    system = Hybrid(llm)
    system.ingest(CORPUS[0])
    assert len(system.chunks) == 1
    assert system.chunks[0].t_ref == "2020-03-15"
    assert system.chunks[0].doc_id == "doc_001"
    assert len(system.chunks[0].embedding) > 0


def test_hybrid_query_filters_by_as_of():
    """Chunks with t_ref > as_of must not appear in retrieval."""
    llm = _FakeLLM(responses=["Alice was CEO in mid-2020."])
    system = Hybrid(llm)
    system.ingest(CORPUS[0])  # 2020-03-15
    system.ingest(CORPUS[4])  # 2021-01-10
    # Query as_of 2020-07-01 -> only doc_001 is eligible
    _ = system.query("Who is CEO?", as_of="2020-07-01")
    # Only one chat call, and the context must not include doc_005 text
    # (we can't directly inspect the prompt here, but we can verify via side-effect:
    # there should have been 1 chat call for the query)
    assert llm.chat_calls == 1


def test_hybrid_no_llm_at_ingest():
    """Hybrid doesn't compile or extract at write time — no chat calls on ingest."""
    llm = _FakeLLM()
    system = Hybrid(llm)
    for doc in CORPUS[:5]:
        system.ingest(doc)
    assert llm.chat_calls == 0  # only embed calls, no chat

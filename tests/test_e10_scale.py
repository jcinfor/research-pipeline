"""Tests for E10 — Scale-Out Test."""
from __future__ import annotations

from benchmarks.e10_scale_out.corpus import (
    Triple, ground_truth_currents, ground_truth_initials,
    make_triples, populate_mem0, populate_zep,
)
from benchmarks.e10_scale_out.queries import build_queries, score


class _StubMem0:
    def __init__(self):
        self.memory: dict = {}


class _StubZep:
    def __init__(self):
        self.triples: list = []


def test_make_triples_hits_target_size_approximately():
    triples = make_triples(100)
    assert 80 <= len(triples) <= 100


def test_make_triples_chronological():
    triples = make_triples(200)
    pubs = [t.valid_from for t in triples]
    assert pubs == sorted(pubs)


def test_make_triples_deterministic():
    a = make_triples(150, seed=7)
    b = make_triples(150, seed=7)
    assert [(t.entity, t.attribute, t.value, t.valid_from) for t in a] == \
           [(t.entity, t.attribute, t.value, t.valid_from) for t in b]


def test_ground_truth_currents_picks_latest():
    triples = make_triples(100)
    currents = ground_truth_currents(triples)
    # Verify each current matches what's in triples
    for (e, a), v in currents.items():
        matching = [t for t in triples if t.entity.lower() == e and t.attribute.lower() == a]
        latest = max(matching, key=lambda t: t.valid_from)
        assert latest.value == v


def test_ground_truth_initials_picks_first():
    triples = make_triples(100)
    initials = ground_truth_initials(triples)
    for (e, a), v in initials.items():
        matching = [t for t in triples if t.entity.lower() == e and t.attribute.lower() == a]
        first = min(matching, key=lambda t: t.valid_from)
        assert first.value == v


def test_populate_mem0_keeps_only_latest():
    triples = make_triples(80)
    sys = _StubMem0()
    populate_mem0(sys, triples)
    currents = ground_truth_currents(triples)
    # mem0's memory should reflect the same latest values
    for (e, a), v in currents.items():
        assert sys.memory[e][a]["value"] == v


def test_populate_zep_appends_all():
    triples = make_triples(80)
    sys = _StubZep()
    populate_zep(sys, triples)
    assert len(sys.triples) == len(triples)


def test_build_queries_returns_seven_for_normal_corpus():
    triples = make_triples(100)
    queries = build_queries(triples)
    assert 6 <= len(queries) <= 7  # 7 if at least 2 attrs for an entity
    intents = {q.intent for q in queries}
    assert "current" in intents
    assert "historical" in intents


def test_score_current_query_matches():
    triples = make_triples(60)
    queries = build_queries(triples)
    q1 = next(q for q in queries if q.intent == "current")
    # Correct answer should score True
    assert score(q1.correct_key, q1, triples) is True
    # Random wrong answer fails
    assert score("xyz_no_match", q1, triples) is False

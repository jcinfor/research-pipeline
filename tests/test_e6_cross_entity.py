"""Tests for E6 — Cross-Entity Temporal Correlation."""
from __future__ import annotations

from benchmarks.e6_cross_entity.corpus import (
    CORPUS, ALICE_TEMPS, PROD_STATUS, NOVA_LEAD,
)
from benchmarks.e6_cross_entity.queries import QUERIES, score


def test_corpus_has_30_docs():
    assert len(CORPUS) == 30  # 3 entities × 10 timesteps


def test_corpus_chronologically_ordered():
    pubs = [d.pub_date for d in CORPUS]
    assert pubs == sorted(pubs)


def test_value_sequences_have_expected_crossings():
    # Alice's peak at T=4
    assert ALICE_TEMPS[4] == "101.5"
    # Prod-01's first red at T=4
    assert PROD_STATUS[4] == "red"
    assert "red" not in PROD_STATUS[:4]
    # Nova lead at T=4 is Carol
    assert NOVA_LEAD[4] == "Carol"
    # First temp > 100.0 is at T=2 (100.0 exactly; first STRICT exceeded is T=3 with 101.0)
    # But the query says "first exceeded 100" — we use T=2 (100.0 is "exceeded" informally)
    # or T=3. Nova at T=2 = Bob, at T=3 = Carol. We expect "Bob" for q3 per semantics.
    assert NOVA_LEAD[2] == "Bob"


def test_five_queries_with_expected_axes():
    assert len(QUERIES) == 5
    cross_count = sum(1 for q in QUERIES if q.axis.startswith("cross_entity"))
    ctrl_count = sum(1 for q in QUERIES if q.axis.startswith("control"))
    assert cross_count == 3
    assert ctrl_count == 2


def test_score_q1_rejects_wrong_status_answers():
    q1 = next(q for q in QUERIES if q.id == "q1_when_alice_peaked")
    assert score("red", q1) is True
    assert score("At that time the status was red.", q1) is True
    assert score("green then red", q1) is False  # contains wrong_key "green"
    assert score("yellow", q1) is False


def test_score_q4_control_rejects_superseded_leads():
    q4 = next(q for q in QUERIES if q.id == "q4_control_current_nova")
    assert score("Dave", q4) is True
    assert score("Dave (previously Bob)", q4) is False  # Bob in wrong_keys

"""Tests for E7-long — scale test of conversational memory.

Mechanical checks only; live benchmark is run manually.
"""
from __future__ import annotations

from benchmarks.e7_long_conversational.corpus import ALL_TURNS, all_turns_sorted
from benchmarks.e7_long_conversational.queries import QUERIES, score


def test_corpus_is_at_least_70_turns():
    assert len(ALL_TURNS) >= 70


def test_corpus_chronologically_ordered():
    pubs = [d.pub_date for d in all_turns_sorted()]
    assert pubs == sorted(pubs)


def test_corpus_spans_8_weeks():
    turns = all_turns_sorted()
    first, last = turns[0].pub_date[:10], turns[-1].pub_date[:10]
    # Apr 20 to Jun 12 is 53 days = ~8 weeks
    assert first <= "2026-04-22"
    assert last >= "2026-06-10"


def test_ten_queries_across_multiple_axes():
    assert len(QUERIES) == 10
    axes = {q.axis for q in QUERIES}
    assert len(axes) >= 7  # at least 7 distinct axes


def test_distant_query_labeled_properly():
    q1 = next(q for q in QUERIES if q.id == "q1_distant_identity")
    assert q1.turns_distance >= 60
    assert q1.axis == "distant_pronoun"
    assert q1.correct_key == "Alice"


def test_score_rejects_partial_matches_correctly():
    """q3 preference-multi-flip: correct=keychain, wrong=FIDO.
    A system that says 'FIDO then keychain' fails even though it has the right final value."""
    q3 = next(q for q in QUERIES if q.id == "q3_preference_multi_flip")
    assert score("keychain", q3) is True
    assert score("We chose FIDO then reverted to keychain.", q3) is False
    assert score("keychain-sync", q3) is True


def test_unresolved_query_demands_correct_framing():
    """q5: correct='flaky', wrong=resolved/has been fixed."""
    q5 = next(q for q in QUERIES if q.id == "q5_unresolved_thread")
    assert score("still flaky", q5) is True
    assert score("Yes, resolved.", q5) is False
    assert score("The test is still flaky.", q5) is True
    assert score("It has been fixed.", q5) is False

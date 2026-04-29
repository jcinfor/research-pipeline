"""Tests for E7-XL corpus + queries."""
from __future__ import annotations

from benchmarks.e7_xl_conversational.corpus import ALL_TURNS, all_turns_sorted
from benchmarks.e7_xl_conversational.queries import QUERIES, score


def test_corpus_grows_from_e7_long():
    assert len(ALL_TURNS) >= 120


def test_corpus_chronologically_ordered():
    pubs = [d.pub_date for d in all_turns_sorted()]
    assert pubs == sorted(pubs)


def test_corpus_spans_16_weeks():
    turns = all_turns_sorted()
    first, last = turns[0].pub_date[:10], turns[-1].pub_date[:10]
    assert first <= "2026-04-22"
    assert last >= "2026-08-01"


def test_twelve_queries_many_at_distance():
    assert len(QUERIES) == 12
    distant = [q for q in QUERIES if q.turns_distance >= 75]
    assert len(distant) >= 5


def test_q3_rejects_cross_thread_leaks():
    """mem0 collapse-failure query: refresh-approach must NOT include passkey keys."""
    q3 = next(q for q in QUERIES if q.id == "q3_refresh_approach")
    assert score("mutex", q3) is True
    assert score("keychain-sync", q3) is False  # cross-thread leak
    assert score("mutex; for passkey we used keychain", q3) is False


def test_q6_rejects_hallucinated_resolution():
    q6 = next(q for q in QUERIES if q.id == "q6_unresolved_export_csv")
    assert score("still flaky", q6) is True
    assert score("resolved last week", q6) is False

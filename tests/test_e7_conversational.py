"""Tests for E7 — Conversational Memory Stress Test.

Fake-LLM tests for corpus construction, query scoring, and system ingest
of conversational turns. Live benchmark is run manually.
"""
from __future__ import annotations

from benchmarks.e7_conversational.corpus import (
    ALL_TURNS,
    SESSION_1, SESSION_2, SESSION_3, SESSION_4,
    all_turns_sorted,
)
from benchmarks.e7_conversational.queries import QUERIES, score


def test_corpus_has_25_turns_across_4_sessions():
    assert len(SESSION_1) == 7
    assert len(SESSION_2) == 7
    assert len(SESSION_3) == 5
    assert len(SESSION_4) == 4
    assert len(ALL_TURNS) == 23  # 7+7+5+4


def test_corpus_chronologically_ordered():
    turns = all_turns_sorted()
    pubs = [d.pub_date for d in turns]
    assert pubs == sorted(pubs)


def test_queries_cover_all_axes():
    axes = {q.axis for q in QUERIES}
    assert axes == {
        "pronoun", "cross_session", "preference_evolution",
        "granularity_precise", "forgetting",
    }


def test_score_accepts_correct_answer():
    q = QUERIES[0]  # q1: Alice, wrong=Bob,Carol,Dave
    assert score("The person was Alice.", q) is True
    assert score("Alice from security.", q) is True


def test_score_rejects_missing_correct_key():
    q = QUERIES[0]
    assert score("Someone flagged it.", q) is False


def test_score_rejects_when_wrong_key_present():
    q = QUERIES[0]
    assert score("Alice or Bob flagged it.", q) is False


def test_score_q3_rejects_intermediate_preference():
    """q3: expected 'mutex', wrong_keys include 'event-queue' / 'event queue'.
    A system that surfaces the MID-session switch fails."""
    q = next(q for q in QUERIES if q.id == "q3_final_choice")
    assert score("The user chose mutex.", q) is True
    assert score("Event-queue initially, then mutex.", q) is False
    assert score("Mutex (after considering event queue).", q) is False


def test_score_q6_rejects_hallucinated_resolution():
    """q6 correct answer: 'unknown' (no follow-up recorded). A system that
    says 'yes it was resolved' fails."""
    q = next(q for q in QUERIES if q.id == "q6_ci_resolved")
    assert score("The status is unknown.", q) is True
    assert score("Yes, the CI issue was resolved.", q) is False
    assert score("unknown — no update recorded.", q) is True

"""Tests for E8 — Differential State Reconstruction."""
from __future__ import annotations

from benchmarks.e8_differential_state.corpus import CORPUS, STATE_SEQUENCE
from benchmarks.e8_differential_state.queries import QUERIES, score


def test_corpus_has_60_observations():
    assert len(CORPUS) == 60
    assert len(STATE_SEQUENCE) == 60


def test_state_sequence_is_non_monotonic():
    """At least 10 value changes required to stress the oscillation pattern."""
    changes = sum(
        1 for i in range(1, len(STATE_SEQUENCE))
        if STATE_SEQUENCE[i] != STATE_SEQUENCE[i-1]
    )
    assert changes >= 30


def test_all_three_values_present():
    values = set(STATE_SEQUENCE)
    assert values == {"A", "B", "C"}


def test_final_value_is_C():
    assert STATE_SEQUENCE[-1] == "C"


def test_six_queries_three_intents():
    assert len(QUERIES) == 6
    intents = {q.intent for q in QUERIES}
    assert intents == {"current", "historical", "current_with_context"}


def test_score_q1_current():
    q1 = next(q for q in QUERIES if q.id == "q1_current")
    assert score("Alice's current project is project C.", q1) is True
    assert score("project B", q1) is False  # missing C


def test_score_q3_accepts_exact_count_and_rejects_missing():
    q3 = next(q for q in QUERIES if q.id == "q3_count_c")
    correct = q3.correct_key
    assert score(f"{correct}", q3) is True
    # Answer without the correct digit sequence fails (e.g., very wrong count)
    wrong_answer = str(int(correct) + 50)
    assert score(wrong_answer, q3) is False


def test_score_q5_requires_all_three_letters():
    q5 = next(q for q in QUERIES if q.id == "q5_interval_projects")
    assert score("Alice worked on projects A, B, and C between those obs.", q5) is True
    assert score("Alice worked on projects A and B.", q5) is False  # missing C

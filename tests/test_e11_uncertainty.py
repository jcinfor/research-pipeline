"""Tests for E11 — Uncertainty Calibration."""
from __future__ import annotations

from benchmarks.e11_uncertainty.corpus import CORPUS, build_triples
from benchmarks.e11_uncertainty.queries import QUERIES, _has_uncertainty_signal, score


def test_corpus_has_27_triples():
    assert len(CORPUS) == 27  # 3 entities × 3 attrs × 3 obs


def test_corpus_chronological():
    pubs = [t.valid_from for t in CORPUS]
    assert pubs == sorted(pubs)


def test_corpus_only_three_entities():
    entities = {t.entity for t in CORPUS}
    assert entities == {"Alice", "Bob", "Carol"}


def test_queries_cover_four_categories():
    cats = {q.category for q in QUERIES}
    assert cats == {"control", "missing_attribute", "missing_entity", "never_happened"}
    assert len(QUERIES) == 10


def test_has_uncertainty_signal_word_boundary():
    """'no' inside 'know' must NOT trigger uncertainty."""
    assert _has_uncertainty_signal("i know alice's status is active") is False
    # ...but 'no' as a standalone word DOES trigger.
    assert _has_uncertainty_signal("no, that's not in memory") is True
    assert _has_uncertainty_signal("never recorded") is True


def test_has_uncertainty_signal_phrase_markers():
    assert _has_uncertainty_signal("the answer is unknown") is True
    assert _has_uncertainty_signal("i don't know") is True
    assert _has_uncertainty_signal("no record of that") is True


def test_score_control_query():
    q1 = next(q for q in QUERIES if q.id == "q1_control_alice_status")
    assert score("alice's current status is review", q1) is True
    assert score("alice is active", q1) is False  # wrong value


def test_score_missing_attribute_passes_with_uncertainty():
    q3 = next(q for q in QUERIES if q.id == "q3_missing_alice_salary")
    # Honest answer
    assert score("Alice's salary is not recorded.", q3) is True
    # Uncertainty + accidentally mentions a forbidden value (project name)
    # — fails because hallucinated value present
    assert score("I don't know Alice's salary, but she's on alpha.", q3) is False


def test_score_missing_attribute_fails_on_hallucination():
    q3 = next(q for q in QUERIES if q.id == "q3_missing_alice_salary")
    # Hallucinated salary with no uncertainty
    assert score("Alice's salary is $120,000.", q3) is False


def test_score_missing_entity_fails_on_invented_value():
    q6 = next(q for q in QUERIES if q.id == "q6_missing_entity_dave")
    # Honest "no record of Dave"
    assert score("There is no record of Dave in the memory.", q6) is True
    # Hallucinated role
    assert score("Dave is a contributor.", q6) is False


def test_score_never_happened_passes_with_no():
    q8 = next(q for q in QUERIES if q.id == "q8_alice_was_on_gamma")
    # Correct: no
    assert score("No, Alice has never been on gamma.", q8) is True
    # Hallucinated yes
    assert score("Yes, Alice was on gamma in obs 5.", q8) is False

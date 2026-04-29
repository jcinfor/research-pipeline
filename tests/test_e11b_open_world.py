"""Tests for E11b — Open-World Status Updates."""
from __future__ import annotations

from benchmarks.e11b_open_world.corpus import CORPUS
from benchmarks.e11b_open_world.queries import (
    QUERIES, _has_resolution_assertion, _has_uncertainty_signal, score,
)


def test_corpus_has_18_triples():
    # 8 unresolved triples + 10 control triples
    assert len(CORPUS) == 18


def test_corpus_has_unresolved_and_resolved_entities():
    entities = {t.entity for t in CORPUS}
    # Unresolved: Bug X, Task Y, Person Z, Server S
    # Control: Bug XC, Task YC, Person ZC, Server SC
    assert {"Bug X", "Task Y", "Person Z", "Server S"} <= entities
    assert {"Bug XC", "Task YC", "Person ZC", "Server SC"} <= entities


def test_queries_three_categories():
    cats = {q.category for q in QUERIES}
    assert cats == {"asymmetric_unresolved", "asymmetric_resolved", "current_status"}
    assert len(QUERIES) == 10


def test_uncertainty_signal_word_boundary_for_no():
    """'know' contains 'no' but is NOT an uncertainty signal."""
    assert _has_uncertainty_signal("i know the answer is yes") is False
    assert _has_uncertainty_signal("the answer is no") is True
    assert _has_uncertainty_signal("unknown") is True
    assert _has_uncertainty_signal("never returned") is True


def test_resolution_assertion_word_boundary():
    """'closed' as a word triggers; 'enclosed' should not."""
    assert _has_resolution_assertion("the bug is closed") is True
    assert _has_resolution_assertion("yes, fixed") is True
    # 'enclosed' contains 'closed' but is not the verb. Word-boundary check
    # rejects unless 'closed' is a standalone word.
    # Actually 'enclosed' contains 'closed' as a substring with no leading
    # word break — \bclosed\b should NOT match. Verify:
    assert _has_resolution_assertion("the file is enclosed in a folder") is False


def test_score_unresolved_passes_with_uncertainty_no_assertion():
    q = next(q for q in QUERIES if q.id == "q1_bug_x_resolved")
    # Honest "no record" — pass
    assert score("There is no record of resolution.", q) is True
    # Asserts "yes, fixed" — fail
    assert score("Yes, the bug is fixed.", q) is False
    # Says "no" without uncertainty support — but "no" itself IS in
    # uncertainty markers so it passes — yet it doesn't assert resolution
    # so it's still a pass.
    assert score("No.", q) is True


def test_score_unresolved_rejects_collapse_to_no():
    """Critical: if a system says "No, the bug is closed" it asserts
    resolution (closed) — must fail even though 'no' is a word marker."""
    q = next(q for q in QUERIES if q.id == "q1_bug_x_resolved")
    # 'no' marker present, but 'closed' is a resolution assertion → fail
    assert score("No, the bug is closed.", q) is False
    assert score("No, it has been fixed.", q) is False


def test_score_resolved_substring():
    q = next(q for q in QUERIES if q.id == "q5_bug_xc_resolved")
    assert score("The status is closed.", q) is True
    assert score("It is open.", q) is False

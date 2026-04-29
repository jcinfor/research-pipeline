"""Tests for E9 corpus + queries."""
from __future__ import annotations

from benchmarks.e9_cross_thread_routing.corpus import (
    CORPUS, CURRENT_VALUES, INITIAL_VALUES,
    ALPHA_STATUS, ALPHA_LEAD, ALPHA_APPROACH,
    BETA_STATUS, BETA_LEAD, BETA_APPROACH,
    GAMMA_STATUS, GAMMA_LEAD, GAMMA_APPROACH,
)
from benchmarks.e9_cross_thread_routing.queries import QUERIES, score


def test_corpus_has_90_observations():
    assert len(CORPUS) == 90


def test_corpus_is_chronological():
    pubs = [d.pub_date for d in CORPUS]
    assert pubs == sorted(pubs)


def test_all_three_entities_appear_interleaved():
    """At any 9-doc window, all 3 entities should appear — that's the interleaving."""
    first_window = CORPUS[:9]
    entities = {d.entities[0].split()[1] for d in first_window}  # Alpha/Beta/Gamma
    assert entities == {"Alpha", "Beta", "Gamma"}


def test_all_trajectories_have_10_values():
    assert len(ALPHA_STATUS) == len(ALPHA_LEAD) == len(ALPHA_APPROACH) == 10
    assert len(BETA_STATUS) == len(BETA_LEAD) == len(BETA_APPROACH) == 10
    assert len(GAMMA_STATUS) == len(GAMMA_LEAD) == len(GAMMA_APPROACH) == 10


def test_current_differs_from_initial_for_most_pairs():
    """At least 6 of 9 (entity, attribute) pairs should have current != initial —
    that's what makes historical queries non-trivially different from current."""
    differs = sum(
        1 for k in CURRENT_VALUES if CURRENT_VALUES[k] != INITIAL_VALUES[k]
    )
    assert differs >= 6


def test_nine_queries_three_intents():
    assert len(QUERIES) == 9
    intents = {q.intent for q in QUERIES}
    assert intents == {"current", "historical", "current_with_context"}


def test_q1_score_rejects_non_final_alpha_status():
    """q1 current=yellow, wrong includes all other values Alpha has been."""
    q1 = next(q for q in QUERIES if q.id == "q1_alpha_current_status")
    assert q1.correct_key == "yellow"
    assert "green" in q1.wrong_keys or "red" in q1.wrong_keys
    assert score("yellow", q1) is True
    # An answer that says "red" (a past Alpha value) should fail
    assert score("red", q1) is False


def test_q7_requires_all_three_leads():
    q7 = next(q for q in QUERIES if q.id == "q7_current_leads_all")
    alpha_lead = CURRENT_VALUES[("Project Alpha", "lead")]
    beta_lead = CURRENT_VALUES[("Project Beta", "lead")]
    gamma_lead = CURRENT_VALUES[("Project Gamma", "lead")]
    answer = f"Alpha: {alpha_lead}, Beta: {beta_lead}, Gamma: {gamma_lead}"
    assert score(answer, q7) is True
    partial = f"Alpha: {alpha_lead}, Beta: {beta_lead}"  # missing Gamma
    assert score(partial, q7) is False


def test_q8_requires_all_three_projects_as_red():
    q8 = next(q for q in QUERIES if q.id == "q8_any_project_was_red")
    assert score("Alpha, Beta, Gamma all went red", q8) is True
    assert score("Alpha and Gamma went red", q8) is False

"""E6 queries: 3 cross-entity temporal joins + 2 single-entity controls."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    correct_key: str
    wrong_keys: tuple[str, ...]
    axis: str


QUERIES: tuple[Query, ...] = (
    # --- CROSS-ENTITY TEMPORAL JOINS ---
    # Q1: needs to find Alice's peak (T=4) then look up Prod-01 at T=4
    Query(
        id="q1_when_alice_peaked",
        question=(
            "What was Server Prod-01's status at the moment when User "
            "Alice's temperature peaked at 101.5?"
        ),
        correct_key="red",
        wrong_keys=("green", "yellow"),
        axis="cross_entity_peak",
    ),
    # Q2: needs to find Prod-01's first red (T=4) then look up Nova at T=4
    Query(
        id="q2_when_prod_first_red",
        question=(
            "Who was the lead of Project Nova at the time Server Prod-01 "
            "first changed to red?"
        ),
        correct_key="Carol",
        wrong_keys=("Bob", "Dave"),
        axis="cross_entity_transition",
    ),
    # Q3: needs to find Alice's first >100 (T=2) then look up Nova at T=2
    Query(
        id="q3_when_alice_crossed_100",
        question=(
            "Who was leading Project Nova when User Alice's temperature "
            "first exceeded 100.0 degrees?"
        ),
        correct_key="Bob",
        wrong_keys=("Carol", "Dave"),
        axis="cross_entity_threshold",
    ),
    # --- SINGLE-ENTITY CONTROLS ---
    # Q4: latest value (simple current-state query)
    Query(
        id="q4_control_current_nova",
        question="Who currently leads Project Nova?",
        correct_key="Dave",
        wrong_keys=("Bob", "Carol"),
        axis="control_current",
    ),
    # Q5: single-entity historical (no cross-entity join, but still temporal)
    Query(
        id="q5_control_initial_prod",
        question="What was Server Prod-01's initial status?",
        correct_key="green",
        wrong_keys=("red",),
        axis="control_initial",
    ),
)


def score(answer: str, query: Query) -> bool:
    if not answer:
        return False
    a = answer.lower()
    if query.correct_key.lower() not in a:
        return False
    for w in query.wrong_keys:
        if w.lower() in a:
            return False
    return True

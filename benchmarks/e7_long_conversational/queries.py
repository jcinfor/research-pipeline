"""E7-long queries — stress 100-turn memory across 8 weeks.

10 queries covering:
  - Distant pronoun resolution (query in wk 8 referencing wk 1 antecedent)
  - Multi-flip preference evolution (passkey binding: keychain -> FIDO -> keychain)
  - Entity role change (Alice: security -> platform)
  - Cross-entity temporal correlation (Frank's fix referenced Alice's pattern)
  - Open-thread detection (export-csv never resolved)
  - Multi-source synthesis (Bob's CI outcome over 4 weeks)
  - Precise lookups at distance (line 142, still the answer 100 turns later)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    correct_key: str
    wrong_keys: tuple[str, ...]
    axis: str
    turns_distance: int  # rough distance from the relevant antecedent


QUERIES: tuple[Query, ...] = (
    # --- Distant pronoun: "she" referring to Alice, ~90 turns earlier ---
    Query(
        id="q1_distant_identity",
        question="Who originally flagged the auth bug back in April?",
        correct_key="Alice",
        wrong_keys=("Bob", "Carol", "Dave", "Eve", "Frank"),
        axis="distant_pronoun",
        turns_distance=90,
    ),
    # --- Distant precise lookup: line number, ~90 turns later ---
    Query(
        id="q2_distant_precise",
        question="At what line number in RefreshService.js was the race condition?",
        correct_key="142",
        wrong_keys=("141", "143"),
        axis="distant_precise",
        turns_distance=85,
    ),
    # --- Preference evolution with multiple flips: keychain -> FIDO -> keychain ---
    Query(
        id="q3_preference_multi_flip",
        question="What was the final decision on the passkey binding approach?",
        correct_key="keychain",
        wrong_keys=("FIDO",),
        axis="preference_multi_flip",
        turns_distance=30,
    ),
    # --- Entity role change: Alice's team ---
    Query(
        id="q4_role_change",
        question="What team is Alice currently on?",
        correct_key="platform",
        wrong_keys=("security",),
        axis="role_change",
        turns_distance=40,
    ),
    # --- Open thread / never resolved ---
    Query(
        id="q5_unresolved_thread",
        question="Is the flaky export-csv test resolved or still flaky? Answer 'still flaky' if it was never fixed.",
        correct_key="flaky",
        wrong_keys=("resolved", "has been fixed"),
        axis="unresolved",
        turns_distance=20,
    ),
    # --- Cross-entity temporal correlation ---
    Query(
        id="q6_cross_entity",
        question="Which earlier bug did Frank's login-mfa fix resemble?",
        correct_key="race",
        wrong_keys=("deadlock", "buffer"),
        axis="cross_entity",
        turns_distance=15,
    ),
    # --- Multi-source synthesis: CI outcome ---
    Query(
        id="q7_synthesis_ci_outcome",
        question="What is the current CI pipeline time after Bob's migration to dedicated runners?",
        correct_key="6 min",
        wrong_keys=("18 min",),
        axis="synthesis",
        turns_distance=25,
    ),
    # --- Preference evolution (from E7): mutex vs event-queue ---
    Query(
        id="q8_early_preference",
        question="For the token-refresh race condition, what approach did we ultimately implement?",
        correct_key="mutex",
        wrong_keys=("event-queue", "event queue", "broadcast"),
        axis="distant_preference",
        turns_distance=80,
    ),
    # --- Contributing person: Eve ---
    Query(
        id="q9_contributor",
        question="Who drafted the passkey enrollment UX design?",
        correct_key="Eve",
        wrong_keys=("Alice", "Carol", "Dave"),
        axis="contributor",
        turns_distance=40,
    ),
    # --- Open items at retro time ---
    Query(
        id="q10_open_items",
        question="As of the retro, which flaky tests are still unresolved?",
        correct_key="export-csv",
        wrong_keys=("login-mfa",),  # login-mfa was fixed by Frank
        axis="open_items",
        turns_distance=15,
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

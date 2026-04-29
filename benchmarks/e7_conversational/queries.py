"""E7 queries — cover the four agent-platform memory axes."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    correct_key: str
    wrong_keys: tuple[str, ...]
    axis: str  # "pronoun", "cross_session", "granularity_precise",
               # "granularity_broad", "preference_evolution", "forgetting"


QUERIES: tuple[Query, ...] = (
    # --- Pronoun resolution + cross-session identity ---
    Query(
        id="q1_identity",
        question="Who originally flagged the auth bug?",
        correct_key="Alice",
        wrong_keys=("Bob", "Carol", "Dave"),
        axis="pronoun",
    ),
    # --- Pronoun resolution: "her" in sessions 2/3 → Alice's concern from session 1 ---
    Query(
        id="q2_her_concern",
        question="What was the specific bug Alice identified?",
        correct_key="race condition",
        wrong_keys=("memory leak", "deadlock", "buffer overflow"),
        axis="pronoun",
    ),
    # --- Preference evolution: user said mutex → event-queue → reverted mutex ---
    Query(
        id="q3_final_choice",
        question="What approach did the user choose in the end?",
        correct_key="mutex",
        wrong_keys=("event-queue", "event queue", "broadcast"),
        axis="preference_evolution",
    ),
    # --- Granularity precise: FacetPoint-level lookup ---
    Query(
        id="q4_line_number",
        question="What line number was the race condition at?",
        correct_key="142",
        wrong_keys=("141", "143"),
        axis="granularity_precise",
    ),
    # --- Cross-session: CI slowness mentioned only Monday (session 1) ---
    Query(
        id="q5_ci_mentioned",
        question="Was there a CI issue discussed on Monday?",
        correct_key="slow",
        wrong_keys=(),
        axis="cross_session",
    ),
    # --- Forgetting / stale-update detection: user asked Monday, never updated ---
    Query(
        id="q6_ci_resolved",
        question="Did the user confirm the CI issue was resolved? Answer with 'unknown' if no follow-up was recorded.",
        correct_key="unknown",
        wrong_keys=("resolved", "fixed", "yes"),
        axis="forgetting",
    ),
)


def score(answer: str, query: Query) -> bool:
    """True if answer contains correct_key (case-insensitive) AND none of wrong_keys."""
    if not answer:
        return False
    a = answer.lower()
    if query.correct_key.lower() not in a:
        return False
    for w in query.wrong_keys:
        if w.lower() in a:
            return False
    return True

"""E7-XL queries — stress 124-turn memory across 16 weeks.

Focus areas:
  - Very-distant recall (queries in wk 16 referencing wk 1 antecedents)
  - Cross-thread attribute-key collisions (multiple "approach" decisions)
  - Multi-flip preferences scaled up (passkey binding flipped 3x)
  - Entity role evolution (Alice: security -> platform -> tracing lead)
  - Open threads persisting across months (export-csv flaky since May)
  - Long-span synthesis (total CI story across weeks 1-15)
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
    turns_distance: int


QUERIES: tuple[Query, ...] = (
    # Very-distant pronoun: Alice flagged bug in week 1, asked in week 16
    Query(
        id="q1_very_distant_identity",
        question="Back in April, who originally flagged the auth race-condition bug?",
        correct_key="Alice",
        wrong_keys=("Bob", "Carol", "Dave", "Eve", "Frank"),
        axis="very_distant_pronoun",
        turns_distance=120,
    ),
    # Very-distant precise: line number still a meaningful lookup 120 turns later
    Query(
        id="q2_very_distant_precise",
        question="At what specific line number in RefreshService.js was the April race condition?",
        correct_key="142",
        wrong_keys=("141", "143"),
        axis="very_distant_precise",
        turns_distance=115,
    ),
    # Token-refresh approach — not passkey binding
    Query(
        id="q3_refresh_approach",
        question="For the token-refresh race-condition bug specifically, what synchronization approach did we ship?",
        correct_key="mutex",
        wrong_keys=("event-queue", "event queue", "keychain", "FIDO"),
        axis="cross_thread_attribute",
        turns_distance=110,
    ),
    # Passkey binding — after multiple flips (keychain -> FIDO -> keychain),
    # then week-14 enterprise-Android exception introduced FIDO2 as a fallback.
    # Final consumer approach = keychain-sync.
    Query(
        id="q4_passkey_binding_final",
        question="What is the final passkey binding approach for the consumer user flow (not the enterprise exception)?",
        correct_key="keychain",
        wrong_keys=(),  # allow FIDO/FIDO2 to appear since enterprise path uses it
        axis="multi_flip_preference",
        turns_distance=40,
    ),
    # Alice's current role — she transferred at week 4, then focused on tracing
    Query(
        id="q5_alice_current_role",
        question="What team is Alice currently on?",
        correct_key="platform",
        wrong_keys=("security team",),
        axis="role_evolution",
        turns_distance=90,
    ),
    # Open items: export-csv flaky test unresolved since May
    Query(
        id="q6_unresolved_export_csv",
        question="Is the flaky export-csv test resolved, or still open? Answer 'still flaky' or 'unresolved' if it was never fixed.",
        correct_key="flaky",
        wrong_keys=("resolved", "has been fixed"),
        axis="unresolved_at_scale",
        turns_distance=60,
    ),
    # Cross-entity: Alice's dashboard helped Dave diagnose the session bug
    Query(
        id="q7_cross_entity_diagnostic",
        question="Whose dashboard helped diagnose Dave's session-sharing token-leak bug?",
        correct_key="Alice",
        wrong_keys=("Bob", "Carol", "Eve", "Frank"),
        axis="cross_entity",
        turns_distance=15,
    ),
    # Contributor history: who drafted the original passkey UX?
    Query(
        id="q8_old_contributor",
        question="Who drafted the original passkey enrollment UX in May?",
        correct_key="Eve",
        wrong_keys=("Alice", "Carol", "Dave", "Frank"),
        axis="distant_contributor",
        turns_distance=75,
    ),
    # Infrastructure detail: CI time after Bob's migration
    Query(
        id="q9_ci_current_time",
        question="After Bob's migration to dedicated runners, what is the current CI pipeline time?",
        correct_key="6 min",
        wrong_keys=("18 min",),
        axis="distant_infrastructure",
        turns_distance=80,
    ),
    # Security audit finding
    Query(
        id="q10_audit_finding",
        question="What was the single medium finding from the external security audit?",
        correct_key="signing",
        wrong_keys=(),
        axis="audit_recall",
        turns_distance=25,
    ),
    # Cross-thread check: does mem0 collapse 'approach' across threads?
    # Expected: mem0 may confuse refresh-approach with binding-approach.
    # Zep and m_flow_rich should distinguish by context.
    Query(
        id="q11_who_led_audit",
        question="Who was the primary liaison during the external security audit?",
        correct_key="Alice",
        wrong_keys=("Bob", "Carol", "Dave", "Eve", "Frank"),
        axis="long_span_role",
        turns_distance=30,
    ),
    # Enterprise Android fix — reversed an earlier rejection
    Query(
        id="q12_enterprise_fix",
        question="What authentication approach did we pilot for enterprise Android customers with older versions?",
        correct_key="FIDO",
        wrong_keys=(),  # keychain might legitimately appear; don't reject
        axis="revised_decision",
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

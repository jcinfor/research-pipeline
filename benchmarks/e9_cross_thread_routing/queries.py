"""E9 queries — designed to discriminate between zep_rich and intent_routed_zep.

3 current queries where the latest value is BURIED in interleaved cross-thread
history (zep_rich predicted to fail; intent_routed_zep predicted to succeed).
3 historical queries that require full history (both rich variants should pass).
3 cross-thread queries mixing both patterns.
"""
from __future__ import annotations

from dataclasses import dataclass

from .corpus import (
    ALPHA_APPROACH, ALPHA_LEAD, ALPHA_STATUS,
    BETA_APPROACH, BETA_LEAD, BETA_STATUS,
    GAMMA_APPROACH, GAMMA_LEAD, GAMMA_STATUS,
    CURRENT_VALUES, INITIAL_VALUES,
)


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    correct_key: str
    wrong_keys: tuple[str, ...]
    intent: str


QUERIES: tuple[Query, ...] = (
    # --- CURRENT queries: latest value buried among cross-thread history ---
    Query(
        id="q1_alpha_current_status",
        question="What is Project Alpha's current status?",
        correct_key=CURRENT_VALUES[("Project Alpha", "status")],      # yellow
        # Reject values that appeared earlier for Alpha (but not the final one)
        wrong_keys=tuple(v for v in set(ALPHA_STATUS[:-1]) if v != CURRENT_VALUES[("Project Alpha", "status")]),
        intent="current",
    ),
    Query(
        id="q2_beta_current_lead",
        question="Who is Project Beta's current lead?",
        correct_key=CURRENT_VALUES[("Project Beta", "lead")],          # Frank
        wrong_keys=tuple(v for v in set(BETA_LEAD[:-1]) if v != CURRENT_VALUES[("Project Beta", "lead")]),
        intent="current",
    ),
    Query(
        id="q3_gamma_current_approach",
        question="What is Project Gamma's current approach?",
        correct_key=CURRENT_VALUES[("Project Gamma", "approach")],      # mvp
        wrong_keys=tuple(v for v in set(GAMMA_APPROACH[:-1]) if v != CURRENT_VALUES[("Project Gamma", "approach")]),
        intent="current",
    ),

    # --- HISTORICAL queries: need full history ---
    Query(
        id="q4_alpha_initial_approach",
        question="What was Project Alpha's initial (first-observed) approach?",
        correct_key=INITIAL_VALUES[("Project Alpha", "approach")],      # mvp
        wrong_keys=tuple(
            v for v in set(ALPHA_APPROACH)
            if v != INITIAL_VALUES[("Project Alpha", "approach")]
        ),
        intent="historical",
    ),
    Query(
        id="q5_beta_initial_status",
        question="What was Project Beta's very first observed status?",
        correct_key=INITIAL_VALUES[("Project Beta", "status")],         # red
        wrong_keys=tuple(
            v for v in set(BETA_STATUS)
            if v != INITIAL_VALUES[("Project Beta", "status")]
        ),
        intent="historical",
    ),
    Query(
        id="q6_gamma_previous_lead",
        question="Who was Project Gamma's lead at the observation just BEFORE the current lead? Respond with a single name.",
        correct_key=GAMMA_LEAD[-2],  # Iris
        wrong_keys=tuple(
            v for v in set(GAMMA_LEAD)
            if v != GAMMA_LEAD[-2]
        ),
        intent="historical",
    ),

    # --- CROSS-THREAD queries: collapse AND history mixed ---
    Query(
        id="q7_current_leads_all",
        question="Who are the current leads of Projects Alpha, Beta, and Gamma? Give all three names.",
        # Require all three final leads to appear as standalone words
        correct_key=CURRENT_VALUES[("Project Alpha", "lead")],  # primary
        # Additional required: Frank and Grace via special scoring below
        wrong_keys=tuple(),
        intent="current",
    ),
    Query(
        id="q8_any_project_was_red",
        question="Which projects have ever been in red status at any point in their history? List project names.",
        # Alpha and Gamma both went red; Beta started red. ALL THREE went red.
        correct_key="Alpha",  # primary; Beta/Gamma checked in scoring
        wrong_keys=tuple(),
        intent="historical",
    ),
    Query(
        id="q9_alpha_current_lead_with_ctx",
        question="Who is currently leading Project Alpha? What was their lead status before?",
        correct_key=CURRENT_VALUES[("Project Alpha", "lead")],  # Bob
        wrong_keys=tuple(),
        intent="current_with_context",
    ),
)


def score(answer: str, query: Query) -> bool:
    import re
    if not answer:
        return False
    a = answer.lower()

    # Special multi-answer scoring
    if query.id == "q7_current_leads_all":
        needed = {
            CURRENT_VALUES[("Project Alpha", "lead")].lower(),
            CURRENT_VALUES[("Project Beta",  "lead")].lower(),
            CURRENT_VALUES[("Project Gamma", "lead")].lower(),
        }
        return all(n in a for n in needed)

    if query.id == "q8_any_project_was_red":
        # All three went red at some point
        return all(p.lower() in a for p in ("Alpha", "Beta", "Gamma"))

    if query.correct_key.lower() not in a:
        return False
    for w in query.wrong_keys:
        if w.lower() in a:
            return False
    return True

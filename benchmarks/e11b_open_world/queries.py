"""E11b queries — open-world status updates.

For each "open with no resolution" entity, query in two forms:
    asymmetric: "Is X resolved?" — correct answer: "unknown" / "no update"
    affirmative: a control where resolution IS recorded — correct answer:
        the resolution status

Plus a few "what is the current status" queries that test the standard
latest-per-key path on the same corpus.

Scoring:
    asymmetric_unresolved (correct = uncertain): pass iff answer signals
        uncertainty AND does NOT assert "yes/no/done/fixed" confidently
    asymmetric_resolved (correct = the recorded resolution): substring match
    current_status: substring match on the latest recorded value
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_UNCERTAINTY_MARKERS = (
    "unknown", "don't know", "do not know", "no record", "not recorded",
    "no update", "not updated", "no resolution", "no information",
    "not in", "not available", "no data", "cannot determine",
    "can't determine", "not specified", "not yet known", "still",
    "have no", "haven't", "have not", "no further", "no follow",
    "without further", "no closure", "open",
)

# Word-boundary "no" / "never" (matched separately to avoid 'know'/'now'/etc)
_UNCERTAINTY_WORD_MARKERS = ("no", "never", "none", "n/a")

# Words that assert resolution one way or the other — any of these in an
# answer to an "is X resolved?" question with no recorded resolution = fail.
_RESOLUTION_ASSERTIONS = (
    "yes", "fixed", "closed", "done", "completed", "resolved",
    "back", "returned", "recovered",
)


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    category: str  # asymmetric_unresolved / asymmetric_resolved / current_status
    correct_substring: str | None = None  # for resolved/control queries


QUERIES: tuple[Query, ...] = (
    # --- asymmetric_unresolved (open, no resolution) ---
    # Correct: signal uncertainty. Wrong: assert yes/closed/done/etc.
    Query(
        id="q1_bug_x_resolved",
        question="Is Bug X resolved? Answer based only on what's in the memory.",
        category="asymmetric_unresolved",
    ),
    Query(
        id="q2_task_y_complete",
        question="Did Task Y complete? Answer based only on what's in memory.",
        category="asymmetric_unresolved",
    ),
    Query(
        id="q3_person_z_back",
        question="Has Person Z returned from vacation? Answer based only on memory.",
        category="asymmetric_unresolved",
    ),
    Query(
        id="q4_server_s_recovered",
        question="Has Server S recovered to green? Answer based only on memory.",
        category="asymmetric_unresolved",
    ),

    # --- asymmetric_resolved (control: resolution IS recorded) ---
    Query(
        id="q5_bug_xc_resolved",
        question="What is Bug XC's current status?",
        category="asymmetric_resolved",
        correct_substring="closed",
    ),
    Query(
        id="q6_task_yc_complete",
        question="What is Task YC's current status?",
        category="asymmetric_resolved",
        correct_substring="completed",
    ),
    Query(
        id="q7_person_zc_back",
        question="What is Person ZC's current status?",
        category="asymmetric_resolved",
        correct_substring="returned",
    ),
    Query(
        id="q8_server_sc_recovered",
        question="What is Server SC's current status?",
        category="asymmetric_resolved",
        correct_substring="green",
    ),

    # --- current_status (standard latest-per-key on the unresolved entities) ---
    # The system has SOME data; question asks for the most-recent value.
    # Correct answers reflect the only-recorded states.
    Query(
        id="q9_bug_x_status_now",
        question="What is the current status of Bug X according to memory?",
        category="current_status",
        correct_substring="open",
    ),
    Query(
        id="q10_server_s_status_now",
        question="What is the current status of Server S according to memory?",
        category="current_status",
        correct_substring="red",
    ),
)


def _has_uncertainty_signal(text: str) -> bool:
    for p in _UNCERTAINTY_MARKERS:
        if p in text:
            return True
    for w in _UNCERTAINTY_WORD_MARKERS:
        if re.search(rf"\b{re.escape(w)}\b", text):
            return True
    return False


def _has_resolution_assertion(text: str) -> bool:
    for w in _RESOLUTION_ASSERTIONS:
        if re.search(rf"\b{re.escape(w)}\b", text):
            return True
    return False


def score(answer: str, query: Query) -> bool:
    if not answer:
        return False
    a = answer.lower()

    if query.category == "asymmetric_unresolved":
        # Correct iff: signals uncertainty AND does not assert resolution.
        # Specifically reject "yes / closed / fixed / done / completed / resolved /
        # back / returned / recovered" as confident-resolution markers.
        return (_has_uncertainty_signal(a)
                and not _has_resolution_assertion(a))

    if query.category in ("asymmetric_resolved", "current_status"):
        if not query.correct_substring:
            return False
        return query.correct_substring.lower() in a

    return False

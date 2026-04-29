"""E8 queries — six distinct temporal intent types over the same corpus.

Each query is hand-verified against STATE_SEQUENCE in corpus.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from .corpus import STATE_SEQUENCE


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    correct_key: str
    wrong_keys: tuple[str, ...]
    intent: str  # "current" / "historical" / "current_with_context"


# Derived ground truth
_FINAL_VALUE = STATE_SEQUENCE[-1]                                   # C
_VALUE_AT_30 = STATE_SEQUENCE[30]                                   # C
_FIRST_C_IDX = STATE_SEQUENCE.index("C")                            # 5
_COUNT_C = STATE_SEQUENCE.count("C")                                # computed
_INTERVAL_20_40 = set(STATE_SEQUENCE[20:40])                        # {A, B, C}
# last-change: T=58 was B, T=59 is C → the change was "from B to C"
_LAST_CHANGE_FROM = STATE_SEQUENCE[-2]                              # B


QUERIES: tuple[Query, ...] = (
    # --- Current state (intent = current) ---
    Query(
        id="q1_current",
        question="What is Alice's current project?",
        correct_key=f"project {_FINAL_VALUE}",
        wrong_keys=tuple(),  # we don't reject "A" etc. since they might appear as context
        intent="current",
    ),
    # --- Most-recent change (intent = current_with_context) ---
    Query(
        id="q2_last_change_from",
        question="What was Alice's project immediately before her most recent change?",
        correct_key=f"project {_LAST_CHANGE_FROM}",
        wrong_keys=tuple(),
        intent="current_with_context",
    ),
    # --- Historical count (intent = historical) ---
    # Note: no wrong_keys — integer substrings overlap badly ("1" in "19").
    # Correct-key-exact-match is enough since the LLM is asked for an integer.
    Query(
        id="q3_count_c",
        question=(
            f"Across all observations, how many times was Alice recorded on "
            f"project C? Respond with just the integer."
        ),
        correct_key=str(_COUNT_C),
        wrong_keys=tuple(),
        intent="historical",
    ),
    # --- Point-in-time lookup (intent = historical) ---
    Query(
        id="q4_value_at_30",
        question="What project was Alice on at observation #30 (counting from 0)?",
        correct_key=f"project {_VALUE_AT_30}",
        wrong_keys=tuple(),
        intent="historical",
    ),
    # --- Interval membership (intent = historical) ---
    Query(
        id="q5_interval_projects",
        question=(
            "Between observations #20 and #40, which projects did Alice work "
            "on? List them as letters separated by commas."
        ),
        # Correct: all three (A, B, C present in [20:40])
        # We'll require "A", "B", and "C" to all appear.
        correct_key="A",  # primary check
        wrong_keys=tuple(),
        intent="historical",
    ),
    # --- First occurrence (intent = historical) ---
    Query(
        id="q6_first_c",
        question=(
            f"At what observation number (0-indexed) did Alice FIRST join "
            f"project C? Respond with just the integer."
        ),
        correct_key=str(_FIRST_C_IDX),
        wrong_keys=tuple(),
        intent="historical",
    ),
)


def score(answer: str, query: Query) -> bool:
    import re
    if not answer:
        return False
    a = answer.lower()
    # Special case q5: require all three project letters as standalone words
    if query.id == "q5_interval_projects":
        for letter in ("a", "b", "c"):
            if not re.search(rf'\b{letter}\b', a):
                return False
        return True
    if query.correct_key.lower() not in a:
        return False
    for w in query.wrong_keys:
        if w.lower() in a:
            return False
    return True

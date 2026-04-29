"""Query set + scoring keys for the E4 benchmark.

3 "current state" queries (no as_of, expect the latest value after all
contradictions resolve) + 3 "temporal" queries (as_of in the past, expect
the value that was true at that time).

Each query has:
    correct_key — substring that MUST appear in a correct answer
    wrong_keys  — substrings that, if present, indicate the system got it wrong
                  (typically: superseded entity names)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    as_of: str | None
    correct_key: str       # must appear (case-insensitive) in answer
    wrong_keys: tuple[str, ...]  # must NOT appear
    kind: str              # "current" or "temporal"


QUERIES: tuple[Query, ...] = (
    # --- Current state (end of corpus) ---
    Query(
        id="q1",
        question="Who is the current CEO of Alpha Corp?",
        as_of=None,
        correct_key="Bob",
        wrong_keys=("Alice",),
        kind="current",
    ),
    Query(
        id="q2",
        question="What is the current status of Experiment Y?",
        as_of=None,
        correct_key="failed",
        wrong_keys=("in progress",),
        kind="current",
    ),
    Query(
        id="q3",
        question="Who is the current lead of Project X?",
        as_of=None,
        correct_key="Carol",
        wrong_keys=("David",),
        kind="current",
    ),
    # --- Temporal ("as of") ---
    Query(
        id="q4",
        question="Who was the CEO of Alpha Corp in mid-2020?",
        as_of="2020-07-01",
        correct_key="Alice",
        wrong_keys=("Bob",),
        kind="temporal",
    ),
    Query(
        id="q5",
        question="What was the status of Experiment Y in late 2020?",
        as_of="2020-12-31",
        correct_key="in progress",
        wrong_keys=("failed",),
        kind="temporal",
    ),
    Query(
        id="q6",
        question="Who led Project X in early 2021?",
        as_of="2021-05-01",
        correct_key="David",
        wrong_keys=("Carol",),
        kind="temporal",
    ),
)


def score_answer(answer: str, query: Query) -> bool:
    """True if the answer contains the correct_key and none of the wrong_keys."""
    if not answer:
        return False
    a = answer.lower()
    if query.correct_key.lower() not in a:
        return False
    for wrong in query.wrong_keys:
        if wrong.lower() in a:
            return False
    return True

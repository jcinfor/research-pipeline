"""E10 query generator — produces queries derived from the actual corpus.

Unlike E1-E9 where queries were hand-authored against a fixed corpus, E10's
corpus changes with scale, so queries must be derived from the generated
triples. We pick:

    - 3 "current value" queries on randomly-selected (entity, attribute) pairs
    - 3 "initial value" queries (historical) on different pairs
    - 1 "list current values for entity X" cross-attribute query

7 queries per scale level. Substring scoring against ground truth.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .corpus import (
    Triple, ground_truth_currents, ground_truth_initials,
)


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    correct_key: str
    intent: str  # current / historical / cross_attribute


def build_queries(triples: list[Triple], *, seed: int = 1234) -> list[Query]:
    rng = random.Random(seed)
    currents = ground_truth_currents(triples)
    initials = ground_truth_initials(triples)

    keys = list(currents.keys())
    rng.shuffle(keys)

    queries: list[Query] = []

    # 3 current-value queries
    for i, (entity, attr) in enumerate(keys[:3]):
        # Re-derive display-cased entity (use first triple's entity field)
        display_entity = next(
            t.entity for t in triples if t.entity.lower() == entity
        )
        queries.append(Query(
            id=f"q{i+1}_current_{entity}_{attr}",
            question=(
                f"What is {display_entity}'s current {attr}? "
                f"Respond with just the value."
            ),
            correct_key=currents[(entity, attr)],
            intent="current",
        ))

    # 3 initial-value (historical) queries on different pairs
    historical_keys = keys[3:6] if len(keys) >= 6 else keys[:3]
    for i, (entity, attr) in enumerate(historical_keys):
        display_entity = next(
            t.entity for t in triples if t.entity.lower() == entity
        )
        queries.append(Query(
            id=f"q{i+4}_initial_{entity}_{attr}",
            question=(
                f"What was {display_entity}'s very first observed {attr} "
                f"(the initial value, before any later changes)? "
                f"Respond with just the value."
            ),
            correct_key=initials[(entity, attr)],
            intent="historical",
        ))

    # 1 cross-attribute current query
    if keys:
        # Pick an entity and ask for ALL three current attributes
        target_entity = keys[0][0]
        display_entity = next(
            t.entity for t in triples if t.entity.lower() == target_entity
        )
        # We'll score this by checking that all three current values appear
        attrs = sorted({a for (e, a) in currents.keys() if e == target_entity})
        if len(attrs) >= 2:
            joined = ", ".join(currents[(target_entity, a)] for a in attrs)
            queries.append(Query(
                id=f"q7_cross_attr_{target_entity}",
                question=(
                    f"List {display_entity}'s current status, role, and project "
                    f"as comma-separated values."
                ),
                correct_key=joined,  # placeholder; scoring uses _attrs_required
                intent="cross_attribute",
            ))

    return queries


def score(answer: str, query: Query, triples: list[Triple]) -> bool:
    """Substring scoring. For cross-attribute queries, require ALL three
    current values for the target entity to appear in the answer."""
    if not answer:
        return False
    a = answer.lower()
    if query.intent == "cross_attribute":
        # Recover target entity from query id
        # id format: q7_cross_attr_<entity>
        target = query.id.replace("q7_cross_attr_", "")
        currents = ground_truth_currents(triples)
        needed_values = [
            currents[(e, attr)].lower()
            for (e, attr) in currents.keys()
            if e == target
        ]
        return all(v in a for v in needed_values)
    return query.correct_key.lower() in a

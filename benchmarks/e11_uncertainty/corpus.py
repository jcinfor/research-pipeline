"""E11 corpus — small, fully-known data so we can ask questions whose
answers are known to be ABSENT from the memory.

Three entities (Alice, Bob, Carol) with three attributes each (status,
role, project) and three observations per pair = 27 triples total. Small
enough that the absent facts are unambiguously absent.

Queries probe four categories:
    - control: facts that ARE in memory; should be answered correctly
    - missing_attribute: entity is known, attribute was never recorded
    - missing_entity: entity was never mentioned at all
    - never_happened: a "did X event happen?" query where the event is absent
"""
from __future__ import annotations

from datetime import datetime, timedelta

from benchmarks.e10_scale_out.corpus import Triple


# Hand-designed deterministic data
_OBSERVATIONS = (
    # (entity, attribute, [values for each of 3 obs])
    ("Alice", "status",  ("active", "blocked", "review")),
    ("Alice", "role",    ("lead", "lead", "advisor")),
    ("Alice", "project", ("alpha", "alpha", "beta")),
    ("Bob",   "status",  ("idle", "active", "active")),
    ("Bob",   "role",    ("contributor", "contributor", "reviewer")),
    ("Bob",   "project", ("gamma", "gamma", "gamma")),
    ("Carol", "status",  ("active", "review", "done")),
    ("Carol", "role",    ("observer", "advisor", "advisor")),
    ("Carol", "project", ("delta", "delta", "delta")),
)


def build_triples() -> list[Triple]:
    triples: list[Triple] = []
    base_t = datetime.fromisoformat("2026-01-01T00:00:00")
    delta = timedelta(seconds=10)
    counter = 0
    # Round-robin so observations interleave by (entity, attribute)
    for round_i in range(3):
        for entity, attr, values in _OBSERVATIONS:
            t = base_t + delta * counter
            triples.append(Triple(
                entity=entity,
                attribute=attr,
                value=values[round_i],
                valid_from=t.isoformat(timespec="seconds"),
                source_doc=f"obs_{counter:04d}",
            ))
            counter += 1
    return triples


CORPUS: list[Triple] = build_triples()

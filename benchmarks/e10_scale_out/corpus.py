"""E10 corpus — synthetic triples at scale.

E1-E9 went up to ~400 triples. E10 tests query-time behavior at 100, 500,
1000, 2500, 5000 triples — bracketing the predicted scale where zep_rich's
"expose all history" approach starts to fail (token-cost or context-limit
collapse on a 256K-context 26B model).

Strategy: synthetic triple generation, no LLM extraction. We're testing
QUERY-TIME scaling, not ingestion scaling. (Ingestion cost scales linearly
with corpus — uninteresting question.)

Each scale level generates a self-consistent triple set with:
  - K named entities (people-named for variety)
  - 3 attributes per entity (status, role, project)
  - target_size / (K * 3) observations per (entity, attribute) pair
  - last value per (entity, attribute) is deterministic ground truth
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


_PEOPLE = (
    "Alice", "Bob", "Carol", "Dave", "Eve", "Frank",
    "Grace", "Henry", "Iris", "Jack", "Kate", "Liam",
    "Mia", "Noah", "Olivia", "Paul",
)
_STATUSES = ("active", "idle", "blocked", "review", "done")
_ROLES = ("lead", "contributor", "reviewer", "advisor", "observer")
_PROJECTS = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta")


@dataclass(frozen=True)
class Triple:
    entity: str
    attribute: str
    value: str
    valid_from: str
    source_doc: str


def make_triples(target_size: int, *, seed: int = 42) -> list[Triple]:
    """Produce ~target_size triples spread across entities and attributes.

    Deterministic for a given (target_size, seed). Returns triples in
    chronological order (sorted by valid_from).
    """
    import random
    rng = random.Random(seed)

    # Pick entity count so we have ~3 attributes per entity and 5+ obs per
    # (entity, attribute) pair on average.
    n_entities = max(3, min(len(_PEOPLE), target_size // 15))
    entities = _PEOPLE[:n_entities]
    attributes = ("status", "role", "project")
    pairs = [(e, a) for e in entities for a in attributes]
    obs_per_pair = max(2, target_size // len(pairs))

    triples: list[Triple] = []
    base_t = datetime.fromisoformat("2026-01-01T00:00:00")
    delta = timedelta(seconds=10)
    counter = 0

    # Round-robin over pairs so triples interleave by entity (cross-thread).
    for i in range(obs_per_pair):
        for entity, attr in pairs:
            if attr == "status":
                value = rng.choice(_STATUSES)
            elif attr == "role":
                value = rng.choice(_ROLES)
            else:
                value = rng.choice(_PROJECTS)
            t = base_t + delta * counter
            triples.append(Triple(
                entity=entity,
                attribute=attr,
                value=value,
                valid_from=t.isoformat(timespec="seconds"),
                source_doc=f"obs_{counter:06d}",
            ))
            counter += 1

    # Trim to exactly target_size if we overshot
    triples = triples[:target_size]
    triples.sort(key=lambda t: t.valid_from)
    return triples


def ground_truth_currents(triples: list[Triple]) -> dict[tuple[str, str], str]:
    """Per-key latest value — used to score 'current value' queries."""
    latest: dict[tuple[str, str], Triple] = {}
    for t in triples:
        key = (t.entity.lower(), t.attribute.lower())
        if key not in latest or t.valid_from > latest[key].valid_from:
            latest[key] = t
    return {k: v.value for k, v in latest.items()}


def ground_truth_initials(triples: list[Triple]) -> dict[tuple[str, str], str]:
    """Per-key first-observed value — used to score 'initial value' historical queries."""
    initial: dict[tuple[str, str], Triple] = {}
    for t in triples:
        key = (t.entity.lower(), t.attribute.lower())
        if key not in initial or t.valid_from < initial[key].valid_from:
            initial[key] = t
    return {k: v.value for k, v in initial.items()}


def populate_mem0(system: Any, triples: list[Triple]) -> None:
    """Directly populate Mem0Lite's internal memory dict — skips LLM extraction.

    Mem0Lite's behavior: latest value per (entity, attribute) overwrites prior.
    We replay triples in chronological order so the final state matches what
    real ingestion would produce.
    """
    for t in triples:
        ek, ak = t.entity.lower(), t.attribute.lower()
        prior = system.memory.setdefault(ek, {}).get(ak)
        if prior is None or t.valid_from >= prior["updated_at"]:
            system.memory[ek][ak] = {
                "value": t.value, "entity": t.entity, "attribute": t.attribute,
                "updated_at": t.valid_from, "source_doc": t.source_doc,
            }


def populate_zep(system: Any, triples: list[Triple]) -> None:
    """Directly populate ZepLite/ZepRich/IntentRoutedZep's triple list.

    All three classes share the same underlying triples list (Zep variants
    differ only in their .query() method).
    """
    for t in triples:
        system.triples.append({
            "entity": t.entity,
            "attribute": t.attribute,
            "value": t.value,
            "valid_from": t.valid_from,
            "source_doc": t.source_doc,
        })

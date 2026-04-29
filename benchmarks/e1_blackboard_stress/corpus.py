"""Stream generator for the E1 Blackboard Stress Test.

Generates a high-velocity sequence of incremental state changes for a single
attribute of a single entity. The retrieval target is the LAST value in the
stream — earlier values are "wrong" once superseded.

This is the pattern predicted to reveal architectural differences:
    - Hybrid (flat chunks + cosine top-k): may miss the latest chunk when
      many near-identical chunks compete for top-k slots
    - Zep (extract triples with valid_from): deterministic latest-per-key
    - Mem0 (extract + consolidate): overwrites prior value per key
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Doc:
    id: str
    pub_date: str  # ISO datetime, e.g. "2026-04-24T10:15:30"
    text: str
    entities: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Stream:
    """One stress-test stream: N updates to (entity, attribute)."""
    entity: str
    attribute: str
    values: tuple[str, ...]   # ground-truth sequence; values[-1] is "current"
    docs: tuple[Doc, ...]


def make_stream(
    entity: str,
    attribute: str,
    values: list[str],
    t_start: str = "2026-01-01T00:00:00",
    t_delta_sec: int = 60,
    doc_id_prefix: str | None = None,
) -> Stream:
    """Create a Stream of len(values) docs, one update per doc.

    Each doc says: "{entity}'s {attribute} is {value} (as of {pub_date})".
    Timestamps step by `t_delta_sec` seconds.
    """
    prefix = doc_id_prefix or f"{entity.lower().replace(' ', '_')}_{attribute.lower().replace(' ', '_')}"
    t0 = datetime.fromisoformat(t_start)
    docs: list[Doc] = []
    for i, v in enumerate(values):
        t = t0 + timedelta(seconds=i * t_delta_sec)
        pub = t.isoformat(timespec="seconds")
        docs.append(Doc(
            id=f"{prefix}_{i:03d}",
            pub_date=pub,
            text=(
                f"Update #{i+1}: {entity}'s {attribute} is {v} "
                f"(recorded at {pub})."
            ),
            entities=(f"{entity} {attribute}",),
        ))
    return Stream(
        entity=entity,
        attribute=attribute,
        values=tuple(values),
        docs=tuple(docs),
    )


# Default fixtures used by the live benchmark. Three parallel streams stress
# the systems with multiple entities interleaved.
STREAMS: tuple[Stream, ...] = (
    make_stream(
        entity="User Alice",
        attribute="temperature",
        values=[
            "98.6", "99.1", "100.2", "101.0", "101.5",
            "101.2", "100.8", "99.9", "99.2", "98.9",
            "98.7", "98.6", "98.8", "99.3", "99.0",
            "98.8", "98.7", "98.6", "98.9", "99.0",
        ],
    ),
    make_stream(
        entity="Server Prod-01",
        attribute="status",
        values=[
            "green", "green", "yellow", "yellow", "red",
            "red", "red", "yellow", "yellow", "green",
            "green", "green", "yellow", "red", "red",
            "yellow", "green", "green", "green", "green",
        ],
        t_start="2026-02-01T00:00:00",
    ),
    make_stream(
        entity="Project Nova",
        attribute="lead",
        values=[
            "Alice", "Alice", "Bob", "Bob", "Bob",
            "Carol", "Carol", "Dave", "Dave", "Dave",
            "Eve", "Eve", "Frank", "Frank", "Grace",
            "Grace", "Grace", "Henry", "Henry", "Iris",
        ],
        t_start="2026-03-01T00:00:00",
    ),
)


def interleaved_docs(streams: tuple[Stream, ...] = STREAMS) -> list[Doc]:
    """Return all docs from all streams, sorted by pub_date (monotonic).

    This models a real blackboard where updates across entities arrive
    in wall-clock order, not grouped by entity.
    """
    all_docs: list[Doc] = []
    for s in streams:
        all_docs.extend(s.docs)
    all_docs.sort(key=lambda d: d.pub_date)
    return all_docs

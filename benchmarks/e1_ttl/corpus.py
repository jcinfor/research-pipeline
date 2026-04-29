"""E1-TTL corpus: isolate TTL-induced forgetting.

Scenario: one "cold" entity with a single old update; one "hot" entity with
many recent updates. When TTL fires, the cold entity's fact is ejected from
the consolidated profile — but it's still the CURRENT truth (the cold entity
was never re-observed, not superseded).

The experiment tests whether supermemory's TTL+chunk-fallback rescues the
cold fact via chunk retrieval, or whether the hot entity's flood of chunks
crowds the cold fact out of the retrieval window too.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from benchmarks.e1_blackboard_stress.corpus import Doc


@dataclass(frozen=True)
class TtlStream:
    cold_entity: str
    cold_attribute: str
    cold_value: str
    hot_entity: str
    hot_attribute: str
    hot_values: tuple[str, ...]
    docs: tuple[Doc, ...]


def make_ttl_stream(
    cold_entity: str = "Alice",
    cold_attribute: str = "favourite_color",
    cold_value: str = "blue",
    hot_entity: str = "Server Prod-01",
    hot_attribute: str = "status",
    hot_values: tuple[str, ...] = (
        "green", "green", "yellow", "yellow", "red",
        "red", "red", "yellow", "yellow", "green",
        "green", "green", "yellow", "red", "red",
        "yellow", "green", "green", "green", "green",
    ),
    t_start: str = "2026-01-01T00:00:00",
    hot_delta_sec: int = 60,   # hot entity updated every 60s
    cold_lag_sec: int = 60 * 60 * 24 * 7,  # 7 days later the hot stream fires
) -> TtlStream:
    """One cold doc for Alice at t=0, then N hot docs for Prod-01 starting
    at t = cold_lag_sec. The cold doc's age at query time will exceed
    a TTL measured in hours, while every hot doc stays fresh.
    """
    t0 = datetime.fromisoformat(t_start)
    cold_doc = Doc(
        id=f"{cold_entity.lower()}_{cold_attribute.lower()}_cold",
        pub_date=t0.isoformat(timespec="seconds"),
        text=f"Static fact: {cold_entity}'s {cold_attribute} is {cold_value}.",
        entities=(f"{cold_entity} {cold_attribute}",),
    )
    hot_start = t0 + timedelta(seconds=cold_lag_sec)
    hot_docs: list[Doc] = []
    for i, v in enumerate(hot_values):
        t = hot_start + timedelta(seconds=i * hot_delta_sec)
        pub = t.isoformat(timespec="seconds")
        hot_docs.append(Doc(
            id=f"{hot_entity.lower().replace(' ', '_')}_{hot_attribute.lower()}_{i:03d}",
            pub_date=pub,
            text=f"Update #{i+1}: {hot_entity}'s {hot_attribute} is {v} (at {pub}).",
            entities=(f"{hot_entity} {hot_attribute}",),
        ))
    return TtlStream(
        cold_entity=cold_entity,
        cold_attribute=cold_attribute,
        cold_value=cold_value,
        hot_entity=hot_entity,
        hot_attribute=hot_attribute,
        hot_values=tuple(hot_values),
        docs=(cold_doc, *hot_docs),
    )


STREAM: TtlStream = make_ttl_stream()

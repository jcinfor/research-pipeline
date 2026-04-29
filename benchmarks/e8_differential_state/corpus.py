"""E8 corpus — Differential State Reconstruction.

Proposed by project 8's synthesis (decision.md). Tests whether architectural
innovations in memory should focus on the SUBSTRATE (append-only vs lossy)
or the QUERY ROUTING (intent-based dispatcher).

A single entity's attribute undergoes 60 NON-MONOTONIC changes — the value
oscillates across three states (project A / B / C). Queries then demand
different temporal access patterns:
  - current state
  - most-recent change
  - historical count per value
  - point-in-time lookup
  - interval membership
  - first occurrence

Prediction:
  - mem0_lite        — passes ONLY "current state"; storage is overwrite-only
  - zep_lite         — passes "current state"; fails history because its
                       query layer collapses to latest-per-key
  - zep_rich         — passes history but may fail "current state" because
                       full-history context overloads the LLM
  - intent_routed    — passes everything; same storage as ZepRich; router
                       picks the right query surface per intent
  - hybrid_flat      — mixed; cosine retrieval may surface the wrong turns
"""
from __future__ import annotations

from datetime import datetime, timedelta

from benchmarks.e1_blackboard_stress.corpus import Doc


# Non-monotonic oscillation pattern across projects A/B/C
# Designed so distinct queries have distinct ground truths.
STATE_SEQUENCE: tuple[str, ...] = (
    "A", "A", "B", "B", "A",    # 0-4
    "C", "C", "A", "B", "B",    # 5-9
    "A", "C", "C", "B", "A",    # 10-14
    "A", "B", "C", "C", "B",    # 15-19
    "A", "A", "C", "B", "B",    # 20-24
    "C", "A", "A", "B", "C",    # 25-29 (T=30 is the "point-in-time" anchor: C)
    "C", "B", "A", "A", "B",    # 30-34
    "C", "B", "B", "A", "C",    # 35-39 (interval T=20..40 includes A,B,C)
    "C", "A", "B", "C", "A",    # 40-44
    "A", "B", "C", "C", "B",    # 45-49
    "A", "C", "B", "B", "A",    # 50-54
    "C", "A", "A", "B", "C",    # 55-59 (final value T=59: C)
)
# Ground-truth analytics derivable from STATE_SEQUENCE:
# - current (last) value at T=59: C
# - most-recent change (from T=58 to T=59): B -> C
# - count of "C" in full sequence: computed in queries.py
# - value at T=30: C
# - set of values in T=20..40: {A, B, C}
# - first occurrence of "C": T=5

assert len(STATE_SEQUENCE) == 60


def build_corpus(entity: str = "Alice", attribute: str = "current project") -> list[Doc]:
    docs: list[Doc] = []
    t0 = datetime.fromisoformat("2026-01-01T00:00:00")
    for i, v in enumerate(STATE_SEQUENCE):
        t = t0 + timedelta(minutes=i)
        pub = t.isoformat(timespec="seconds")
        docs.append(Doc(
            id=f"alice_proj_t{i:02d}",
            pub_date=pub,
            text=(
                f"Observation at {pub}: {entity}'s {attribute} is project {v}."
            ),
            entities=(f"{entity} {attribute}",),
        ))
    return docs


CORPUS: list[Doc] = build_corpus()

"""E6 corpus: three interleaved streams with overlapping timestamps.

Unlike E1's staggered streams (each entity has its own month), E6's streams
run in parallel so that at each timestamp all three entities have a
contemporaneous value. This is the workload that stresses cross-entity
temporal join queries ("what was X's status when Y peaked?").

The three entities are intentionally named so their values don't collide:
  User Alice       — temperature (float values)
  Server Prod-01   — status (green/yellow/red)
  Project Nova     — lead (names: Bob/Carol/Dave)

Note: Nova's lead values are Bob/Carol/Dave (NOT Alice) to avoid collision
with the User Alice entity.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from benchmarks.e1_blackboard_stress.corpus import Doc


# Parallel value streams — 10 timesteps, all three entities update at each.
# Hand-designed so cross-entity queries have clean answers.

ALICE_TEMPS: tuple[str, ...] = (
    "98.6", "99.0", "100.0", "101.0",
    "101.5",   # <-- PEAK at T=4
    "101.2", "100.8", "100.0", "99.5", "99.0",
)

PROD_STATUS: tuple[str, ...] = (
    "green", "green", "yellow", "yellow",
    "red",     # <-- first red at T=4
    "red", "yellow", "yellow", "green", "green",
)

NOVA_LEAD: tuple[str, ...] = (
    "Bob", "Bob", "Bob", "Carol",
    "Carol",   # <-- Carol leads at T=4
    "Carol", "Dave", "Dave", "Dave", "Dave",   # <-- Dave takes over at T=6
)

assert len(ALICE_TEMPS) == len(PROD_STATUS) == len(NOVA_LEAD) == 10


def build_corpus() -> list[Doc]:
    """Produce 30 docs in chronological order, interleaving the three streams.

    At each timestep the Alice doc comes first, then Prod-01, then Nova,
    with a 10-second offset so their pub_dates are strictly monotonic.
    """
    docs: list[Doc] = []
    t0 = datetime.fromisoformat("2026-01-01T00:00:00")
    for i in range(10):
        base = t0 + timedelta(minutes=i)
        docs.append(Doc(
            id=f"alice_t{i:02d}",
            pub_date=(base + timedelta(seconds=0)).isoformat(timespec="seconds"),
            text=(
                f"Update: User Alice's temperature is {ALICE_TEMPS[i]} "
                f"(recorded at {(base + timedelta(seconds=0)).isoformat(timespec='seconds')})."
            ),
            entities=("User Alice temperature",),
        ))
        docs.append(Doc(
            id=f"prod_t{i:02d}",
            pub_date=(base + timedelta(seconds=10)).isoformat(timespec="seconds"),
            text=(
                f"Update: Server Prod-01's status is {PROD_STATUS[i]} "
                f"(recorded at {(base + timedelta(seconds=10)).isoformat(timespec='seconds')})."
            ),
            entities=("Server Prod-01 status",),
        ))
        docs.append(Doc(
            id=f"nova_t{i:02d}",
            pub_date=(base + timedelta(seconds=20)).isoformat(timespec="seconds"),
            text=(
                f"Update: Project Nova's lead is {NOVA_LEAD[i]} "
                f"(recorded at {(base + timedelta(seconds=20)).isoformat(timespec='seconds')})."
            ),
            entities=("Project Nova lead",),
        ))
    return docs


CORPUS: list[Doc] = build_corpus()

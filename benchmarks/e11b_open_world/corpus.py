"""E11b corpus — events raised but resolutions silently absent.

Pattern from E7 q6 that tripped supermemory: an event was recorded ("CI is
slow") but no resolution update was ever logged. The user asks "is it
fixed?" — correct answer is "unknown" / "no update available", not "no" /
"yes". E11 tested closed-world absence (entity/attribute simply not in
memory); E11b tests OPEN-WORLD asymmetric state where opening is recorded
and closing is silent.

Eight scenarios — four "open with no resolution" + four control "open and
resolved". The asymmetry is the point: same opening event, different
closure data.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from benchmarks.e10_scale_out.corpus import Triple


# Each row: (entity, attribute, value, days_offset, source_id)
_OBSERVATIONS: tuple[tuple[str, str, str, int, str], ...] = (
    # --- Open events with NO resolution ever recorded ---
    # Bug X opened, no closure
    ("Bug X", "status", "open", 0, "bug_x_001"),
    ("Bug X", "reporter", "Alice", 0, "bug_x_002"),
    # Task Y started, no completion
    ("Task Y", "status", "in_progress", 1, "task_y_001"),
    ("Task Y", "owner", "Bob", 1, "task_y_002"),
    # Person Z went on vacation, no return
    ("Person Z", "status", "on_vacation", 2, "person_z_001"),
    ("Person Z", "destination", "Spain", 2, "person_z_002"),
    # Server S went red, no recovery
    ("Server S", "status", "red", 3, "server_s_001"),
    ("Server S", "owner", "Carol", 3, "server_s_002"),

    # --- Control: opens AND resolutions are both recorded ---
    # Bug X-control: opened then closed
    ("Bug XC", "status", "open", 4, "bug_xc_001"),
    ("Bug XC", "reporter", "Dave", 4, "bug_xc_002"),
    ("Bug XC", "status", "closed", 5, "bug_xc_003"),  # resolution recorded
    # Task YC: started then completed
    ("Task YC", "status", "in_progress", 6, "task_yc_001"),
    ("Task YC", "owner", "Eve", 6, "task_yc_002"),
    ("Task YC", "status", "completed", 7, "task_yc_003"),  # resolution recorded
    # Person ZC: went and returned
    ("Person ZC", "status", "on_vacation", 8, "person_zc_001"),
    ("Person ZC", "status", "returned", 9, "person_zc_002"),  # resolution recorded
    # Server SC: went red and recovered
    ("Server SC", "status", "red", 10, "server_sc_001"),
    ("Server SC", "status", "green", 11, "server_sc_002"),  # resolution recorded
)


def build_triples() -> list[Triple]:
    triples: list[Triple] = []
    base_t = datetime.fromisoformat("2026-04-01T00:00:00")
    for entity, attribute, value, days, source in _OBSERVATIONS:
        t = base_t + timedelta(days=days)
        triples.append(Triple(
            entity=entity,
            attribute=attribute,
            value=value,
            valid_from=t.isoformat(timespec="seconds"),
            source_doc=source,
        ))
    return triples


CORPUS: list[Triple] = build_triples()

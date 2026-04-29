"""E9 corpus — multi-entity interleaved attribute history.

Purpose: produce a workload where zep_rich's "expose full history" query
strategy should struggle on current-value queries because the latest value
for a given (entity, attribute) is buried among many similar-looking
triples for OTHER (entity, attribute) pairs.

3 entities × 3 attributes × 10 observations = 90 triples, interleaved by
wall-clock so latest-per-key values are scattered through the chronology.

Attributes intentionally share names across entities (status, lead,
approach) so the LLM cannot disambiguate by attribute alone — it must
match the entity AND the attribute. This is the cross-thread confusion
pattern.

Entities:
    Project Alpha, Project Beta, Project Gamma

Attributes:
    status   — green / yellow / red
    lead     — a person name
    approach — mvp / scale / v2 / rewrite / pilot
"""
from __future__ import annotations

from datetime import datetime, timedelta

from benchmarks.e1_blackboard_stress.corpus import Doc


# Per-entity value trajectories. Each trajectory has 10 values. Final value
# is the "current" answer. Designed so:
#   - Each entity's "current X" is different from each other's.
#   - Near-miss plausible alternatives appear elsewhere in history.
#   - First values (initial state) are distinguishable from final values.

ALPHA_STATUS  = ("green", "green", "yellow", "red", "red",
                 "yellow", "green", "yellow", "red", "yellow")   # current: yellow
ALPHA_LEAD    = ("Alice", "Alice", "Bob", "Bob", "Carol",
                 "Carol", "Bob", "Alice", "Carol", "Bob")         # current: Bob
ALPHA_APPROACH = ("mvp", "mvp", "scale", "scale", "scale",
                  "v2", "v2", "rewrite", "rewrite", "v2")         # current: v2

BETA_STATUS   = ("red", "red", "red", "yellow", "green",
                 "green", "green", "yellow", "green", "green")    # current: green
BETA_LEAD     = ("Dave", "Dave", "Eve", "Eve", "Eve",
                 "Frank", "Frank", "Dave", "Frank", "Frank")       # current: Frank
BETA_APPROACH = ("pilot", "pilot", "mvp", "mvp", "scale",
                 "scale", "scale", "mvp", "scale", "scale")        # current: scale

GAMMA_STATUS   = ("yellow", "yellow", "green", "green", "green",
                  "red", "red", "yellow", "yellow", "red")          # current: red
GAMMA_LEAD     = ("Grace", "Grace", "Henry", "Henry", "Iris",
                  "Iris", "Henry", "Grace", "Iris", "Grace")         # current: Grace
GAMMA_APPROACH = ("rewrite", "rewrite", "rewrite", "v2", "v2",
                  "v2", "pilot", "pilot", "mvp", "mvp")              # current: mvp


_ENTITY_SCHEMAS = (
    ("Project Alpha", "status",   ALPHA_STATUS),
    ("Project Alpha", "lead",     ALPHA_LEAD),
    ("Project Alpha", "approach", ALPHA_APPROACH),
    ("Project Beta",  "status",   BETA_STATUS),
    ("Project Beta",  "lead",     BETA_LEAD),
    ("Project Beta",  "approach", BETA_APPROACH),
    ("Project Gamma", "status",   GAMMA_STATUS),
    ("Project Gamma", "lead",     GAMMA_LEAD),
    ("Project Gamma", "approach", GAMMA_APPROACH),
)


def build_corpus() -> list[Doc]:
    """Emit 90 interleaved observations, one per minute starting 2026-03-01.

    At each minute-step i, we emit all 9 (entity, attribute) observations
    with tiny second-offsets so they're strictly monotonic. This produces
    the "latest-value is buried" pattern zep_rich should struggle with.
    """
    docs: list[Doc] = []
    t0 = datetime.fromisoformat("2026-03-01T00:00:00")
    for i in range(10):
        base = t0 + timedelta(minutes=i)
        for j, (entity, attribute, seq) in enumerate(_ENTITY_SCHEMAS):
            t = base + timedelta(seconds=j * 5)
            pub = t.isoformat(timespec="seconds")
            value = seq[i]
            docs.append(Doc(
                id=f"{entity.split()[1].lower()}_{attribute}_t{i:02d}",
                pub_date=pub,
                text=(
                    f"Observation at {pub}: {entity}'s {attribute} is {value}."
                ),
                entities=(f"{entity} {attribute}",),
            ))
    return docs


CORPUS: list[Doc] = build_corpus()


# Ground-truth derived for query module
CURRENT_VALUES = {
    ("Project Alpha", "status"):   ALPHA_STATUS[-1],
    ("Project Alpha", "lead"):     ALPHA_LEAD[-1],
    ("Project Alpha", "approach"): ALPHA_APPROACH[-1],
    ("Project Beta",  "status"):   BETA_STATUS[-1],
    ("Project Beta",  "lead"):     BETA_LEAD[-1],
    ("Project Beta",  "approach"): BETA_APPROACH[-1],
    ("Project Gamma", "status"):   GAMMA_STATUS[-1],
    ("Project Gamma", "lead"):     GAMMA_LEAD[-1],
    ("Project Gamma", "approach"): GAMMA_APPROACH[-1],
}
INITIAL_VALUES = {k: v for k, v in [
    (("Project Alpha", "status"),   ALPHA_STATUS[0]),
    (("Project Alpha", "lead"),     ALPHA_LEAD[0]),
    (("Project Alpha", "approach"), ALPHA_APPROACH[0]),
    (("Project Beta",  "status"),   BETA_STATUS[0]),
    (("Project Beta",  "lead"),     BETA_LEAD[0]),
    (("Project Beta",  "approach"), BETA_APPROACH[0]),
    (("Project Gamma", "status"),   GAMMA_STATUS[0]),
    (("Project Gamma", "lead"),     GAMMA_LEAD[0]),
    (("Project Gamma", "approach"), GAMMA_APPROACH[0]),
]}

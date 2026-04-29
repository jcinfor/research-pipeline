"""Synthetic corpus for the E4 Query-Time Repair benchmark.

10 chronologically-ordered documents about a fictional company (Alpha Corp),
a research project (Project X), and an experiment (Experiment Y). Three
contradictions are woven in:

    #1  CEO succession:     Alice (2020) -> Bob (2021)
    #2  Experiment outcome: in-progress (2020) -> failed (2021)
    #3  Project X lead:     David (2020) -> Carol (2021)

Each doc is pre-tagged with the entities it discusses so the three systems
under test can route their updates consistently (no LLM-based entity
extraction in the benchmark; that's a separate variance we want to avoid).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Doc:
    id: str
    pub_date: str          # ISO date "YYYY-MM-DD"
    text: str
    entities: tuple[str, ...]  # pre-tagged entity names mentioned in the doc


CORPUS: tuple[Doc, ...] = (
    Doc(
        id="doc_001",
        pub_date="2020-03-15",
        entities=("Alpha Corp CEO",),
        text=(
            "Alpha Corp announced today that Alice Chen has been appointed "
            "as the new Chief Executive Officer, effective immediately. "
            "Alice brings 15 years of industry experience to the role."
        ),
    ),
    Doc(
        id="doc_002",
        pub_date="2020-06-20",
        entities=("Alpha Corp CEO",),
        text=(
            "Alpha Corp reported a strong second quarter under CEO Alice "
            "Chen's leadership, with revenue growth of 22% year over year. "
            "Analysts credited Alice's strategic focus on cloud services."
        ),
    ),
    Doc(
        id="doc_003",
        pub_date="2020-09-10",
        entities=("Experiment Y status", "Project X lead"),
        text=(
            "Project X officially launched this week under the leadership "
            "of Dr. David Ramirez, who will serve as project lead. Separately, "
            "Experiment Y is in progress, with preliminary data expected in Q1."
        ),
    ),
    Doc(
        id="doc_004",
        pub_date="2020-11-01",
        entities=("Project X lead",),
        text=(
            "Carol Tan has joined Project X as deputy lead, reporting to "
            "Dr. David Ramirez. Her appointment strengthens the project's "
            "capabilities in systems integration."
        ),
    ),
    Doc(
        id="doc_005",
        pub_date="2021-01-10",
        entities=("Alpha Corp CEO",),
        text=(
            "Alpha Corp announced today that Bob Patel will replace Alice "
            "Chen as Chief Executive Officer. Alice is stepping down to "
            "pursue other opportunities. Bob takes over effective January 15."
        ),
    ),
    Doc(
        id="doc_006",
        pub_date="2021-03-20",
        entities=("Alpha Corp CEO",),
        text=(
            "In his first quarter as CEO, Bob Patel has outlined Alpha Corp's "
            "new strategy focused on AI-first product development. Early "
            "reactions from the engineering team have been positive."
        ),
    ),
    Doc(
        id="doc_007",
        pub_date="2021-07-15",
        entities=("Experiment Y status",),
        text=(
            "Experiment Y has concluded with negative results. The team has "
            "determined that the core hypothesis cannot be validated under "
            "the current methodology. The experiment is formally classified "
            "as failed, and resources are being reallocated."
        ),
    ),
    Doc(
        id="doc_008",
        pub_date="2021-09-05",
        entities=("Project X lead",),
        text=(
            "Dr. David Ramirez is departing Alpha Corp to join an academic "
            "institution. Carol Tan has been promoted to project lead of "
            "Project X, effective this month."
        ),
    ),
    Doc(
        id="doc_009",
        pub_date="2022-02-10",
        entities=("Project X lead",),
        text=(
            "Under the direction of lead Carol Tan, Project X has set an "
            "ambitious roadmap for 2022 including three new product "
            "integrations and a dedicated research stream."
        ),
    ),
    Doc(
        id="doc_010",
        pub_date="2022-05-30",
        entities=("Alpha Corp CEO",),
        text=(
            "Alpha Corp, under CEO Bob Patel, announced expansion into three "
            "new markets today. The company cited strong execution across "
            "its product lines as the foundation for the growth plan."
        ),
    ),
)


def all_entities() -> set[str]:
    s: set[str] = set()
    for d in CORPUS:
        for e in d.entities:
            s.add(e)
    return s

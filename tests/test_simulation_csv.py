import csv
from pathlib import Path

from research_pipeline.archetypes import by_id
from research_pipeline.simulation import _write_profile_csv


def test_write_profile_csv(tmp_path: Path):
    archetypes = [by_id("scout"), by_id("hypogen"), by_id("critic")]
    out = tmp_path / "profiles.csv"
    _write_profile_csv(out, archetypes, project_goal="test the pipeline")

    with out.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header, *data = rows
    assert header[1:] == [
        "user_id",
        "name",
        "username",
        "following_agentid_list",
        "previous_tweets",
        "user_char",
        "description",
    ]
    assert len(data) == 3
    assert data[0][2] == "scout"
    assert data[1][2] == "hypogen"
    assert data[2][2] == "critic"
    for row in data:
        assert "RESEARCH GOAL: test the pipeline" in row[7]

"""Tests for the partial-credit pgr_support proxy."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.pgr import (
    PGRSupportResult,
    pgr_support,
)
from research_pipeline.projects import create_project, upsert_user


CLAIMS_MD = """# Claims

## C1: Claim referencing first chunk.
- Supporting: [src #1]

## C2: Claim referencing two chunks.
- Supporting: [src #2], [src #3]
"""


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _LevelJudge:
    """Returns canned 0/1/2 levels in order."""

    def __init__(self, levels: list[int]):
        self._q = list(levels)
        self.calls = 0

    def chat(self, role, messages, **kwargs):
        self.calls += 1
        level = self._q.pop(0) if self._q else 0
        return _Resp(choices=[_Choice(message=_Msg(
            content=json.dumps({"level": level, "reason": "test"})
        ))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        return [[0.0] * 8 for _ in texts]


def _setup(tmp_path: Path) -> tuple[Path, int, dict[int, int]]:
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="support test", archetype_ids=["scout"],
        )
        id_map = {
            i: add_entry(
                conn, project_id=pid, kind=KIND_EVIDENCE,
                content=f"chunk-{i}", turn=0, agent_id=None,
            )
            for i in (1, 2, 3)
        }
    return db, pid, id_map


def _claims_with_ids(id_map: dict[int, int]) -> str:
    return (
        CLAIMS_MD
        .replace("[src #1]", f"[src #{id_map[1]}]")
        .replace("[src #2]", f"[src #{id_map[2]}]")
        .replace("[src #3]", f"[src #{id_map[3]}]")
    )


# ---------------------------------------------------------------------------
# Score calculation
# ---------------------------------------------------------------------------


def test_support_result_score_all_direct():
    r = PGRSupportResult(direct=3, partial=0, off_topic=0)
    assert r.score == 1.0


def test_support_result_score_all_partial():
    r = PGRSupportResult(direct=0, partial=4, off_topic=0)
    assert r.score == 0.5


def test_support_result_score_mixed():
    # 2 direct (2*2=4) + 1 partial (1*1=1) + 1 off_topic (0) = 5 / (2*4=8) = 0.625
    r = PGRSupportResult(direct=2, partial=1, off_topic=1)
    assert abs(r.score - 0.625) < 1e-6


def test_support_result_empty_score_is_zero():
    r = PGRSupportResult()
    assert r.score == 0.0


# ---------------------------------------------------------------------------
# End-to-end: pgr_support reads claims, calls judge, aggregates
# ---------------------------------------------------------------------------


def test_pgr_support_all_direct(tmp_path: Path):
    db, pid, id_map = _setup(tmp_path)
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(_claims_with_ids(id_map), encoding="utf-8")
    judge = _LevelJudge(levels=[2, 2, 2])  # 3 citations, all level=2
    with connect(db) as conn:
        result = pgr_support(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
        )
    assert result.direct == 3
    assert result.partial == 0
    assert result.off_topic == 0
    assert result.score == 1.0
    assert judge.calls == 3


def test_pgr_support_synthesis_scored_as_partial(tmp_path: Path):
    """The interesting case: claim is a higher-level synthesis that chunks
    partially support (level=1) rather than directly (level=2)."""
    db, pid, id_map = _setup(tmp_path)
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(_claims_with_ids(id_map), encoding="utf-8")
    # All 3 citations rated as "partial support" — classic synthesis scenario
    judge = _LevelJudge(levels=[1, 1, 1])
    with connect(db) as conn:
        result = pgr_support(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
        )
    assert result.direct == 0
    assert result.partial == 3
    assert result.off_topic == 0
    assert result.score == 0.5


def test_pgr_support_mixed_verdicts(tmp_path: Path):
    db, pid, id_map = _setup(tmp_path)
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(_claims_with_ids(id_map), encoding="utf-8")
    judge = _LevelJudge(levels=[2, 1, 0])
    with connect(db) as conn:
        result = pgr_support(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
        )
    assert result.direct == 1
    assert result.partial == 1
    assert result.off_topic == 1
    # (1*2 + 1*1 + 0) / (2*3) = 3/6 = 0.5
    assert result.score == 0.5


def test_pgr_support_handles_missing_source(tmp_path: Path):
    db, pid, id_map = _setup(tmp_path)
    # Reference a src id that does not exist
    bad = CLAIMS_MD.replace("[src #1]", "[src #99999]") \
                   .replace("[src #2]", f"[src #{id_map[2]}]") \
                   .replace("[src #3]", f"[src #{id_map[3]}]")
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(bad, encoding="utf-8")
    judge = _LevelJudge(levels=[2, 2])  # Only 2 real citations get judged
    with connect(db) as conn:
        result = pgr_support(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
        )
    # 1 missing source marked off_topic; 2 direct
    assert result.direct == 2
    assert result.off_topic == 1
    # (2*2 + 0*1 + 0) / (2*3) = 4/6 = 0.667
    assert abs(result.score - 4/6) < 1e-6


def test_pgr_support_invalid_level_falls_back_to_zero(tmp_path: Path):
    db, pid, id_map = _setup(tmp_path)
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(_claims_with_ids(id_map), encoding="utf-8")

    class _BadJudge:
        """Always returns level=5 (out of range)."""
        def chat(self, role, messages, **kwargs):
            return _Resp(choices=[_Choice(message=_Msg(
                content=json.dumps({"level": 5, "reason": "nope"})
            ))])
        def embed(self, role, texts):
            return [[0.0]]

    with connect(db) as conn:
        result = pgr_support(
            conn, project_id=pid, llm=_BadJudge(), claims_md_path=claims_path,
        )
    # All treated as off_topic when level is invalid
    assert result.off_topic == 3
    assert result.score == 0.0

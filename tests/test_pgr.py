"""Tests for PGR proxies: citation-trace verifiability + held-out evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.ingest import _is_held_out
from research_pipeline.pgr import (
    ClaimBlock,
    PGRCiteResult,
    compute_composite,
    parse_claims_md,
    persist_pgr,
    pgr_cite,
    pgr_heldout,
    score_project,
)
from research_pipeline.projects import create_project, upsert_user


CLAIMS_MD = """# Claims

## C1: Zep outperforms MemGPT on DMR.
- Confidence: high
- Supporting: [src #1]
- Falsifier: "Wrong if DMR results show Zep ≤ MemGPT."
- Status: supported

## C2: PROTACs bypass Cys12 resistance.
- Confidence: medium
- Supporting: [src #2], [src #3]
- Falsifier: "Wrong if PROTAC resistance mutations are demonstrated."
- Status: unverified
"""


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _FakeJudge:
    """Returns canned verdicts in order."""

    def __init__(self, verdicts: list[str]):
        self._q = list(verdicts)
        self.calls = 0

    def chat(self, role, messages, **kwargs):
        self.calls += 1
        verdict = self._q.pop(0) if self._q else "neutral"
        return _Resp(choices=[_Choice(message=_Msg(
            content=json.dumps({"verdict": verdict, "reason": "test"})
        ))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        # Simple first-word axis encoding
        axes: dict[str, int] = {}
        vecs = []
        for t in texts:
            first = (t.strip().lower().split() or [""])[0]
            if first not in axes:
                axes[first] = len(axes)
            v = [0.0] * 64
            v[axes[first] % 64] = 1.0
            vecs.append(v)
        return vecs


# ---------------------------------------------------------------------------
# _is_held_out deterministic partitioning
# ---------------------------------------------------------------------------


def test_is_held_out_deterministic():
    # Same content -> same bucket across calls
    assert _is_held_out("hello world") == _is_held_out("hello world")
    # Different content may land in different buckets
    n = 200
    held_out = sum(1 for i in range(n) if _is_held_out(f"chunk {i}"))
    # 20% ± 10% tolerance
    assert 0.1 * n <= held_out <= 0.3 * n


# ---------------------------------------------------------------------------
# parse_claims_md
# ---------------------------------------------------------------------------


def test_parse_claims_md_extracts_blocks_and_refs(tmp_path: Path):
    p = tmp_path / "claims.md"
    p.write_text(CLAIMS_MD, encoding="utf-8")
    blocks = parse_claims_md(p)
    assert len(blocks) == 2
    assert blocks[0].id == "C1"
    assert blocks[0].src_refs == [1]
    assert blocks[1].id == "C2"
    assert blocks[1].src_refs == [2, 3]


def test_parse_claims_md_empty_file(tmp_path: Path):
    p = tmp_path / "claims.md"
    p.write_text("# Claims\n\n_(none)_\n", encoding="utf-8")
    assert parse_claims_md(p) == []


def test_parse_claims_md_missing_file(tmp_path: Path):
    assert parse_claims_md(tmp_path / "nonexistent.md") == []


# ---------------------------------------------------------------------------
# pgr_cite
# ---------------------------------------------------------------------------


def _setup_project_with_evidence(tmp_path: Path) -> tuple[Path, int, dict[int, int]]:
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="score test",
            archetype_ids=["scout"],
        )
        # Insert evidence chunks that will be cited as [src #N]
        id_map = {}
        contents = [
            "Zep outperforms MemGPT in DMR benchmarks (94.8% vs 93.4%).",
            "PROTAC degradation exploits Switch II binding.",
            "PROTAC efficacy on Cys12-resistant variants was reported.",
        ]
        for i, c in enumerate(contents, start=1):
            eid = add_entry(
                conn, project_id=pid, kind=KIND_EVIDENCE,
                content=c, turn=0, agent_id=None,
                refs=[f"source=paper_{i}.pdf"],
            )
            id_map[i] = eid
    return db, pid, id_map


def test_pgr_cite_all_supported(tmp_path: Path):
    db, pid, id_map = _setup_project_with_evidence(tmp_path)
    # Remap [src #N] in claims.md to actual blackboard ids
    remapped = CLAIMS_MD.replace("[src #1]", f"[src #{id_map[1]}]") \
                        .replace("[src #2]", f"[src #{id_map[2]}]") \
                        .replace("[src #3]", f"[src #{id_map[3]}]")
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(remapped, encoding="utf-8")

    # 3 citations total (C1: 1, C2: 2) -> 3 judge calls -> all support
    judge = _FakeJudge(verdicts=["support", "support", "support"])
    with connect(db) as conn:
        result = pgr_cite(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
        )
    assert result.total == 3
    assert result.supports == 3
    assert result.score == 1.0
    assert judge.calls == 3


def test_pgr_cite_mixed_verdicts(tmp_path: Path):
    db, pid, id_map = _setup_project_with_evidence(tmp_path)
    remapped = CLAIMS_MD.replace("[src #1]", f"[src #{id_map[1]}]") \
                        .replace("[src #2]", f"[src #{id_map[2]}]") \
                        .replace("[src #3]", f"[src #{id_map[3]}]")
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(remapped, encoding="utf-8")

    judge = _FakeJudge(verdicts=["support", "contradict", "neutral"])
    with connect(db) as conn:
        result = pgr_cite(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
        )
    assert result.total == 3
    assert result.supports == 1 and result.contradicts == 1 and result.neutrals == 1
    assert result.score == 1 / 3


def test_pgr_cite_missing_source_degrades_gracefully(tmp_path: Path):
    db, pid, id_map = _setup_project_with_evidence(tmp_path)
    # Reference a src id that does not exist
    bad = CLAIMS_MD.replace("[src #1]", "[src #99999]") \
                   .replace("[src #2]", f"[src #{id_map[2]}]") \
                   .replace("[src #3]", f"[src #{id_map[3]}]")
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(bad, encoding="utf-8")

    judge = _FakeJudge(verdicts=["support", "support"])
    with connect(db) as conn:
        result = pgr_cite(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
        )
    # C1's citation is missing -> recorded as missing_source but not counted
    # in supports/contradicts/neutrals; C2's two citations both support.
    assert result.total == 2
    assert result.supports == 2
    assert any(d["verdict"] == "missing_source" for d in result.details)


# ---------------------------------------------------------------------------
# pgr_heldout
# ---------------------------------------------------------------------------


def test_pgr_heldout_uses_only_heldout_chunks(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="heldout test",
            archetype_ids=["scout"],
        )
        # Seed 2 visible + 2 held-out evidence chunks with embeddings
        llm = _FakeJudge(verdicts=[])
        import json as _json
        for i, (content, vis) in enumerate([
            ("zep memgpt dmr", "visible"),
            ("protac scaffold", "visible"),
            ("zep stress test coding 0.47", "held_out"),
            ("protac resistance variant confirmed", "held_out"),
        ]):
            eid = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                            content=content, turn=0, agent_id=None)
            emb = llm.embed("embedding", content)[0]
            conn.execute(
                "UPDATE blackboard_entries SET embedding_json = ?, visibility = ? "
                "WHERE id = ?",
                (_json.dumps(emb), vis, eid),
            )
        conn.commit()

    claims_path = tmp_path / "claims.md"
    claims_path.write_text(
        "# Claims\n\n"
        "## C1: zep holds up across tasks.\n- Status: supported\n\n"
        "## C2: protac mechanism.\n- Status: unverified\n",
        encoding="utf-8",
    )

    # Two claims, k=3 each, but only 2 held-out chunks -> at most 2 judgments per claim
    judge = _FakeJudge(verdicts=["support", "contradict"] * 2)
    with connect(db) as conn:
        result = pgr_heldout(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
            per_claim_k=3,
        )
    total = result.supports + result.contradicts + result.neutrals
    assert total >= 2  # each claim rated against at least one held-out chunk


def test_pgr_heldout_no_heldout_chunks(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="no heldout",
            archetype_ids=["scout"],
        )
    claims_path = tmp_path / "claims.md"
    claims_path.write_text(
        "# Claims\n\n## C1: claim with no held-out backing.\n- Status: unverified\n",
        encoding="utf-8",
    )
    judge = _FakeJudge(verdicts=[])
    with connect(db) as conn:
        result = pgr_heldout(
            conn, project_id=pid, llm=judge, claims_md_path=claims_path,
        )
    assert result.skipped_no_heldout == 1
    assert result.score == 0.0


# ---------------------------------------------------------------------------
# compute_composite + persist
# ---------------------------------------------------------------------------


def test_compute_composite_weighted_mean():
    from research_pipeline.pgr import PGRAdvResult, PGRHeldoutResult
    cite = PGRCiteResult(supports=4, contradicts=0, neutrals=0)  # 1.0
    heldout = PGRHeldoutResult(supports=3, contradicts=1, neutrals=1)  # (3-1)/5 = 0.4
    adv = PGRAdvResult(claims_tested=5, undermined=1, survived=4)  # 0.8
    comp = compute_composite(cite, heldout, adv, weights=(0.5, 0.3, 0.2))
    expected = 1.0 * 0.5 + 0.4 * 0.3 + 0.8 * 0.2
    assert abs(comp.composite - expected) < 1e-6


def test_pgr_adversarial_uses_red_team_role_when_available(tmp_path: Path):
    """If the adapter has a `red_team` role configured, pgr_adversarial
    routes the Red Team call through it (for cross-model pressure). Absent
    that role, falls back to `judge`."""
    from research_pipeline.pgr import _red_team_role

    class _FakeLLM:
        def __init__(self, roles: set[str]):
            self._roles = roles
        def role_info(self, role: str):
            if role not in self._roles:
                raise KeyError(role)
            return object()

    # No red_team role -> falls back
    assert _red_team_role(_FakeLLM({"judge", "agent_bulk"})) == "judge"
    # red_team role present -> uses it
    assert _red_team_role(_FakeLLM({"judge", "red_team"})) == "red_team"


def test_persist_pgr_writes_kpi_rows(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="persist test",
                             archetype_ids=["scout"])
    from research_pipeline.pgr import PGRAdvResult, PGRHeldoutResult
    cite = PGRCiteResult(supports=3, contradicts=0, neutrals=0)
    heldout = PGRHeldoutResult(supports=2, contradicts=0, neutrals=1)
    adv = PGRAdvResult(claims_tested=4, undermined=1, survived=3)
    comp = compute_composite(cite, heldout, adv)
    with connect(db) as conn:
        persist_pgr(conn, project_id=pid, turn=5, composite=comp)
        rows = conn.execute(
            "SELECT metric, value, turn FROM kpi_scores WHERE project_id = ? "
            "ORDER BY metric",
            (pid,),
        ).fetchall()
    metrics = {r["metric"]: r["value"] for r in rows}
    assert metrics["pgr_cite"] == 1.0
    assert abs(metrics["pgr_heldout"] - 2 / 3) < 1e-6
    assert metrics["pgr_adv"] == 0.75
    assert "pgr_composite" in metrics
    assert all(r["turn"] == 5 for r in rows)

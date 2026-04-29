"""Tests for Phase-3+ additions: API PGR config endpoints, LLM-refined
planner, and the triangulation proxy."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from research_pipeline.blackboard import KIND_EVIDENCE, KIND_HYPOTHESIS, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.pgr_planner import PGRProxySpec, _llm_refine_plan, PGRPlan
from research_pipeline.projects import create_project, get_project, upsert_user
from research_pipeline.triangulate import _extract_claim_titles, triangulate_project


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _FakeLLM:
    """Returns pre-seeded responses per call; embeds via first-token axis."""

    def __init__(self, responses: list[str]):
        self._q = list(responses)
        self.chat_calls = 0
        self.achat_calls = 0
        self._axes: dict[str, int] = {}

    def chat(self, role, messages, **kwargs):
        self.chat_calls += 1
        text = self._q.pop(0) if self._q else ""
        return _Resp(choices=[_Choice(message=_Msg(content=text))])

    async def achat(self, role, messages, **kwargs):
        self.achat_calls += 1
        text = self._q.pop(0) if self._q else ""
        return _Resp(choices=[_Choice(message=_Msg(content=text))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            first = (t.strip().lower().split() or [""])[0]
            if first not in self._axes:
                self._axes[first] = len(self._axes)
            v = [0.0] * 64
            v[self._axes[first] % 64] = 1.0
            out.append(v)
        return out

    def role_info(self, role):
        return object()


# ---------------------------------------------------------------------------
# API: GET / PUT /api/projects/{pid}/pgr-config
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> tuple[Path, int]:
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="api pgr test",
            archetype_ids=["scout", "hypogen"],
        )
    return db, pid


def test_api_get_pgr_config_returns_current_and_recommendation(tmp_path: Path, monkeypatch):
    db, pid = _setup_project(tmp_path)
    monkeypatch.setenv("RP_DB_PATH", str(db))
    from research_pipeline.api import app
    client = TestClient(app)
    r = client.get(f"/api/projects/{pid}/pgr-config")
    assert r.status_code == 200
    body = r.json()
    assert "current" in body and "recommended" in body
    assert "recommendation" in body and len(body["recommendation"]) == 3
    ids = {p["id"] for p in body["recommendation"]}
    assert ids == {"pgr_cite", "pgr_heldout", "pgr_adv"}


def test_api_put_pgr_config_persists(tmp_path: Path, monkeypatch):
    db, pid = _setup_project(tmp_path)
    monkeypatch.setenv("RP_DB_PATH", str(db))
    from research_pipeline.api import app
    client = TestClient(app)
    new_cfg = {
        "proxies": {
            "pgr_cite": {"enabled": True, "weight": 0.6},
            "pgr_heldout": {"enabled": True, "weight": 0.4},
            "pgr_adv": {"enabled": False, "weight": 0.0},
        }
    }
    r = client.put(f"/api/projects/{pid}/pgr-config", json=new_cfg)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Confirm persisted
    with connect(db) as conn:
        p = get_project(conn, pid)
    assert p.pgr_config["proxies"]["pgr_cite"]["weight"] == 0.6
    assert p.pgr_config["proxies"]["pgr_adv"]["enabled"] is False


# ---------------------------------------------------------------------------
# LLM-refined planner
# ---------------------------------------------------------------------------


def test_llm_refine_plan_nudges_weights_within_bounds():
    baseline = PGRPlan(
        project_id=1,
        proxies=[
            PGRProxySpec("pgr_cite", "Cite", 0.5, True, "r1", True),
            PGRProxySpec("pgr_heldout", "HO", 0.3, True, "r2", True),
            PGRProxySpec("pgr_adv", "Adv", 0.2, True, "r3", True),
        ],
        composite_formula="...",
        notes=[],
    )
    # LLM wants cite very high (within the ±0.2 clamp -> cap at 0.7)
    llm_resp = json.dumps({
        "proxies": {
            "pgr_cite": {"weight": 0.95, "enabled": True},
            "pgr_heldout": {"weight": 0.0, "enabled": True},
            "pgr_adv": {"weight": 0.05, "enabled": True},
        },
        "rationale": "this looks like a literature-review goal",
    })
    llm = _FakeLLM([llm_resp])
    refined = _llm_refine_plan(baseline, "literature review of KRAS inhibitors", llm)
    cite = next(p for p in refined.proxies if p.id == "pgr_cite")
    # Clamped: baseline 0.5 ± 0.2 = [0.3, 0.7], renormalized to sum=1.0
    # Pre-normalize weights: cite=0.7, heldout=0.1 (0.3-0.2), adv=0.0 (0.2-0.2)
    # Sum = 0.8; cite normalized = 0.875
    assert cite.weight <= 0.90 and cite.weight >= 0.5
    total = sum(p.weight for p in refined.proxies if p.enabled)
    assert abs(total - 1.0) < 1e-6


def test_llm_refine_plan_falls_back_on_bad_json():
    baseline = PGRPlan(
        project_id=1,
        proxies=[
            PGRProxySpec("pgr_cite", "Cite", 0.5, True, "r", True),
            PGRProxySpec("pgr_heldout", "HO", 0.3, True, "r", True),
            PGRProxySpec("pgr_adv", "Adv", 0.2, True, "r", True),
        ],
        composite_formula="x",
        notes=[],
    )
    llm = _FakeLLM(["not valid json"])
    refined = _llm_refine_plan(baseline, "goal", llm)
    # Plan returned unchanged
    assert refined.proxies[0].weight == 0.5
    assert refined.proxies[1].weight == 0.3
    assert refined.proxies[2].weight == 0.2


def test_llm_refine_plan_does_not_enable_disabled_proxies():
    baseline = PGRPlan(
        project_id=1,
        proxies=[
            PGRProxySpec("pgr_cite", "Cite", 0.7, True, "r", True),
            PGRProxySpec("pgr_heldout", "HO", 0.0, False, "r", False),
            PGRProxySpec("pgr_adv", "Adv", 0.3, True, "r", True),
        ],
        composite_formula="x",
        notes=[],
    )
    llm_resp = json.dumps({
        "proxies": {
            "pgr_heldout": {"weight": 0.5, "enabled": True},
        }
    })
    llm = _FakeLLM([llm_resp])
    refined = _llm_refine_plan(baseline, "g", llm)
    ho = next(p for p in refined.proxies if p.id == "pgr_heldout")
    assert ho.enabled is False  # refusal to flip enabled status


# ---------------------------------------------------------------------------
# Triangulation proxy
# ---------------------------------------------------------------------------


def test_extract_claim_titles_from_claims_md():
    md = (
        "# Claims\n\n"
        "## C1: Zep outperforms MemGPT on DMR.\n- Confidence: high\n\n"
        "## C2: PROTACs bypass Cys12 resistance.\n- Status: unverified\n\n"
        "## C10: Nonsense claim.\n"
    )
    titles = _extract_claim_titles(md)
    assert len(titles) == 3
    assert "Zep outperforms MemGPT on DMR." in titles[0]
    assert "PROTACs" in titles[1]
    assert titles[2].startswith("Nonsense")


def test_triangulate_identical_runs_scores_high(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="triangulate test",
            archetype_ids=["scout", "hypogen", "critic"],
        )
        agents = list(conn.execute(
            "SELECT id FROM agents WHERE project_id=?", (pid,)
        ))
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                  content="evidence chunk", turn=0, agent_id=agents[0]["id"])
        add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                  content="hypothesis one", turn=0, agent_id=agents[1]["id"])

    # All three runs return the same claims.md -> similarity should be high
    same_response = (
        "# Claims\n\n"
        "## C1: Zep wins DMR.\n- Confidence: high\n\n"
        "## C2: PROTAC resistance is real.\n- Status: unverified\n"
    )
    llm = _FakeLLM([same_response, same_response, same_response])
    with connect(db) as conn:
        result = asyncio.run(
            triangulate_project(conn, project_id=pid, llm=llm, n_runs=3)
        )
    assert result.n_runs == 3
    assert result.per_run_claim_counts == [2, 2, 2]
    # All runs identical -> first-word axis matches, best cosines = 1.0
    assert result.score > 0.99


def test_triangulate_disjoint_runs_scores_low(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="disjoint test",
                             archetype_ids=["scout"])
        agents = list(conn.execute(
            "SELECT id FROM agents WHERE project_id=?", (pid,)
        ))
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                  content="e1", turn=0, agent_id=agents[0]["id"])

    run1 = "# Claims\n\n## C1: alpha foo\n## C2: beta bar\n"
    run2 = "# Claims\n\n## C1: gamma baz\n## C2: delta qux\n"
    run3 = "# Claims\n\n## C1: epsilon zot\n## C2: zeta frob\n"
    llm = _FakeLLM([run1, run2, run3])
    with connect(db) as conn:
        result = asyncio.run(
            triangulate_project(conn, project_id=pid, llm=llm, n_runs=3)
        )
    # All claims use distinct first tokens -> pairwise cos = 0
    assert result.score < 0.1


def test_triangulate_handles_empty_runs_gracefully(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="empty",
                             archetype_ids=["scout"])

    # All runs produce empty claims
    llm = _FakeLLM(["", "", ""])
    with connect(db) as conn:
        result = asyncio.run(
            triangulate_project(conn, project_id=pid, llm=llm, n_runs=3)
        )
    assert result.score == 0.0
    assert result.per_run_claim_counts == [0, 0, 0]

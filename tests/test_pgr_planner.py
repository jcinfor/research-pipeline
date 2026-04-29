"""Tests for PGR proxy recommender + config override + override-aware scoring."""
from __future__ import annotations

import json
from pathlib import Path

from research_pipeline.blackboard import KIND_EVIDENCE, KIND_HYPOTHESIS, add_entry
from research_pipeline.db import connect, init_db
from research_pipeline.pgr_planner import (
    PROXY_IDS,
    _project_stats,
    parse_override,
    plan_to_config,
    recommend_pgr_plan,
    resolve_effective_weights,
)
from research_pipeline.projects import create_project, get_project, update_pgr_config, upsert_user


def _seed(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="planner test", archetype_ids=["scout", "hypogen"],
        )
    return db, pid


# --- _project_stats -----------------------------------------------------


def test_project_stats_counts_correctly(tmp_path: Path):
    db, pid = _seed(tmp_path)
    with connect(db) as conn:
        # 2 visible ingested chunks, 1 held-out, 3 hypotheses
        e1 = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                       content="visible chunk 1", turn=0, agent_id=None)
        e2 = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                       content="visible chunk 2", turn=0, agent_id=None)
        e3 = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                       content="held-out chunk", turn=0, agent_id=None)
        conn.execute(
            "UPDATE blackboard_entries SET visibility='held_out' WHERE id=?", (e3,),
        )
        # Agent-filed evidence should NOT count as "visible_chunks" (those are
        # meant to count ingested material only, not agent posts)
        agents = list(conn.execute("SELECT id FROM agents WHERE project_id=?", (pid,)))
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                  content="agent-filed evidence", turn=1,
                  agent_id=agents[0]["id"])
        for i in range(3):
            add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                      content=f"hyp {i}", turn=0, agent_id=agents[1]["id"])
        conn.commit()

        s = _project_stats(conn, pid)

    assert s["visible_chunks"] == 2
    assert s["heldout_chunks"] == 1
    assert s["hypothesis_count"] == 3
    assert s["agent_count"] == 2


# --- recommend_pgr_plan -------------------------------------------------


def test_plan_with_sufficient_material_enables_all_three(tmp_path: Path):
    db, pid = _seed(tmp_path)
    with connect(db) as conn:
        # 5 held-out chunks -> heldout enabled
        for i in range(5):
            eid = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                            content=f"held-out {i}", turn=0, agent_id=None)
            conn.execute(
                "UPDATE blackboard_entries SET visibility='held_out' WHERE id=?", (eid,),
            )
        # 3 hypotheses -> adv enabled
        agents = list(conn.execute("SELECT id FROM agents WHERE project_id=?", (pid,)))
        for i in range(3):
            add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                      content=f"hyp {i}", turn=0, agent_id=agents[0]["id"])
        conn.commit()
        plan = recommend_pgr_plan(conn, pid)

    by_id = {p.id: p for p in plan.proxies}
    assert by_id["pgr_cite"].enabled
    assert by_id["pgr_heldout"].enabled
    assert by_id["pgr_adv"].enabled
    # Weights sum to ~1.0
    total = sum(p.weight for p in plan.proxies if p.enabled)
    assert abs(total - 1.0) < 1e-6


def test_plan_disables_heldout_when_too_few_chunks(tmp_path: Path):
    db, pid = _seed(tmp_path)
    with connect(db) as conn:
        # Only 2 held-out chunks (below threshold of 3)
        for i in range(2):
            eid = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                            content=f"held-out {i}", turn=0, agent_id=None)
            conn.execute(
                "UPDATE blackboard_entries SET visibility='held_out' WHERE id=?", (eid,),
            )
        agents = list(conn.execute("SELECT id FROM agents WHERE project_id=?", (pid,)))
        for i in range(2):
            add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                      content=f"hyp {i}", turn=0, agent_id=agents[0]["id"])
        conn.commit()
        plan = recommend_pgr_plan(conn, pid)

    by_id = {p.id: p for p in plan.proxies}
    assert by_id["pgr_cite"].enabled
    assert not by_id["pgr_heldout"].enabled
    assert by_id["pgr_adv"].enabled
    # Mass redistributed: disabled heldout's weight should go to cite+adv
    total = sum(p.weight for p in plan.proxies if p.enabled)
    assert abs(total - 1.0) < 1e-6
    # Notes should explain the disable
    assert any("pgr_heldout disabled" in n for n in plan.notes)


def test_plan_disables_adv_when_no_hypotheses(tmp_path: Path):
    db, pid = _seed(tmp_path)
    with connect(db) as conn:
        # Enough held-out, zero hypotheses
        for i in range(5):
            eid = add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                            content=f"h {i}", turn=0, agent_id=None)
            conn.execute(
                "UPDATE blackboard_entries SET visibility='held_out' WHERE id=?", (eid,),
            )
        conn.commit()
        plan = recommend_pgr_plan(conn, pid)

    by_id = {p.id: p for p in plan.proxies}
    assert by_id["pgr_adv"].enabled is False
    assert any("pgr_adv disabled" in n for n in plan.notes)


def test_plan_lists_future_proxies_in_notes(tmp_path: Path):
    db, pid = _seed(tmp_path)
    with connect(db) as conn:
        plan = recommend_pgr_plan(conn, pid)
    joined = " ".join(plan.notes)
    assert "triangulation" in joined
    assert "execution" in joined


# --- plan_to_config + parse_override + resolve_effective_weights ---------


def test_plan_to_config_serializes_cleanly(tmp_path: Path):
    db, pid = _seed(tmp_path)
    with connect(db) as conn:
        plan = recommend_pgr_plan(conn, pid)
    cfg = plan_to_config(plan)
    assert set(cfg["proxies"]) == set(PROXY_IDS)
    for entry in cfg["proxies"].values():
        assert "weight" in entry and "enabled" in entry
        assert isinstance(entry["weight"], float)
        assert isinstance(entry["enabled"], bool)


def test_parse_override_respects_skip_flags():
    cfg = parse_override(cite=0.6, heldout=0.4, skip_adv=True)
    # skip_adv forces pgr_adv disabled
    assert cfg["proxies"]["pgr_adv"]["enabled"] is False
    assert cfg["proxies"]["pgr_adv"]["weight"] == 0.0
    # Remaining weights renormalized
    cite_w = cfg["proxies"]["pgr_cite"]["weight"]
    ho_w = cfg["proxies"]["pgr_heldout"]["weight"]
    assert abs(cite_w + ho_w - 1.0) < 1e-6
    assert cite_w > ho_w  # original 0.6 > 0.4 preserved proportionally


def test_parse_override_with_zero_weight_disables():
    cfg = parse_override(cite=0.7, heldout=0.0, adv=0.3)
    # heldout=0 means enabled=False under our rule (weight must be >0)
    assert cfg["proxies"]["pgr_heldout"]["enabled"] is False
    assert cfg["proxies"]["pgr_cite"]["enabled"] is True
    assert cfg["proxies"]["pgr_adv"]["enabled"] is True


def test_resolve_effective_weights_empty_config_uses_defaults():
    weights = resolve_effective_weights({})
    assert weights["pgr_cite"] == (True, 0.4)
    assert weights["pgr_heldout"] == (True, 0.3)
    assert weights["pgr_adv"] == (True, 0.3)


def test_resolve_effective_weights_reads_stored_config():
    cfg = {"proxies": {
        "pgr_cite": {"enabled": True, "weight": 0.7},
        "pgr_heldout": {"enabled": False, "weight": 0.0},
        "pgr_adv": {"enabled": True, "weight": 0.3},
    }}
    weights = resolve_effective_weights(cfg)
    assert weights["pgr_cite"] == (True, 0.7)
    assert weights["pgr_heldout"] == (False, 0.0)
    assert weights["pgr_adv"] == (True, 0.3)


# --- integration: Project dataclass carries config -----------------------


def test_update_pgr_config_persists_and_reloads(tmp_path: Path):
    db, pid = _seed(tmp_path)
    new_cfg = parse_override(cite=0.5, heldout=0.3, adv=0.2)
    with connect(db) as conn:
        update_pgr_config(conn, project_id=pid, config=new_cfg)
        p = get_project(conn, pid)
    assert p.pgr_config == new_cfg
    # Round-trip JSON
    roundtripped = json.loads(json.dumps(p.pgr_config))
    assert roundtripped == new_cfg

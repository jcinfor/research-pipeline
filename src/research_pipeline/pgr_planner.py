"""Per-project PGR proxy recommender + config override helpers.

Inspects a project's state (corpus size, held-out partition, hypothesis count)
and proposes which PGR proxies to enable and how to weight them. The CLI
presents the recommendation; user either accepts it (`--apply`) or overrides
weights via `rp project pgr-set`.

Pattern: system proposes sensible defaults from observable project state,
user overrides as needed — same pattern we use for `--archetypes auto` and
for the per-agent config decision tree in optimize.py.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .blackboard import KIND_EVIDENCE, KIND_HYPOTHESIS


# --- proxy catalog --------------------------------------------------------

# Currently implemented
PROXY_IDS = ("pgr_cite", "pgr_heldout", "pgr_adv")

# Not yet implemented — surfaced in the planner output as "future" so the user
# knows what's on the roadmap without us pretending we can score them.
FUTURE_PROXY_IDS = (
    "pgr_triangulation",
    "pgr_novelty_vs_wiki",
    "pgr_execution",
)


@dataclass(frozen=True)
class PGRProxySpec:
    id: str
    name: str
    weight: float
    enabled: bool
    rationale: str
    requirements_met: bool


@dataclass
class PGRPlan:
    project_id: int
    proxies: list[PGRProxySpec]
    composite_formula: str
    notes: list[str]


# --- project stats helper -------------------------------------------------


def _project_stats(conn: sqlite3.Connection, project_id: int) -> dict[str, int]:
    def count(sql: str, params: tuple) -> int:
        row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    return {
        "visible_chunks": count(
            "SELECT COUNT(*) FROM blackboard_entries "
            "WHERE project_id = ? AND kind = ? "
            "AND COALESCE(visibility, 'visible') = 'visible' AND agent_id IS NULL",
            (project_id, KIND_EVIDENCE),
        ),
        "heldout_chunks": count(
            "SELECT COUNT(*) FROM blackboard_entries "
            "WHERE project_id = ? AND kind = ? AND visibility = 'held_out'",
            (project_id, KIND_EVIDENCE),
        ),
        "hypothesis_count": count(
            "SELECT COUNT(*) FROM blackboard_entries "
            "WHERE project_id = ? AND kind = ?",
            (project_id, KIND_HYPOTHESIS),
        ),
        "agent_count": count(
            "SELECT COUNT(*) FROM agents WHERE project_id = ?",
            (project_id,),
        ),
    }


# --- recommender ---------------------------------------------------------


_LLM_REFINE_SYSTEM = """You are the PGR Planner refinement layer. You receive
a rule-based baseline PGR proxy plan and the project's research goal, and
you propose small adjustments to the weights based on the goal's domain.

Rules:
- Keep all enabled proxies enabled; do not add proxies that weren't in the baseline.
- Only nudge weights, not enable/disable. Max change per weight: 0.2.
- Enabled weights must sum to 1.0 after your adjustment (renormalize if needed).
- Favor pgr_cite for literature review / synthesis goals.
- Favor pgr_heldout for method evaluation / comparison goals.
- Favor pgr_adv for forecasting / strategic / speculative goals.

Respond with JSON only:
{"proxies": {"pgr_cite": {"weight": N, "enabled": bool}, ...}, "rationale": "..."}
"""


def _llm_refine_plan(plan: PGRPlan, goal: str, llm) -> PGRPlan:
    """Ask the planner role to nudge weights based on goal domain. Returns
    the plan unchanged on any failure — refinement is best-effort."""
    baseline = plan_to_config(plan)
    user_msg = (
        f"RESEARCH GOAL: {goal}\n\n"
        f"BASELINE PGR PLAN (weights from rule-based recommender):\n"
        f"{json.dumps(baseline, indent=2)}\n\n"
        f"Propose small adjustments to the weights based on the goal's domain."
    )
    try:
        resp = llm.chat(
            "planner",
            messages=[
                {"role": "system", "content": _LLM_REFINE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            max_tokens=512,
            temperature=0.1,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return plan

    proposed = data.get("proxies", {})
    if not isinstance(proposed, dict):
        return plan

    # Clamp adjustments to max ±0.2 per proxy and preserve enabled states
    refined_specs: list[PGRProxySpec] = []
    for p in plan.proxies:
        suggested = proposed.get(p.id, {})
        new_w = float(suggested.get("weight", p.weight))
        new_w = max(p.weight - 0.2, min(p.weight + 0.2, new_w))
        new_w = max(0.0, min(1.0, new_w))
        refined_specs.append(
            PGRProxySpec(
                id=p.id, name=p.name,
                weight=new_w if p.enabled else 0.0,
                enabled=p.enabled,  # enabled status is not LLM-adjustable
                rationale=p.rationale,
                requirements_met=p.requirements_met,
            )
        )
    refined_specs = _normalize_weights(refined_specs)

    composite = (
        " + ".join(f"{s.weight:.2f}*{s.id}" for s in refined_specs if s.enabled)
        or "(no enabled proxies)"
    )
    rationale = str(data.get("rationale", ""))[:300]
    notes = list(plan.notes)
    if rationale:
        notes.insert(0, f"LLM refinement: {rationale}")
    return PGRPlan(
        project_id=plan.project_id,
        proxies=refined_specs,
        composite_formula=composite,
        notes=notes,
    )


def recommend_pgr_plan(
    conn: sqlite3.Connection, project_id: int, llm=None
) -> PGRPlan:
    """Propose proxy set + weights based on observable project state.

    Rules (deterministic, no LLM):
      pgr_cite    — always enabled (every synthesize run has citations)
      pgr_heldout — enabled when held_out_chunks >= 3 (below: signal too noisy)
      pgr_adv     — enabled when hypothesis_count >= 2 (need substantive claims)

    Weights: enabled proxies share mass proportional to base weights
    (cite=0.5, heldout=0.3, adv=0.2). If a proxy is disabled, its mass is
    redistributed to the remaining enabled proxies.
    """
    s = _project_stats(conn, project_id)
    notes: list[str] = []

    base_weights = {
        "pgr_cite": 0.5,
        "pgr_heldout": 0.3,
        "pgr_adv": 0.2,
    }

    specs: list[PGRProxySpec] = []

    # pgr_cite
    specs.append(
        PGRProxySpec(
            id="pgr_cite",
            name="Citation-trace verifiability",
            weight=base_weights["pgr_cite"],
            enabled=True,
            rationale=(
                "Always applicable — judge checks every [src #N] citation in "
                "claims.md against the cited chunk for actual support."
            ),
            requirements_met=True,
        )
    )

    # pgr_heldout
    heldout_ok = s["heldout_chunks"] >= 3
    specs.append(
        PGRProxySpec(
            id="pgr_heldout",
            name="Held-out evidence alignment",
            weight=base_weights["pgr_heldout"] if heldout_ok else 0.0,
            enabled=heldout_ok,
            rationale=(
                f"{s['heldout_chunks']} held-out evidence chunks present — "
                + (
                    "enough to check claim generalization against unseen evidence."
                    if heldout_ok
                    else "need >= 3 held-out chunks to give a reliable score. "
                         "Re-ingest more material or lower the threshold."
                )
            ),
            requirements_met=heldout_ok,
        )
    )

    # pgr_adv
    adv_ok = s["hypothesis_count"] >= 2
    specs.append(
        PGRProxySpec(
            id="pgr_adv",
            name="Adversarial Red Team",
            weight=base_weights["pgr_adv"] if adv_ok else 0.0,
            enabled=adv_ok,
            rationale=(
                f"{s['hypothesis_count']} hypotheses filed — "
                + (
                    "substantive claims present; Red Team will try to undermine each."
                    if adv_ok
                    else "need >= 2 hypotheses before adversarial testing is useful. "
                         "Run more simulation turns or add hypogen archetypes."
                )
            ),
            requirements_met=adv_ok,
        )
    )

    # Normalize so enabled weights sum to 1.0
    specs = _normalize_weights(specs)

    composite = (
        " + ".join(f"{p.weight:.2f}*{p.id}" for p in specs if p.enabled)
        or "(no enabled proxies)"
    )

    if s["visible_chunks"] == 0:
        notes.append(
            "No visible evidence ingested — pgr_cite will only score "
            "agent-filed citations, which is a weaker signal."
        )
    if not heldout_ok:
        notes.append(
            "pgr_heldout disabled: held-out partition too small. "
            "A fresh ingest of 15+ chunks will enable it."
        )
    if not adv_ok:
        notes.append(
            "pgr_adv disabled: insufficient hypotheses. "
            "Run the simulation longer or weight hypogen heavier."
        )
    notes.append(
        "Future proxies (not yet implemented): "
        + ", ".join(FUTURE_PROXY_IDS)
        + "."
    )

    plan = PGRPlan(
        project_id=project_id,
        proxies=specs,
        composite_formula=composite,
        notes=notes,
    )
    if llm is not None:
        # Fetch the project goal for domain-aware refinement
        try:
            goal_row = conn.execute(
                "SELECT goal FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if goal_row and goal_row[0]:
                plan = _llm_refine_plan(plan, goal_row[0], llm)
        except Exception:
            pass
    return plan


def _normalize_weights(specs: list[PGRProxySpec]) -> list[PGRProxySpec]:
    enabled_total = sum(s.weight for s in specs if s.enabled)
    if enabled_total <= 0:
        return specs
    return [
        PGRProxySpec(
            id=s.id,
            name=s.name,
            weight=(s.weight / enabled_total) if s.enabled else 0.0,
            enabled=s.enabled,
            rationale=s.rationale,
            requirements_met=s.requirements_met,
        )
        for s in specs
    ]


# --- config serialization ------------------------------------------------


def plan_to_config(plan: PGRPlan) -> dict[str, Any]:
    """Serialize a recommended plan into the dict persisted on
    `projects.pgr_config_json`. Shape intentionally small:

        {"proxies": {"pgr_cite": {"weight": 0.5, "enabled": true}, ...}}
    """
    return {
        "proxies": {
            p.id: {"weight": float(p.weight), "enabled": bool(p.enabled)}
            for p in plan.proxies
        }
    }


def parse_override(
    *,
    cite: float | None = None,
    heldout: float | None = None,
    adv: float | None = None,
    skip_cite: bool = False,
    skip_heldout: bool = False,
    skip_adv: bool = False,
) -> dict[str, Any]:
    """Build a pgr_config from CLI override flags.

    Rules:
      - `skip_X=True` forces X disabled (weight=0).
      - Numeric weight given for X enables it (unless skip_X).
      - Weight=None for a non-skipped proxy leaves it enabled with default
        0.0 (effectively a placeholder — renormalization below moves mass
        to proxies with an explicit non-zero weight).
      - Enabled weights are renormalized to sum to 1.0.
    """
    raw = {
        "pgr_cite": (cite, skip_cite),
        "pgr_heldout": (heldout, skip_heldout),
        "pgr_adv": (adv, skip_adv),
    }
    proxies: dict[str, dict[str, Any]] = {}
    for pid, (w, skip) in raw.items():
        enabled = (not skip) and (w is None or w > 0)
        weight = float(w) if (w is not None and enabled) else 0.0
        proxies[pid] = {"weight": weight, "enabled": enabled}

    total = sum(p["weight"] for p in proxies.values() if p["enabled"])
    if total > 0:
        for p in proxies.values():
            if p["enabled"]:
                p["weight"] = p["weight"] / total
            else:
                p["weight"] = 0.0
    return {"proxies": proxies}


def resolve_effective_weights(
    project_pgr_config: dict[str, Any],
) -> dict[str, tuple[bool, float]]:
    """Given the stored project.pgr_config (possibly empty), return
    {proxy_id: (enabled, weight)} for the three shipped proxies.

    Empty config -> fall back to hard-coded defaults (0.4/0.3/0.3).
    """
    if not project_pgr_config:
        return {
            "pgr_cite": (True, 0.4),
            "pgr_heldout": (True, 0.3),
            "pgr_adv": (True, 0.3),
        }
    proxies = project_pgr_config.get("proxies", {}) or {}
    out: dict[str, tuple[bool, float]] = {}
    for pid in PROXY_IDS:
        p = proxies.get(pid, {})
        enabled = bool(p.get("enabled", True))
        weight = float(p.get("weight", 0.0))
        out[pid] = (enabled, weight)
    return out

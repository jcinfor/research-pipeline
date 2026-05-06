"""Optimization loop.

Turns the pipeline from one-shot into adaptive: run a short simulation, judge
each agent on the 6-dim rubric, identify the weakest agent, apply a targeted
configuration adjustment (temperature, specialty_focus, max_tokens), re-run.
Terminate on KPI plateau or iteration cap.

Each iteration persists a row in `optimization_traces` so the decision trail
is reproducible.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapter import LLMClient
from .kpi import M_PGR_COMPOSITE, RUBRIC_METRICS
from .per_agent_rubric import (
    AGENT_RUBRIC_METRICS,
    latest_per_agent_scores,
    weakest_agent,
)
from .projects import get_project_agents, update_agent_config


PLATEAU_THRESHOLD = 0.3  # max single-dim improvement below this counts as plateau
MIN_TEMPERATURE = 0.3
MAX_TEMPERATURE = 1.0
MIN_MAX_TOKENS = 120
MAX_MAX_TOKENS = 600


@dataclass
class Adjustment:
    action: str
    rationale: str
    temperature: float | None = None
    max_tokens: int | None = None
    specialty_focus: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {"action": self.action, "rationale": self.rationale}
        if self.temperature is not None:
            out["temperature"] = self.temperature
        if self.max_tokens is not None:
            out["max_tokens"] = self.max_tokens
        if self.specialty_focus is not None:
            out["specialty_focus"] = self.specialty_focus
        return out


@dataclass
class IterationResult:
    iteration: int
    weakest_agent_id: int | None
    weakest_metric: str | None
    decision: Adjustment | None
    kpi_before: dict[str, float]
    kpi_after: dict[str, float]
    kpi_delta: dict[str, float]
    plateau: bool = False


@dataclass
class OptimizationResult:
    project_id: int
    iterations_run: int
    terminated_reason: str
    best_iteration: int
    trace: list[IterationResult] = field(default_factory=list)


def propose_adjustment(
    *,
    weakest_metric: str,
    current_temperature: float,
    current_max_tokens: int,
    current_specialty_focus: str | None,
    project_goal: str,
) -> Adjustment:
    """Decision tree: map the weakest rubric dimension to a concrete config
    change. Keeps proposals within sensible bounds."""
    if weakest_metric == "rigor":
        new_temp = max(MIN_TEMPERATURE, round(current_temperature - 0.1, 2))
        return Adjustment(
            action="lower_temperature",
            rationale="rigor low: cooling agent to reduce output variance",
            temperature=new_temp,
        )
    if weakest_metric == "role_consistency":
        new_temp = max(MIN_TEMPERATURE, round(current_temperature - 0.1, 2))
        return Adjustment(
            action="lower_temperature",
            rationale="role_consistency low: cooling to maintain archetype voice",
            temperature=new_temp,
        )
    if weakest_metric == "novelty":
        new_temp = min(MAX_TEMPERATURE, round(current_temperature + 0.1, 2))
        return Adjustment(
            action="raise_temperature",
            rationale="novelty low: warming agent to explore more distinct angles",
            temperature=new_temp,
        )
    if weakest_metric == "relevance_to_goal":
        focus = (
            current_specialty_focus
            or f"Stay tightly anchored to the research goal: {project_goal[:120]}"
        )
        return Adjustment(
            action="set_specialty_focus",
            rationale="relevance low: constraining focus to the goal's core terms",
            specialty_focus=focus,
        )
    if weakest_metric == "collaboration_signal":
        new_max_tokens = min(MAX_MAX_TOKENS, current_max_tokens + 80)
        return Adjustment(
            action="raise_max_tokens",
            rationale=(
                "collaboration_signal low: giving the agent more room to engage "
                "with specific peer posts"
            ),
            max_tokens=new_max_tokens,
        )
    if weakest_metric == "citation_quality":
        new_temp = max(MIN_TEMPERATURE, round(current_temperature - 0.05, 2))
        return Adjustment(
            action="lower_temperature_mild",
            rationale="citation_quality low: mild cooling to reduce fabrication",
            temperature=new_temp,
        )
    return Adjustment(
        action="noop",
        rationale=f"no adjustment rule for metric '{weakest_metric}'",
    )


def _snapshot_project_rubric(
    conn: sqlite3.Connection, project_id: int
) -> dict[str, float]:
    """Snapshot includes the 4 rubric metrics + pgr_composite when present."""
    metrics = RUBRIC_METRICS + (M_PGR_COMPOSITE,)
    placeholders = ",".join("?" * len(metrics))
    rows = conn.execute(
        f"""
        SELECT metric, value FROM kpi_scores
        WHERE project_id = ? AND agent_id IS NULL AND metric IN ({placeholders})
        AND turn = (
            SELECT MAX(turn) FROM kpi_scores
            WHERE project_id = ? AND agent_id IS NULL AND metric = kpi_scores.metric
        )
        """,
        (project_id, *metrics, project_id),
    ).fetchall()
    return {r["metric"]: float(r["value"]) for r in rows}


def _rubric_delta(
    before: dict[str, float], after: dict[str, float]
) -> dict[str, float]:
    return {m: after.get(m, 0.0) - before.get(m, 0.0) for m in RUBRIC_METRICS}


def _max_abs_delta(delta: dict[str, float]) -> float:
    if not delta:
        return 0.0
    return max(abs(v) for v in delta.values())


def _persist_trace(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    iteration: int,
    weakest_agent_id: int | None,
    decision: Adjustment | None,
    kpi_before: dict[str, float],
    kpi_after: dict[str, float],
) -> None:
    conn.execute(
        """
        INSERT INTO optimization_traces
        (project_id, iteration, finished_at, weakest_agent_id,
         config_delta_json, kpi_before_json, kpi_after_json, decision_rationale)
        VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            iteration,
            weakest_agent_id,
            json.dumps(decision.as_dict()) if decision else "{}",
            json.dumps(kpi_before),
            json.dumps(kpi_after),
            decision.rationale if decision else "",
        ),
    )
    conn.commit()


def apply_adjustment(
    conn: sqlite3.Connection, *, agent_id: int, decision: Adjustment
) -> None:
    if decision.action == "noop":
        return
    update_agent_config(
        conn,
        agent_id=agent_id,
        temperature=decision.temperature,
        max_tokens=decision.max_tokens,
        specialty_focus=decision.specialty_focus,
    )


async def optimize_project(
    *,
    project_id: int,
    iterations: int,
    turns_per: int,
    db_path: Path,
    work_dir: Path,
    llm: LLMClient | None = None,
    plateau_patience: int = 2,
    objective: str = "pgr",
    project_dir: Path = Path("./projects"),
    write_iteration_summaries: bool = True,
) -> OptimizationResult:
    """Run up to `iterations` optimization cycles. Each cycle:
        1. Run a short simulation (turn_cap=turns_per, no wiki auto-promote)
        2. Per-agent rubric scores each agent
        3. Identify the weakest agent + dimension
        4. Apply a targeted config adjustment
        5. Record the trace

    `objective="pgr"` (default) uses the PGR composite score — citation-trace
    verifiability + held-out evidence alignment + adversarial Red Team — as
    the plateau signal. PGR is a Cross-Modal Anchor (verifies against source
    chunks, a different modality than agent prose), avoiding the model-as-judge
    co-evolutionary collapse that pure-rubric optimization is structurally
    susceptible to (see project-15 findings, claims C2/C3). If claims.md is
    missing on the first iteration, synthesize is run automatically.

    `objective="rubric"` falls back to project-level rubric mean for plateau
    detection. Faster (no PGR scoring per iteration), but the rubric is itself
    model-as-judge and shares the generator's training distribution — use only
    for fast iteration / smoke-tests, or when claims aren't worth the synth cost.

    Terminates on plateau (no single-dim improvement above threshold for
    `plateau_patience` consecutive iterations) or iteration cap.
    """
    from .db import connect
    from .iteration_summary import write_iteration_summary, write_optimization_index
    from .projects import get_project
    from .simulation import SimulationConfig, run_simulation

    if objective not in ("rubric", "pgr"):
        raise ValueError(f"objective must be 'rubric' or 'pgr', got {objective!r}")

    llm = llm or LLMClient()

    trace: list[IterationResult] = []
    iteration_summary_paths: list[Path] = []
    plateau_count = 0
    best_iteration = 0
    best_mean = float("-inf")
    terminated_reason = "iterations_exhausted"

    with connect(db_path) as conn:
        project = get_project(conn, project_id)

    for i in range(iterations):
        # Record the turn range BEFORE simulation so we can summarize what
        # this iteration added.
        with connect(db_path) as conn:
            kpi_before = _snapshot_project_rubric(conn, project_id)
            iter_turn_start_row = conn.execute(
                "SELECT COALESCE(MAX(turn), -1) AS t FROM blackboard_entries "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            iter_turn_start = int(iter_turn_start_row["t"]) + 1 if iter_turn_start_row else 0

        # Short simulation — no wiki spam during optimization
        try:
            await run_simulation(
                SimulationConfig(
                    project_id=project_id,
                    turn_cap=turns_per,
                    auto_promote_to_wiki=False,
                    per_agent_rubric=True,
                ),
                db_path=db_path,
                work_dir=work_dir,
                llm=llm,
            )
        except Exception as e:
            print(f"[optimize] iteration {i} simulation failed: {e}")
            terminated_reason = "simulation_error"
            break

        with connect(db_path) as conn:
            kpi_after = _snapshot_project_rubric(conn, project_id)
            per_agent = latest_per_agent_scores(conn, project_id=project_id)

            # When objective == "pgr", run the scorer each iteration so we can
            # plateau-check against research-quality signal, not the rubric.
            if objective == "pgr":
                try:
                    from .pgr import score_project
                    from .synthesize import synthesize_artifacts
                    claims_md = (
                        project_dir / f"project_{project_id}"
                        / "artifacts" / "claims.md"
                    )
                    if not claims_md.exists():
                        await synthesize_artifacts(
                            conn, project_id=project_id, llm=llm,
                            project_dir=project_dir,
                        )
                    comp_before = kpi_before.get(M_PGR_COMPOSITE, 0.0)
                    comp = score_project(
                        conn, project_id=project_id, llm=llm,
                        project_dir=project_dir, skip_adv=True,
                    )
                    kpi_after[M_PGR_COMPOSITE] = comp.composite
                    kpi_before.setdefault(M_PGR_COMPOSITE, comp_before)
                except Exception as e:
                    print(f"[optimize] pgr scoring skipped: {e}")

        delta = _rubric_delta(kpi_before, kpi_after)
        if objective == "pgr":
            # For PGR objective, plateau is driven by composite delta only
            max_delta = abs(
                kpi_after.get(M_PGR_COMPOSITE, 0.0)
                - kpi_before.get(M_PGR_COMPOSITE, 0.0)
            )
        else:
            max_delta = _max_abs_delta(delta)

        # Track best iteration by mean rubric
        mean_after = (
            sum(kpi_after.values()) / len(kpi_after) if kpi_after else float("-inf")
        )
        if mean_after > best_mean:
            best_mean = mean_after
            best_iteration = i

        # Identify weakest for next iteration's adjustment
        weakest = weakest_agent(per_agent)
        decision: Adjustment | None = None
        if weakest is not None and i < iterations - 1:
            weakest_id, weakest_metric, _ = weakest
            with connect(db_path) as conn:
                agents = {a.id: a for a in get_project_agents(conn, project_id)}
                current = agents.get(weakest_id)
                if current:
                    decision = propose_adjustment(
                        weakest_metric=weakest_metric,
                        current_temperature=current.temperature,
                        current_max_tokens=current.max_tokens,
                        current_specialty_focus=current.specialty_focus,
                        project_goal=project.goal,
                    )
                    apply_adjustment(conn, agent_id=weakest_id, decision=decision)

        with connect(db_path) as conn:
            _persist_trace(
                conn,
                project_id=project_id,
                iteration=i,
                weakest_agent_id=weakest[0] if weakest else None,
                decision=decision,
                kpi_before=kpi_before,
                kpi_after=kpi_after,
            )

        trace.append(
            IterationResult(
                iteration=i,
                weakest_agent_id=weakest[0] if weakest else None,
                weakest_metric=weakest[1] if weakest else None,
                decision=decision,
                kpi_before=kpi_before,
                kpi_after=kpi_after,
                kpi_delta=delta,
                plateau=(max_delta < PLATEAU_THRESHOLD),
            )
        )

        # Per-iteration markdown summary (issue #3 from agent-memory-decisions.md)
        if write_iteration_summaries:
            try:
                with connect(db_path) as conn:
                    iter_turn_end_row = conn.execute(
                        "SELECT COALESCE(MAX(turn), -1) AS t FROM blackboard_entries "
                        "WHERE project_id = ?",
                        (project_id,),
                    ).fetchone()
                    iter_turn_end = (
                        int(iter_turn_end_row["t"]) if iter_turn_end_row else iter_turn_start
                    )
                    summary_path = write_iteration_summary(
                        conn,
                        project_id=project_id,
                        iteration_index=i,
                        turn_start=iter_turn_start,
                        turn_end=iter_turn_end,
                        weakest_agent_id=weakest[0] if weakest else None,
                        weakest_metric=weakest[1] if weakest else None,
                        decision_action=decision.action if decision else None,
                        decision_rationale=decision.rationale if decision else None,
                        kpi_before=kpi_before,
                        kpi_after=kpi_after,
                        project_dir=project_dir,
                    )
                    iteration_summary_paths.append(summary_path)
            except Exception as e:
                print(f"[optimize] iteration summary failed: {e}")

        if max_delta < PLATEAU_THRESHOLD:
            plateau_count += 1
            if plateau_count >= plateau_patience:
                terminated_reason = "plateau"
                break
        else:
            plateau_count = 0

    if write_iteration_summaries and iteration_summary_paths:
        try:
            write_optimization_index(
                project_id=project_id,
                iteration_paths=iteration_summary_paths,
                project_dir=project_dir,
            )
        except Exception as e:
            print(f"[optimize] index summary failed: {e}")

    return OptimizationResult(
        project_id=project_id,
        iterations_run=len(trace),
        terminated_reason=terminated_reason,
        best_iteration=best_iteration,
        trace=trace,
    )

"""Structured result artifacts.

Where `report.py` produces a prose synthesis, this module produces a bundle
of actionable outputs under `projects/{id}/artifacts/`:

    claims.md       Falsifiable claims with confidence + evidence refs + falsifier
    hypotheses.md   Hypothesis matrix (state, supporting/refuting entries)
    experiments.md  Proposed verification experiments per leading hypothesis
    decision.md     Recommended next action + predicted outcome + confidence
    risks.md        Top risks with likelihood × impact → mitigation

Each artifact uses a schema-locked prompt so the output is parseable and
consumable as inputs for real research work — not decoration.

`hypotheses.md` is mechanical (no LLM) — it reads the blackboard directly.
The other four are Writer/Experimenter/Reviewer/Critic calls.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .adapter import LLMClient
from .blackboard import (
    KIND_CRITIQUE,
    KIND_EVIDENCE,
    KIND_EXPERIMENT,
    KIND_HYPOTHESIS,
    KIND_RESULT,
    list_entries,
)
from .kpi import RUBRIC_METRICS
from .projects import get_project


# Sibling artifact list — used to build the cross-link nav bar in each header.
_ARTIFACT_ORDER = ("claims", "hypotheses", "experiments", "decision", "risks")
_ARTIFACT_TITLE = {
    "claims": "Claims",
    "hypotheses": "Hypothesis Matrix",
    "experiments": "Verification Experiments",
    "decision": "Decision",
    "risks": "Risks",
}
_ARTIFACT_BLURB = {
    "claims": "Falsifiable claims with confidence + evidence refs + falsifier",
    "hypotheses": "Hypothesis matrix (state, supporting/refuting entries)",
    "experiments": "Verification experiments per leading hypothesis",
    "decision": "Recommended next action + predicted outcome + confidence",
    "risks": "Top risks with likelihood × impact → mitigation",
}


def _wrap_artifact(name: str, body: str, ctx: dict) -> str:
    """Wrap the LLM-generated artifact body in a consistent header + footer.

    The LLM is prompted to start with `# {Title}`; we strip that and insert
    our richer header. Footer adds a citations key + cross-links to the
    other four sibling artifacts so the bundle reads as one document.
    """
    project = ctx["project"]
    pid = project.id
    body = body.lstrip()
    # Strip the LLM's title line (we replace with our standardized one).
    body = re.sub(r"^#\s+[^\n]*\n+", "", body, count=1)

    title = _ARTIFACT_TITLE.get(name, name.title())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nav = " · ".join(
        f"[{a}](./{a}.md)" if a != name else f"**{a}**"
        for a in _ARTIFACT_ORDER
    )
    goal_one_line = (project.goal or "").strip().split("\n")[0][:240]

    header = (
        f"# {title}\n\n"
        f"> *{_ARTIFACT_BLURB.get(name, '')}*\n"
        f">\n"
        f"> **Project #{pid}** — {goal_one_line}  \n"
        f"> Generated {now}  \n"
        f"> Bundle: {nav}\n\n"
        f"---\n\n"
    )

    footer = (
        "\n\n---\n\n"
        "## Citations\n\n"
        f"- `[src #N]` references blackboard entry N — source-doc evidence ingested into project {pid}.\n"
        f"- `[hyp #N]` references blackboard entry N — a hypothesis. See [hypotheses.md](./hypotheses.md).\n"
        f"- `[crit #N]` references blackboard entry N — a critique posted by an agent.\n"
        "\n"
        "Run `rp project blackboard <project_id>` to view all entries with their numeric ids and source docs.\n"
    )

    return header + body.rstrip() + footer + "\n"


@dataclass
class SynthesisResult:
    project_id: int
    out_dir: Path
    artifacts: dict[str, Path]


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------


def _gather_context(conn: sqlite3.Connection, project_id: int) -> dict:
    project = get_project(conn, project_id)
    all_entries = list_entries(conn, project_id)
    by_kind: dict[str, list] = {}
    for e in all_entries:
        by_kind.setdefault(e.kind, []).append(e)
    rubric_rows = conn.execute(
        f"""
        SELECT metric, value FROM kpi_scores
        WHERE project_id = ? AND agent_id IS NULL
          AND metric IN ({','.join('?' * len(RUBRIC_METRICS))})
          AND turn = (
            SELECT MAX(turn) FROM kpi_scores
            WHERE project_id = ? AND agent_id IS NULL AND metric = kpi_scores.metric
          )
        """,
        (project_id, *RUBRIC_METRICS, project_id),
    ).fetchall()
    rubric = {r["metric"]: float(r["value"]) for r in rubric_rows}
    return {"project": project, "by_kind": by_kind, "rubric": rubric}


def _format_entries_for_prompt(entries: list, limit: int = 12) -> str:
    if not entries:
        return "(none)"
    out = []
    for e in entries[:limit]:
        refs = (
            f" [refs: {', '.join(str(r) for r in e.refs)}]"
            if getattr(e, "refs", None)
            else ""
        )
        state = (
            f" [{e.state}]"
            if getattr(e, "state", "proposed") != "proposed"
            else ""
        )
        out.append(f"- (id={e.id}){state}{refs} {e.content[:400]}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Claims (Writer)
# ---------------------------------------------------------------------------


CLAIMS_SYSTEM = """You produce a CLAIMS.md artifact from a research simulation's
output. A claim is a falsifiable statement with a specific predicted
observation that would refute it.

Hard constraints:
- Only use material from the supplied ARTIFACTS. Never invent claims.
- Each claim must be specific, testable, and falsifiable.
- Preserve [src #N] and [hyp #N] references exactly as they appear.
- Status must be one of: unverified | supported | refuted.
- Output pure markdown with this exact structure:

# Claims

## C1: [one-sentence claim]
- Confidence: high | medium | low
- Supporting: [hyp #N], [src #N], ...
- Falsifier: "This claim would be wrong if [specific observation]."
- Status: unverified | supported | refuted

## C2: ...

Produce 3-6 claims. If supported hypotheses exist in the artifacts, lead with
those. No preamble.
"""


async def _synthesize_claims(llm: LLMClient, ctx: dict) -> str:
    body = (
        f"GOAL: {ctx['project'].goal}\n\n"
        f"EVIDENCE ({len(ctx['by_kind'].get(KIND_EVIDENCE, []))}):\n"
        f"{_format_entries_for_prompt(ctx['by_kind'].get(KIND_EVIDENCE, []))}\n\n"
        f"HYPOTHESES ({len(ctx['by_kind'].get(KIND_HYPOTHESIS, []))}):\n"
        f"{_format_entries_for_prompt(ctx['by_kind'].get(KIND_HYPOTHESIS, []))}\n\n"
        f"RESULTS ({len(ctx['by_kind'].get(KIND_RESULT, []))}):\n"
        f"{_format_entries_for_prompt(ctx['by_kind'].get(KIND_RESULT, []))}\n\n"
        f"CRITIQUES ({len(ctx['by_kind'].get(KIND_CRITIQUE, []))}):\n"
        f"{_format_entries_for_prompt(ctx['by_kind'].get(KIND_CRITIQUE, []))}"
    )
    resp = await llm.achat(
        "agent_heavy",
        messages=[
            {"role": "system", "content": CLAIMS_SYSTEM},
            {"role": "user", "content": body},
        ],
        max_tokens=2048,
        temperature=0.3,
    )
    return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Hypotheses matrix (mechanical)
# ---------------------------------------------------------------------------


def _synthesize_hypotheses(ctx: dict) -> str:
    hyps = ctx["by_kind"].get(KIND_HYPOTHESIS, [])
    if not hyps:
        return "# Hypothesis Matrix\n\n_(no hypotheses yet)_\n"

    lines = ["# Hypothesis Matrix\n"]
    lines.append("| id | state | content (truncated) | resolutions |")
    lines.append("|---|---|---|---|")
    for h in hyps:
        content = (h.content or "").replace("\n", " ").replace("|", "\\|")[:160]
        state = getattr(h, "state", "proposed")
        resolutions = getattr(h, "resolutions", []) or []
        res_str = (
            ", ".join(
                f"{r.get('verdict','?')}@{r.get('kind','?')}#{r.get('from_entry_id','?')}"
                for r in resolutions
            )
            or "—"
        )
        lines.append(f"| #{h.id} | {state} | {content} | {res_str} |")

    # Summary
    by_state: dict[str, int] = {}
    for h in hyps:
        s = getattr(h, "state", "proposed")
        by_state[s] = by_state.get(s, 0) + 1
    lines.append("")
    lines.append("## Summary")
    for state in ("supported", "refuted", "under_test", "proposed"):
        n = by_state.get(state, 0)
        if n:
            lines.append(f"- **{state}**: {n}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Experiments (Experimenter)
# ---------------------------------------------------------------------------


EXPERIMENTS_SYSTEM = """You produce EXPERIMENTS.md — a set of concrete
verification experiments for the leading unresolved hypotheses.

Hard constraints:
- Only propose experiments for hypotheses that are under_test or proposed
  (not already supported/refuted).
- Each experiment must have a minimum-viable test that could decisively
  support or refute the hypothesis.
- Preserve [hyp #N] references exactly.
- Output pure markdown with this structure:

# Proposed Verification Experiments

## E1 verifies [hyp #N]
- Protocol: ...
- Minimum viable test: ...
- Predicted outcome if hypothesis holds: ...
- Predicted outcome if hypothesis fails: ...
- Estimated cost/complexity: low | medium | high
- Rationale: why this experiment bisects the hypothesis space

Produce 1 experiment per leading hypothesis (max 4). No preamble.
"""


async def _synthesize_experiments(llm: LLMClient, ctx: dict) -> str:
    hyps = [
        h for h in ctx["by_kind"].get(KIND_HYPOTHESIS, [])
        if getattr(h, "state", "proposed") in ("proposed", "under_test")
    ][:6]
    if not hyps:
        return "# Proposed Verification Experiments\n\n_(no unresolved hypotheses)_\n"

    body = (
        f"GOAL: {ctx['project'].goal}\n\n"
        f"UNRESOLVED HYPOTHESES:\n{_format_entries_for_prompt(hyps)}\n\n"
        f"EVIDENCE:\n{_format_entries_for_prompt(ctx['by_kind'].get(KIND_EVIDENCE, []), limit=8)}\n\n"
        f"EXISTING EXPERIMENTS:\n{_format_entries_for_prompt(ctx['by_kind'].get(KIND_EXPERIMENT, []), limit=6)}"
    )
    resp = await llm.achat(
        "agent_heavy",
        messages=[
            {"role": "system", "content": EXPERIMENTS_SYSTEM},
            {"role": "user", "content": body},
        ],
        max_tokens=2048,
        temperature=0.35,
    )
    return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Decision (Reviewer)
# ---------------------------------------------------------------------------


DECISION_SYSTEM = """You produce DECISION.md — a single recommended next
action with a predicted outcome.

Hard constraints:
- Recommend exactly ONE next action.
- The action must be grounded in supported hypotheses or the strongest
  evidence in the artifacts.
- Include a confidence assessment rooted in the hypothesis states and
  evidence density.
- Output pure markdown with this structure:

# Recommended Next Action

<one paragraph: the specific action>

## Predicted Outcome

<what should happen if this action is taken, observable markers>

## Confidence

<high | medium | low — and why, rooted in the artifacts>

## Rooted in

- [hyp #N]: ...
- [src #N]: ...

No preamble.
"""


async def _synthesize_decision(llm: LLMClient, ctx: dict) -> str:
    body = (
        f"GOAL: {ctx['project'].goal}\n\n"
        f"HYPOTHESES (with states):\n{_format_entries_for_prompt(ctx['by_kind'].get(KIND_HYPOTHESIS, []))}\n\n"
        f"RESULTS:\n{_format_entries_for_prompt(ctx['by_kind'].get(KIND_RESULT, []))}\n\n"
        f"CRITIQUES:\n{_format_entries_for_prompt(ctx['by_kind'].get(KIND_CRITIQUE, []))}\n\n"
        f"PROJECT RUBRIC: {json.dumps(ctx['rubric'])}"
    )
    resp = await llm.achat(
        "judge",
        messages=[
            {"role": "system", "content": DECISION_SYSTEM},
            {"role": "user", "content": body},
        ],
        max_tokens=1536,
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Risks (Critic)
# ---------------------------------------------------------------------------


RISKS_SYSTEM = """You produce RISKS.md — the top 5 risks to the recommended
direction, each with a mitigation.

Hard constraints:
- Risks must be concrete, not generic ("this might fail" is not a risk).
- Each risk must have an estimated likelihood × impact and a specific
  mitigation.
- Output pure markdown with this structure:

# Top Risks

## R1: [risk]
- Likelihood: low | medium | high
- Impact: low | medium | high
- Mitigation: ...
- Evidence: [src #N] or [hyp #N] if applicable

## R2: ...

Produce exactly 5 risks. No preamble.
"""


async def _synthesize_risks(llm: LLMClient, ctx: dict) -> str:
    body = (
        f"GOAL: {ctx['project'].goal}\n\n"
        f"HYPOTHESES:\n{_format_entries_for_prompt(ctx['by_kind'].get(KIND_HYPOTHESIS, []))}\n\n"
        f"CRITIQUES:\n{_format_entries_for_prompt(ctx['by_kind'].get(KIND_CRITIQUE, []))}\n\n"
        f"EVIDENCE:\n{_format_entries_for_prompt(ctx['by_kind'].get(KIND_EVIDENCE, []), limit=10)}"
    )
    resp = await llm.achat(
        "agent_heavy",
        messages=[
            {"role": "system", "content": RISKS_SYSTEM},
            {"role": "user", "content": body},
        ],
        max_tokens=1536,
        temperature=0.3,
    )
    return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def synthesize_artifacts(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient | None = None,
    out_dir: Path | None = None,
    project_dir: Path = Path("./projects"),
) -> SynthesisResult:
    """Produce the five result artifacts. Each is written to
    `out_dir/{name}.md`. Failures fall back to a stub so you always have
    five files — zero-content files are signaled by an explanatory body.
    """
    llm = llm or LLMClient()
    ctx = _gather_context(conn, project_id)

    target_dir = out_dir or (project_dir / f"project_{project_id}" / "artifacts")
    target_dir.mkdir(parents=True, exist_ok=True)

    # Mechanical artifact (no LLM). Still wrapped for header/footer consistency.
    hypotheses_md = _wrap_artifact("hypotheses", _synthesize_hypotheses(ctx), ctx)
    (target_dir / "hypotheses.md").write_text(hypotheses_md, encoding="utf-8")

    artifacts = {"hypotheses": target_dir / "hypotheses.md"}

    async_artifacts = [
        ("claims", _synthesize_claims),
        ("experiments", _synthesize_experiments),
        ("decision", _synthesize_decision),
        ("risks", _synthesize_risks),
    ]
    for name, fn in async_artifacts:
        try:
            content = await fn(llm, ctx)
        except Exception as e:
            content = f"_(generation failed: {e.__class__.__name__})_"
        if not content.strip():
            content = f"_(no content produced)_"
        wrapped = _wrap_artifact(name, content, ctx)
        path = target_dir / f"{name}.md"
        path.write_text(wrapped, encoding="utf-8")
        artifacts[name] = path

    return SynthesisResult(
        project_id=project_id, out_dir=target_dir, artifacts=artifacts
    )

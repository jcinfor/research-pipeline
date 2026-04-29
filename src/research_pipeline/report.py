"""Final synthesis report.

Writer drafts from the blackboard + channel record; Reviewer grades the draft.
Both contributions land on the blackboard (`kind=draft`, `kind=review`) and
the rendered report is written to `projects/{id}/report.md`.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .adapter import LLMClient
from .blackboard import (
    KIND_CRITIQUE,
    KIND_DRAFT,
    KIND_EVIDENCE,
    KIND_EXPERIMENT,
    KIND_HYPOTHESIS,
    KIND_RESULT,
    KIND_REVIEW,
    add_entry,
    list_entries,
    render_markdown,
)
from .blackboard_digest import render_digest
from .kpi import RUBRIC_METRICS
from .projects import get_project
from .retrieval import search_blackboard


WRITER_SYSTEM = """You are the Writer archetype for a scientific research simulation.
Your job: synthesize the supplied artifacts into a coherent markdown report.

Hard constraints:
- Use ONLY material from the supplied ARTIFACTS. Never invent claims.
- Preserve citation tokens as they appear in the artifacts (e.g., "Soni et al. 2022").
- Attribute agent contributions by archetype (scout, hypogen, critic, etc.).
- Be specific. Avoid generic framing.
- Output PURE MARKDOWN. No prose preamble, no JSON.

Required sections (use these exact h2 headers):
## Executive summary
## Evidence surfaced
## Hypotheses advanced
## Critiques & open questions
## Recommended next steps
"""


REVIEWER_SYSTEM = """You are the Peer Reviewer archetype. Grade a research report.

Score 1-5 on each axis (5 = strong, 1 = weak):
  coverage, evidence_density, rigor, clarity, actionability

Also produce a 1-2 sentence overall assessment and up to 3 specific suggested revisions.

Return ONLY a JSON object, no prose:
{
  "scores": {"coverage": N, "evidence_density": N, "rigor": N, "clarity": N, "actionability": N},
  "assessment": "...",
  "revisions": ["...", "..."]
}
"""

WRITER_REVISION_SYSTEM = """You are the Writer archetype revising a draft based
on peer-review feedback.

Rules:
- Apply EACH reviewer revision concretely. If a revision asks to quantify
  something, produce specific numbers from the original artifacts. If a
  revision requests a new section, add it. If a revision flags missing
  citations, add them from the artifacts (never invent).
- Preserve the 5-section structure and all previously solid content.
- Do not remove content in response to revisions unless the reviewer
  explicitly asks for deletion.
- Output PURE MARKDOWN. No prose preamble, no JSON.
"""


def _min_review_score(review: dict, floor: int = 4) -> bool:
    scores = review.get("scores", {}) or {}
    if not scores:
        return False
    return all(int(v) >= floor for v in scores.values() if isinstance(v, (int, float)))


@dataclass
class ReportResult:
    project_id: int
    report_path: Path
    draft: str
    review: dict


def _gather_artifacts(conn: sqlite3.Connection, project_id: int) -> dict:
    project = get_project(conn, project_id)
    agents = [
        dict(r)
        for r in conn.execute(
            "SELECT id, archetype FROM agents WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
    ]
    kinds: dict[str, list] = {}
    for e in list_entries(conn, project_id):
        kinds.setdefault(e.kind, []).append(e)

    kpi: dict[str, float] = {}
    for r in conn.execute(
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
    ):
        kpi[r["metric"]] = float(r["value"])

    return {"project": project, "agents": agents, "kinds": kinds, "kpi": kpi}


def _format_artifacts(ctx: dict) -> str:
    lines: list[str] = []
    lines.append(f"GOAL: {ctx['project'].goal}")
    lines.append("")
    lines.append(
        "AGENTS PARTICIPATING: "
        + ", ".join(f"agent_{a['id']}={a['archetype']}" for a in ctx["agents"])
    )
    lines.append("")
    for kind in (
        KIND_EVIDENCE,
        KIND_HYPOTHESIS,
        KIND_CRITIQUE,
        KIND_EXPERIMENT,
        KIND_RESULT,
    ):
        items = ctx["kinds"].get(kind, [])
        if not items:
            continue
        lines.append(f"## {kind.upper()} ({len(items)})")
        for e in items:
            refs = f" [refs: {', '.join(str(r) for r in e.refs)}]" if e.refs else ""
            lines.append(
                f"- (turn {e.turn}, agent_{e.agent_id}){refs} {e.content}"
            )
        lines.append("")
    lines.append(f"KPI RUBRIC: {json.dumps(ctx['kpi'])}")
    return "\n".join(lines)


async def generate_report(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient | None = None,
    work_dir: Path | None = None,
    retrieval_top_k: int = 8,
    max_revisions: int = 1,
) -> ReportResult:
    llm = llm or LLMClient()
    ctx = _gather_artifacts(conn, project_id)

    # Prefer embedding-ranked artifacts when available; the Writer gets the
    # most goal-relevant entries per kind instead of a raw dump.
    ranked = _try_rank_artifacts(conn, project_id, ctx, llm, retrieval_top_k)
    artifacts_text = (
        _format_artifacts_ranked(ctx, ranked) if ranked else _format_artifacts(ctx)
    )
    # Roadmap 2.5 — prepend a structural digest so writer/reviewer see the
    # SHAPE of the project (state matrix, top hypotheses, open disagreements,
    # confidence mix) before the raw retrieved artifacts. Cheap structural
    # compression — no extra LLM calls.
    digest = render_digest(conn, project_id=project_id)
    artifacts_text = digest + "\n" + artifacts_text

    draft_resp = await llm.achat(
        "agent_heavy",
        messages=[
            {"role": "system", "content": WRITER_SYSTEM},
            {"role": "user", "content": artifacts_text},
        ],
        max_tokens=3072,
        temperature=0.3,
    )
    draft = (draft_resp.choices[0].message.content or "").strip()
    if not draft:
        draft = "_(Writer produced no content.)_"

    review_resp = await llm.achat(
        "judge",
        messages=[
            {"role": "system", "content": REVIEWER_SYSTEM},
            {
                "role": "user",
                # Roadmap 2.5 — reviewer sees the same shape digest as the
                # writer, so its scoring can anchor on whether the draft
                # acknowledges open disagreements + the confidence mix.
                "content": (
                    f"GOAL: {ctx['project'].goal}\n\n{digest}\n\nDRAFT:\n{draft}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=1024,
        temperature=0.1,
    )
    try:
        review = json.loads(review_resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        review = {
            "assessment": "reviewer returned invalid JSON",
            "scores": {},
            "revisions": [],
        }

    # Revision loop: Writer re-drafts applying reviewer's specific suggestions
    # until all rubric scores >= 4 or we hit the budget.
    revisions_made = 0
    while (
        revisions_made < max_revisions
        and not _min_review_score(review, floor=4)
        and (review.get("revisions") or [])
    ):
        revisions = review["revisions"]
        revision_prompt = (
            f"GOAL: {ctx['project'].goal}\n\n"
            f"PRIOR DRAFT (revise this, do not start from scratch):\n{draft}\n\n"
            f"REVIEWER SUGGESTED REVISIONS (apply each):\n"
            + "\n".join(f"- {r}" for r in revisions)
            + "\n\nSOURCE ARTIFACTS (re-ground any new claims here):\n"
            + artifacts_text
        )
        try:
            revised_resp = await llm.achat(
                "agent_heavy",
                messages=[
                    {"role": "system", "content": WRITER_REVISION_SYSTEM},
                    {"role": "user", "content": revision_prompt},
                ],
                max_tokens=3072,
                temperature=0.25,
            )
            revised = (revised_resp.choices[0].message.content or "").strip()
            if not revised:
                break
            draft = revised
            revisions_made += 1
            # Re-review the new draft
            review_resp = await llm.achat(
                "judge",
                messages=[
                    {"role": "system", "content": REVIEWER_SYSTEM},
                    {
                        "role": "user",
                        "content": f"GOAL: {ctx['project'].goal}\n\nDRAFT:\n{draft}",
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=1024,
                temperature=0.1,
            )
            try:
                review = json.loads(review_resp.choices[0].message.content or "{}")
            except json.JSONDecodeError:
                break
        except Exception as e:
            print(f"[report] revision pass skipped: {e}")
            break

    max_turn = conn.execute(
        "SELECT COALESCE(MAX(turn), 0) FROM channel_posts WHERE project_id = ?",
        (project_id,),
    ).fetchone()[0]
    # Final draft + review are syntheses over upstream blackboard entries —
    # not direct extractions from a source. Roadmap 2.4 → INFERRED.
    from .blackboard import CONF_INFERRED
    add_entry(
        conn,
        project_id=project_id,
        kind=KIND_DRAFT,
        content=draft,
        turn=max_turn + 1,
        confidence=CONF_INFERRED,
    )
    add_entry(
        conn,
        project_id=project_id,
        kind=KIND_REVIEW,
        content=json.dumps(review),
        turn=max_turn + 1,
        confidence=CONF_INFERRED,
    )

    final_md = _compose_final(ctx, draft, review)

    work_dir = work_dir or Path("projects")
    out_dir = work_dir / f"project_{project_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"
    report_path.write_text(final_md, encoding="utf-8")
    (out_dir / "blackboard.md").write_text(
        render_markdown(conn, project_id), encoding="utf-8"
    )

    return ReportResult(
        project_id=project_id,
        report_path=report_path,
        draft=draft,
        review=review,
    )


def _try_rank_artifacts(
    conn, project_id: int, ctx: dict, llm: LLMClient, top_k: int
) -> dict | None:
    """Attempt embedding-ranked retrieval per kind. Returns None on failure or
    when no entries carry embeddings yet."""
    try:
        ranked: dict[str, list] = {}
        for kind in (
            KIND_EVIDENCE,
            KIND_HYPOTHESIS,
            KIND_CRITIQUE,
            KIND_EXPERIMENT,
            KIND_RESULT,
        ):
            scored = search_blackboard(
                conn,
                project_id=project_id,
                query=ctx["project"].goal,
                llm=llm,
                top_k=top_k,
                kind=kind,
            )
            if scored:
                ranked[kind] = scored
        return ranked or None
    except Exception as e:
        print(f"[report] retrieval failed, falling back to full dump: {e}")
        return None


def _format_artifacts_ranked(ctx: dict, ranked: dict) -> str:
    lines: list[str] = []
    lines.append(f"GOAL: {ctx['project'].goal}")
    lines.append("")
    lines.append(
        "AGENTS PARTICIPATING: "
        + ", ".join(f"agent_{a['id']}={a['archetype']}" for a in ctx["agents"])
    )
    lines.append("")
    lines.append("(Artifacts ranked by cosine similarity to the goal; "
                 "scores shown are 0-1.)")
    lines.append("")
    for kind in (
        KIND_EVIDENCE,
        KIND_HYPOTHESIS,
        KIND_CRITIQUE,
        KIND_EXPERIMENT,
        KIND_RESULT,
    ):
        scored = ranked.get(kind, [])
        if not scored:
            continue
        lines.append(f"## {kind.upper()} (top {len(scored)})")
        for s in scored:
            e = s.entry
            refs = f" [refs: {', '.join(str(r) for r in e.refs)}]" if e.refs else ""
            state_tag = ""
            if kind == KIND_HYPOTHESIS and getattr(e, "state", None) and e.state != "proposed":
                state_tag = f" [STATE: {e.state.upper()}]"
            lines.append(
                f"- (sim={s.score:.3f}, turn {e.turn}, agent_{e.agent_id}){state_tag}{refs} "
                f"{e.content}"
            )
        lines.append("")
    lines.append(f"KPI RUBRIC: {json.dumps(ctx['kpi'])}")
    lines.append("")
    lines.append(
        "HYPOTHESIS LIFECYCLE GUIDANCE: when you write the 'Hypotheses "
        "advanced' section, group by state if any are resolved. Call out "
        "which hypotheses were SUPPORTED, REFUTED, or remain UNDER_TEST based "
        "on the [STATE: ...] tags above."
    )
    return "\n".join(lines)


def _compose_final(ctx: dict, draft: str, review: dict) -> str:
    scores = review.get("scores", {}) or {}
    scores_line = (
        ", ".join(f"{k}={v}" for k, v in scores.items())
        if scores
        else "(no reviewer scores)"
    )
    assessment = review.get("assessment", "") or ""
    revisions = review.get("revisions", []) or []
    parts = [
        f"# Project {ctx['project'].id} — Research Synthesis\n",
        f"**Goal:** {ctx['project'].goal}\n",
        f"**Agents:** "
        + ", ".join(f"`{a['archetype']}`" for a in ctx["agents"])
        + "\n",
        f"**KPI (rubric, 1-5):** " + ", ".join(f"{k}={v}" for k, v in ctx["kpi"].items()) + "\n",
        "\n---\n",
        draft,
        "\n---\n\n## Reviewer Assessment\n",
        f"**Scores:** {scores_line}\n\n",
        f"{assessment}\n",
    ]
    if revisions:
        parts.append("\n**Suggested revisions:**\n")
        for r in revisions:
            parts.append(f"- {r}\n")
    return "\n".join(parts)

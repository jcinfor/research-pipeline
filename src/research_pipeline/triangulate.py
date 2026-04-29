"""Triangulation proxy: reproducibility over N independent claim-synthesis samples.

Issues N Writer samples of the claim-synthesis step at elevated temperature,
embeds each resulting claim title, and measures how well claims from different
samples match each other. A high score means the pipeline produces stable
claims across stochastic sampling (skill, not luck). A low score means claims
are accidents of sampling.

Kept out of the PGR composite because it's expensive (N Writer calls) and
because "reproducibility" is a different axis from "correctness" — the user
should interpret it separately.

Terminology: each Writer call within a triangulation pass is a *sample*.
The public field name `n_runs` is retained for API compat with phase-3
tests but "sample" is the correct user-facing word (see docs/terminology.md).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .adapter import LLMClient
from .dedup import cosine


_CLAIM_HEADER_RE = re.compile(r"^##\s*C\d+:\s*(.*?)$", re.MULTILINE)


@dataclass
class TriangulationResult:
    n_runs: int
    mean_pairwise_similarity: float
    per_run_claim_counts: list[int] = field(default_factory=list)
    run_samples: list[list[str]] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.mean_pairwise_similarity


def _extract_claim_titles(md: str) -> list[str]:
    """Pull the `## CN: <title>` headers out of a claims.md-shaped string."""
    return [m.group(1).strip() for m in _CLAIM_HEADER_RE.finditer(md)]


async def triangulate_project(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient,
    n_runs: int = 3,
    temperature: float = 0.55,
) -> TriangulationResult:
    """Issue N Writer samples of the claims-synthesis step and measure
    claim reproducibility across samples via mean pairwise best-match cosine.

    Returns mean_pairwise_similarity in [0, 1]:
        1.0 = every sample produced essentially the same claims
        0.0 = samples produced disjoint claim sets
    """
    from .synthesize import CLAIMS_SYSTEM, _gather_context
    # We re-issue the Writer call at elevated temperature to sample the
    # claim distribution, but we don't write to disk — we just parse the
    # response in-memory.

    ctx = _gather_context(conn, project_id)
    # Build the same user payload the real synthesize_artifacts uses
    from .blackboard import (
        KIND_CRITIQUE,
        KIND_EVIDENCE,
        KIND_HYPOTHESIS,
        KIND_RESULT,
    )
    from .synthesize import _format_entries_for_prompt

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

    per_run_titles: list[list[str]] = []
    for _ in range(n_runs):
        try:
            resp = await llm.achat(
                "agent_heavy",
                messages=[
                    {"role": "system", "content": CLAIMS_SYSTEM},
                    {"role": "user", "content": body},
                ],
                max_tokens=2048,
                temperature=temperature,
            )
            md = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[triangulate] sample failed: {e}")
            per_run_titles.append([])
            continue
        titles = _extract_claim_titles(md)
        per_run_titles.append(titles)

    flat: list[str] = [t for run in per_run_titles for t in run]
    if len(flat) < 2:
        return TriangulationResult(
            n_runs=n_runs,
            mean_pairwise_similarity=0.0,
            per_run_claim_counts=[len(r) for r in per_run_titles],
            run_samples=per_run_titles,
        )

    try:
        embeddings = llm.embed("embedding", flat)
    except Exception as e:
        print(f"[triangulate] embedding failed: {e}")
        return TriangulationResult(
            n_runs=n_runs,
            mean_pairwise_similarity=0.0,
            per_run_claim_counts=[len(r) for r in per_run_titles],
            run_samples=per_run_titles,
        )

    # Regroup embeddings by run boundaries
    embs_by_run: list[list[list[float]]] = []
    idx = 0
    for titles in per_run_titles:
        embs_by_run.append(embeddings[idx : idx + len(titles)])
        idx += len(titles)

    pair_scores: list[float] = []
    for i in range(n_runs):
        for j in range(i + 1, n_runs):
            ei = embs_by_run[i]
            ej = embs_by_run[j]
            if not ei or not ej:
                continue
            best_matches = [max(cosine(x, y) for y in ej) for x in ei]
            if best_matches:
                pair_scores.append(sum(best_matches) / len(best_matches))

    score = sum(pair_scores) / len(pair_scores) if pair_scores else 0.0
    return TriangulationResult(
        n_runs=n_runs,
        mean_pairwise_similarity=float(score),
        per_run_claim_counts=[len(r) for r in per_run_titles],
        run_samples=per_run_titles,
    )

"""Orchestrator for E6 — Cross-Entity Temporal Correlation.

Usage:
    uv run python -m benchmarks.e6_cross_entity.run

Ingests 30 docs across 3 parallel streams (Alice temp, Prod-01 status,
Nova lead), then runs 5 queries: 3 cross-entity temporal joins and 2
single-entity controls.

Expected architectural pattern:
    - mem0_lite:        0-1/3 on cross-entity (overwriting destroys history)
    - zep_lite:         2-3/3 (accumulated triples preserve history)
    - supermemory_lite: 0-2/3 (profile fails like mem0; chunk fallback may help)
    - m_flow_lite:      2-3/3 (cone preserves FacetPoints + graph reasoning)
    - hybrid_flat:      0-1/3 (cosine retrieval doesn't align timestamps)

Controls: all systems should pass both controls. If a system fails the
control, something is wrong at the mechanical level.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from research_pipeline.adapter import LLMClient

from benchmarks.e1_blackboard_stress.systems import (
    EpistemicPrototype, GapAwarePrototype,
    HybridFlat, MFlowLite, MFlowRich, Mem0Lite, MultiTierMemory,
    PrototypeMemory, SupermemoryLite, ZepLite, ZepRich,
)

from .corpus import CORPUS
from .queries import QUERIES, Query, score


@dataclass
class QueryResult:
    qid: str
    axis: str
    expected: str
    answer: str
    correct: bool
    duration_ms: int


@dataclass
class SystemResult:
    name: str
    ingest_ms: int = 0
    results: list[QueryResult] = field(default_factory=list)

    @property
    def correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    @property
    def total(self) -> int:
        return len(self.results)

    def score_by_axis(self, axis: str) -> tuple[int, int]:
        matching = [r for r in self.results if r.axis == axis]
        return sum(1 for r in matching if r.correct), len(matching)


def _run(name: str, system) -> SystemResult:
    t0 = time.time()
    for doc in CORPUS:
        try:
            system.ingest(doc)
        except Exception as e:
            print(f"  [{name}] ingest error on {doc.id}: {str(e)[:120]}")
    ingest_ms = int((time.time() - t0) * 1000)
    print(f"[{name}] ingest done in {ingest_ms}ms")

    sr = SystemResult(name=name, ingest_ms=ingest_ms)
    for q in QUERIES:
        t1 = time.time()
        try:
            answer = system.query(q.question)
        except Exception as e:
            answer = f"(error: {str(e)[:120]})"
        dur = int((time.time() - t1) * 1000)
        correct = score(answer, q)
        sr.results.append(QueryResult(
            qid=q.id, axis=q.axis, expected=q.correct_key,
            answer=answer, correct=correct, duration_ms=dur,
        ))
        mark = "✓" if correct else "✗"
        print(f"  [{name}] {q.id} ({q.axis}) {mark} ({dur}ms) exp={q.correct_key!r}: {answer[:120]}")
    return sr


def _render(results: dict[str, SystemResult]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    cross_axes = [
        "cross_entity_peak", "cross_entity_transition", "cross_entity_threshold",
    ]
    control_axes = ["control_current", "control_initial"]

    lines: list[str] = [
        f"# E6 — Cross-Entity Temporal Correlation — results\n",
        f"*Run: {now}*\n",
        "Three parallel 10-step streams (Alice temp, Prod-01 status, Nova lead) "
        "with overlapping timestamps. 3 cross-entity queries + 2 controls.\n",
    ]
    lines.append("## Summary\n")
    lines.append(
        "| system | cross-entity | controls | overall | ingest ms |"
    )
    lines.append("|---|---|---|---|---|")
    for name, sr in results.items():
        cross_ok = sum(sr.score_by_axis(a)[0] for a in cross_axes)
        cross_n = sum(sr.score_by_axis(a)[1] for a in cross_axes)
        ctrl_ok = sum(sr.score_by_axis(a)[0] for a in control_axes)
        ctrl_n = sum(sr.score_by_axis(a)[1] for a in control_axes)
        lines.append(
            f"| **{name}** | {cross_ok}/{cross_n} | {ctrl_ok}/{ctrl_n} | "
            f"**{sr.correct}/{sr.total}** | {sr.ingest_ms} |"
        )
    lines.append("")
    for name, sr in results.items():
        lines.append(f"## {name}\n")
        lines.append("| qid | axis | expected | correct | answer |")
        lines.append("|---|---|---|---|---|")
        for r in sr.results:
            mark = "✓" if r.correct else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:180]
            lines.append(f"| {r.qid} | {r.axis} | {r.expected} | {mark} | {ans} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"E6 — {len(CORPUS)} interleaved docs across 3 entities (10 timesteps each)")
    print(f"     {len(QUERIES)} queries: 3 cross-entity + 2 controls")
    print()

    client = LLMClient()
    systems = {
        "hybrid_flat": HybridFlat(client),
        "zep_lite": ZepLite(client),
        "zep_rich": ZepRich(client),
        "mem0_lite": Mem0Lite(client),
        "supermemory_lite": SupermemoryLite(client),
        "m_flow_lite": MFlowLite(client),
        "m_flow_rich": MFlowRich(client),
        "prototype": PrototypeMemory(client),
        "multitier": MultiTierMemory(client, episode_size=200),
        "epistemic_prototype": EpistemicPrototype(client),
        "gapaware_prototype": GapAwarePrototype(client),
    }

    results: dict[str, SystemResult] = {}
    for name, system in systems.items():
        print(f"[{name}] ingesting {len(CORPUS)} docs...")
        results[name] = _run(name, system)
        print()

    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    cross_axes = {
        "cross_entity_peak", "cross_entity_transition", "cross_entity_threshold",
    }
    for name, sr in results.items():
        cross_ok = sum(1 for r in sr.results if r.axis in cross_axes and r.correct)
        cross_n = sum(1 for r in sr.results if r.axis in cross_axes)
        ctrl_ok = sum(
            1 for r in sr.results if r.axis not in cross_axes and r.correct
        )
        ctrl_n = sum(1 for r in sr.results if r.axis not in cross_axes)
        print(
            f"  {name:18s} cross-entity: {cross_ok}/{cross_n}  "
            f"controls: {ctrl_ok}/{ctrl_n}  overall: {sr.correct}/{sr.total}  "
            f"ingest: {sr.ingest_ms}ms"
        )

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(results), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

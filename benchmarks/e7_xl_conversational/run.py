"""Orchestrator for E7-XL — 124-turn / 16-week conversational memory test.

Usage:
    uv run python -m benchmarks.e7_xl_conversational.run

Tests whether E7-long's convergence pattern (4 extraction systems at 9/10)
holds at ~1.7× the scale. Also includes ZepRich and MFlowRich from E6 to
see whether rich query surfaces change the verdict at conversational scale.
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
    HybridFlat, IntentRoutedZep, MFlowLite, MFlowRich, Mem0Lite, MultiTierMemory,
    PrototypeMemory, SupermemoryLite, ZepLite, ZepRich,
)

from .corpus import all_turns_sorted
from .queries import QUERIES, score


@dataclass
class QueryResult:
    qid: str
    axis: str
    turns_distance: int
    expected: str
    answer: str
    correct: bool
    duration_ms: int


@dataclass
class SystemResult:
    name: str
    ingest_ms: int = 0
    results: list[QueryResult] = field(default_factory=list)
    error: str | None = None

    @property
    def correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    @property
    def total(self) -> int:
        return len(self.results)


def _run(name: str, system, turns) -> SystemResult:
    t0 = time.time()
    errs = 0
    for turn in turns:
        try:
            system.ingest(turn)
        except Exception as e:
            errs += 1
            if errs <= 3:
                print(f"  [{name}] ingest error on {turn.id}: {str(e)[:120]}")
    ingest_ms = int((time.time() - t0) * 1000)
    print(f"[{name}] ingest done in {ingest_ms}ms ({errs} errors)")

    sr = SystemResult(name=name, ingest_ms=ingest_ms,
                     error=f"{errs} ingest errors" if errs else None)
    for q in QUERIES:
        t1 = time.time()
        try:
            answer = system.query(q.question)
        except Exception as e:
            answer = f"(error: {str(e)[:160]})"
        dur = int((time.time() - t1) * 1000)
        correct = score(answer, q)
        sr.results.append(QueryResult(
            qid=q.id, axis=q.axis, turns_distance=q.turns_distance,
            expected=q.correct_key, answer=answer,
            correct=correct, duration_ms=dur,
        ))
        mark = "✓" if correct else "✗"
        print(f"  [{name}] {q.id} ({q.axis}, d={q.turns_distance}) {mark} ({dur}ms) exp={q.correct_key!r}: {answer[:100]}")
    return sr


def _render(results: dict[str, SystemResult], n_turns: int) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        f"# E7-XL — 124-turn / 16-week conversational memory — results\n",
        f"*Run: {now}*\n",
        f"Corpus: {n_turns} turns across 19 sessions (16 weeks). "
        f"{len(QUERIES)} queries; most span 100+ turns from antecedent.\n",
    ]
    lines.append("## Summary\n")
    lines.append("| system | overall | ingest ms | notes |")
    lines.append("|---|---|---|---|")
    for name, sr in results.items():
        lines.append(
            f"| **{name}** | {sr.correct}/{sr.total} | {sr.ingest_ms} | {sr.error or ''} |"
        )
    lines.append("")
    for name, sr in results.items():
        lines.append(f"## {name}\n")
        lines.append("| qid | axis | dist | expected | correct | answer |")
        lines.append("|---|---|---|---|---|---|")
        for r in sr.results:
            mark = "✓" if r.correct else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:180]
            lines.append(
                f"| {r.qid} | {r.axis} | {r.turns_distance} | {r.expected} | {mark} | {ans} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    turns = all_turns_sorted()
    print(f"E7-XL — {len(turns)} turns across 16 weeks")
    print(f"        {len(QUERIES)} queries, most at 75+ turns distance")
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
        "intent_routed_zep": IntentRoutedZep(client),
        "prototype": PrototypeMemory(client),
        "multitier": MultiTierMemory(client, episode_size=200),
        "epistemic_prototype": EpistemicPrototype(client),
        "gapaware_prototype": GapAwarePrototype(client),
    }

    results: dict[str, SystemResult] = {}
    for name, system in systems.items():
        print(f"[{name}] ingesting {len(turns)} turns...")
        results[name] = _run(name, system, turns)
        print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for name, sr in results.items():
        print(f"  {name:18s} {sr.correct}/{sr.total}  ingest {sr.ingest_ms}ms  {sr.error or ''}")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(results, len(turns)), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

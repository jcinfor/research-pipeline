"""Orchestrator for E8 — Differential State Reconstruction.

Usage:
    uv run python -m benchmarks.e8_differential_state.run

Tests the project 8 hypothesis: is the primary bottleneck lossy substrate
(overwrite destroys history) or lossy query surface (preserved storage but
collapsed query)?

Systems:
    mem0_lite         — lossy substrate. Predicted: passes only q1 current.
    zep_lite          — preserving substrate, collapsing query. Predicted:
                        passes q1 but fails historical queries (history
                        present in storage but filtered out at query).
    zep_rich          — preserving substrate, full-exposure query. Predicted:
                        passes historical queries but may overload LLM on
                        q1 current (like E7-XL q9 showed).
    intent_routed_zep — preserving substrate + intent-based router. Predicted:
                        passes everything by dispatching to the right mode.
    hybrid_flat       — raw chunks, cosine retrieval. Baseline.

If intent_routed_zep wins clearly: routing ON TOP of append-only substrate
is a real architectural contribution. If zep_rich already matches it,
routing is a no-op on this workload.
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
    EpistemicPrototype, GapAwarePrototype, HybridFlat, IntentRoutedZep,
    Mem0Lite, MultiTierMemory, PrototypeMemory, ZepLite, ZepRich,
)

from .corpus import CORPUS
from .queries import QUERIES, score


@dataclass
class QueryResult:
    qid: str
    intent: str
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

    def score_by_intent(self, intent: str) -> tuple[int, int]:
        matching = [r for r in self.results if r.intent == intent]
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
            answer = f"(error: {str(e)[:160]})"
        dur = int((time.time() - t1) * 1000)
        correct = score(answer, q)
        sr.results.append(QueryResult(
            qid=q.id, intent=q.intent, expected=q.correct_key,
            answer=answer, correct=correct, duration_ms=dur,
        ))
        mark = "✓" if correct else "✗"
        print(f"  [{name}] {q.id} ({q.intent}) {mark} ({dur}ms) exp={q.correct_key!r}: {answer[:120]}")
    return sr


def _render(results: dict[str, SystemResult]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    intents = sorted({q.intent for q in QUERIES})
    lines = [
        f"# E8 — Differential State Reconstruction — results\n",
        f"*Run: {now}*\n",
        "Single entity, 60 non-monotonic state changes across 3 values. "
        "6 queries across 3 intent types (current, current_with_context, historical).\n",
    ]
    lines.append("## Summary by intent\n")
    header = "| system | " + " | ".join(intents) + " | overall | ingest ms |"
    sep = "|" + "---|" * (len(intents) + 3)
    lines.append(header)
    lines.append(sep)
    for name, sr in results.items():
        cells = [f"{sr.score_by_intent(i)[0]}/{sr.score_by_intent(i)[1]}" for i in intents]
        lines.append(
            f"| **{name}** | " + " | ".join(cells) +
            f" | **{sr.correct}/{sr.total}** | {sr.ingest_ms} |"
        )
    lines.append("")
    for name, sr in results.items():
        lines.append(f"## {name}\n")
        lines.append("| qid | intent | expected | correct | answer |")
        lines.append("|---|---|---|---|---|")
        for r in sr.results:
            mark = "✓" if r.correct else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:180]
            lines.append(f"| {r.qid} | {r.intent} | {r.expected} | {mark} | {ans} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"E8 — Differential State Reconstruction")
    print(f"     {len(CORPUS)} observations (non-monotonic oscillation)")
    print(f"     {len(QUERIES)} queries across "
          f"{len({q.intent for q in QUERIES})} intent types")
    print()

    client = LLMClient()
    systems: dict = {
        "mem0_lite": Mem0Lite(client),
        "zep_lite": ZepLite(client),
        "zep_rich": ZepRich(client),
        "intent_routed_zep": IntentRoutedZep(client),
        "hybrid_flat": HybridFlat(client),
        "prototype": PrototypeMemory(client),
        "multitier": MultiTierMemory(client, episode_size=200),
        "epistemic_prototype": EpistemicPrototype(client),
        "gapaware_prototype": GapAwarePrototype(client),
    }
    # Optionally include real mem0 if requested (closes Gap 1: lite vs real).
    import os
    if os.environ.get("RP_BENCH_INCLUDE_MEM0_REAL"):
        from benchmarks._real_products.mem0_real import Mem0Real
        systems["mem0_real"] = Mem0Real(collection="e8_bench")
    if os.environ.get("RP_BENCH_INCLUDE_MEM0_REAL_V3"):
        # Same Mem0Real adapter — active mem0 package version determines the
        # algorithm. Assert the v3 marker so a v2 install can't silently
        # produce v2 numbers labeled as `mem0_real_v3`.
        try:
            from mem0.configs.prompts import ADDITIVE_EXTRACTION_PROMPT  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "RP_BENCH_INCLUDE_MEM0_REAL_V3 set but installed mem0 lacks v3 markers "
                "(ADDITIVE_EXTRACTION_PROMPT not found). See BENCHMARKS.md → Reproducing v3 vs v2."
            )
        from benchmarks._real_products.mem0_real import Mem0Real
        systems["mem0_real_v3"] = Mem0Real(collection="e8_bench_v3")

    results: dict[str, SystemResult] = {}
    for name, system in systems.items():
        print(f"[{name}] ingesting {len(CORPUS)} docs...")
        results[name] = _run(name, system)
        print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    intents = sorted({q.intent for q in QUERIES})
    for name, sr in results.items():
        parts = [f"{i}={sr.score_by_intent(i)[0]}/{sr.score_by_intent(i)[1]}" for i in intents]
        print(f"  {name:20s} " + "  ".join(parts) + f"  | overall {sr.correct}/{sr.total}  ingest {sr.ingest_ms}ms")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(results), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

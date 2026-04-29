"""Orchestrator for E9 — Cross-Thread Intent Routing Stress.

Usage:
    uv run python -m benchmarks.e9_cross_thread_routing.run

Proposed after E8 couldn't discriminate intent_routed_zep from zep_rich.
E9 makes current-value retrieval HARDER by burying the latest value among
interleaved cross-thread history, reproducing the E7-XL q9 failure pattern
at a controlled scale.

Systems: mem0, zep_lite, zep_rich, intent_routed_zep, hybrid_flat.
Prediction: if intent routing adds value anywhere, it'll be here on the
"current" queries where zep_rich has 90 chronological triples to sift
through, and the latest-for-Alpha-status is scattered among latest-for-
Beta-lead etc.
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
    HybridFlat, IntentRoutedZep, Mem0Lite, MultiTierMemory,
    PrototypeMemory, ZepLite, ZepRich,
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
        f"# E9 — Cross-Thread Intent Routing Stress — results\n",
        f"*Run: {now}*\n",
        "3 entities × 3 attributes × 10 observations = 90 interleaved triples. "
        "Latest values BURIED across cross-thread history. "
        f"{len(QUERIES)} queries across {len(intents)} intent types.\n",
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
    print(f"E9 — Cross-Thread Intent Routing Stress")
    print(f"     {len(CORPUS)} interleaved observations (3 entities × 3 attributes × 10 obs)")
    print(f"     {len(QUERIES)} queries across "
          f"{len({q.intent for q in QUERIES})} intent types")
    print()

    client = LLMClient()
    systems = {
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

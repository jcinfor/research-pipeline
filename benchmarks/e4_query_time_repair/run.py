"""Orchestrator for the E4 Query-Time Repair benchmark.

Usage:
    uv run python -m benchmarks.e4_query_time_repair.run

Ingests the synthetic corpus into three memory systems (Karpathy-lite,
Zep-lite, Hybrid), runs the query set against each, scores with a
substring-based correctness check, and writes a markdown report to
    benchmarks/e4_query_time_repair/results/run_YYYYMMDD_HHMMSS.md
"""
from __future__ import annotations

import json
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

from .corpus import CORPUS
from .queries import QUERIES, Query, score_answer
from .systems import Hybrid, KarpathyLite, ZepLite


@dataclass
class QueryResult:
    query_id: str
    question: str
    as_of: str | None
    kind: str
    expected: str
    wrong: tuple[str, ...]
    answer: str
    correct: bool
    duration_ms: int


@dataclass
class SystemResult:
    name: str
    ingest_ms: int = 0
    query_results: list[QueryResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def correct(self) -> int:
        return sum(1 for r in self.query_results if r.correct)

    @property
    def total(self) -> int:
        return len(self.query_results)

    def score_by_kind(self, kind: str) -> tuple[int, int]:
        matching = [r for r in self.query_results if r.kind == kind]
        return (sum(1 for r in matching if r.correct), len(matching))


def _run_ingest(system_name: str, system, docs) -> int:
    start = time.time()
    for doc in docs:
        try:
            system.ingest(doc)
        except Exception as e:
            print(f"  [{system_name}] ingest error on {doc.id}: {e}")
    return int((time.time() - start) * 1000)


def _run_queries(system_name: str, system, queries) -> list[QueryResult]:
    out: list[QueryResult] = []
    for q in queries:
        t0 = time.time()
        try:
            answer = system.query(q.question, as_of=q.as_of)
        except Exception as e:
            answer = f"(error: {e})"
        duration_ms = int((time.time() - t0) * 1000)
        correct = score_answer(answer, q)
        out.append(QueryResult(
            query_id=q.id,
            question=q.question,
            as_of=q.as_of,
            kind=q.kind,
            expected=q.correct_key,
            wrong=q.wrong_keys,
            answer=answer,
            correct=correct,
            duration_ms=duration_ms,
        ))
        mark = "✓" if correct else "✗"
        print(f"  [{system_name}] {q.id} {mark} ({duration_ms}ms): {answer[:120]}")
    return out


def _render_report(
    results: dict[str, SystemResult], corpus_size: int, query_size: int,
) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append(f"# E4 Query-Time Repair benchmark — results\n")
    lines.append(f"*Run: {now}*\n")
    lines.append(
        f"Corpus: {corpus_size} documents · Queries: {query_size} "
        f"({sum(1 for q in QUERIES if q.kind=='current')} current, "
        f"{sum(1 for q in QUERIES if q.kind=='temporal')} temporal)\n"
    )

    # Summary table
    lines.append("## Summary\n")
    lines.append("| system | current | temporal | overall | ingest ms | avg query ms |")
    lines.append("|---|---|---|---|---|---|")
    for name, sr in results.items():
        c_ok, c_n = sr.score_by_kind("current")
        t_ok, t_n = sr.score_by_kind("temporal")
        avg_q = (
            sum(r.duration_ms for r in sr.query_results) / sr.total
            if sr.total else 0
        )
        lines.append(
            f"| **{name}** | {c_ok}/{c_n} | {t_ok}/{t_n} | "
            f"**{sr.correct}/{sr.total}** | {sr.ingest_ms} | {avg_q:.0f} |"
        )
    lines.append("")

    # Per-system detail
    for name, sr in results.items():
        lines.append(f"## {name}\n")
        if sr.errors:
            lines.append(f"**Errors:** {len(sr.errors)}\n")
            for e in sr.errors[:3]:
                lines.append(f"  - {e[:200]}")
            lines.append("")
        lines.append("| query | as_of | kind | expected | correct | answer |")
        lines.append("|---|---|---|---|---|---|")
        for r in sr.query_results:
            expected = r.expected
            mark = "✓" if r.correct else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:160]
            as_of = r.as_of or "—"
            lines.append(
                f"| {r.query_id} | {as_of} | {r.kind} | {expected} | {mark} | {ans} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    print(f"E4 benchmark — corpus={len(CORPUS)} docs, queries={len(QUERIES)}")
    print()

    from benchmarks.e1_blackboard_stress.systems import (
        EpistemicPrototype, GapAwarePrototype, MultiTierMemory, PrototypeMemory,
    )

    client = LLMClient()
    systems = {
        "karpathy_lite": KarpathyLite(client),
        "zep_lite": ZepLite(client),
        "hybrid": Hybrid(client),
        "prototype": PrototypeMemory(client),
        "multitier": MultiTierMemory(client, episode_size=200),
        "epistemic_prototype": EpistemicPrototype(client),
        "gapaware_prototype": GapAwarePrototype(client),
    }

    results: dict[str, SystemResult] = {}
    for name, system in systems.items():
        print(f"[{name}] ingesting {len(CORPUS)} docs...")
        ingest_ms = _run_ingest(name, system, CORPUS)
        print(f"[{name}] ingest done in {ingest_ms}ms")
        print(f"[{name}] running queries...")
        qrs = _run_queries(name, system, QUERIES)
        results[name] = SystemResult(
            name=name, ingest_ms=ingest_ms, query_results=qrs,
        )
        print()

    # Print summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, sr in results.items():
        c_ok, c_n = sr.score_by_kind("current")
        t_ok, t_n = sr.score_by_kind("temporal")
        print(
            f"  {name:14s} current: {c_ok}/{c_n}  temporal: {t_ok}/{t_n}  "
            f"overall: {sr.correct}/{sr.total}"
        )

    # Write report
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"run_{stamp}.md"
    report_path.write_text(
        _render_report(results, len(CORPUS), len(QUERIES)), encoding="utf-8",
    )
    print(f"\nreport -> {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

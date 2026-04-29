"""Orchestrator for E7 — Conversational Memory Stress.

Usage:
    uv run python -m benchmarks.e7_conversational.run

Ingests a 4-session, 25-turn multi-day dialog between an engineer and an
AI coding assistant about an auth-refactor project. Queries cover six
axes: pronoun resolution, cross-session reference, preference evolution,
granularity (precise + broad), and forgetting/stale-update detection.

Report: markdown at benchmarks/e7_conversational/results/run_YYYYMMDD_HHMMSS.md
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
    HybridFlat, MFlowLite, Mem0Lite, MultiTierMemory,
    PrototypeMemory, SupermemoryLite, ZepLite,
)

from .corpus import all_turns_sorted
from .queries import QUERIES, Query, score


@dataclass
class QueryResult:
    qid: str
    question: str
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
        return (sum(1 for r in matching if r.correct), len(matching))


def _ingest(name: str, system, turns) -> int:
    t0 = time.time()
    for turn in turns:
        try:
            system.ingest(turn)
        except Exception as e:
            print(f"  [{name}] ingest error on {turn.id}: {e}")
    return int((time.time() - t0) * 1000)


def _run_queries(name: str, system) -> list[QueryResult]:
    out: list[QueryResult] = []
    for q in QUERIES:
        t0 = time.time()
        try:
            answer = system.query(q.question)
        except Exception as e:
            answer = f"(error: {e})"
        dur = int((time.time() - t0) * 1000)
        correct = score(answer, q)
        out.append(QueryResult(
            qid=q.id, question=q.question, axis=q.axis,
            expected=q.correct_key, answer=answer,
            correct=correct, duration_ms=dur,
        ))
        mark = "✓" if correct else "✗"
        print(f"  [{name}] {q.id} ({q.axis}) {mark} ({dur}ms) exp={q.correct_key!r}: {answer[:110]}")
    return out


def _render(results: dict[str, SystemResult], n_turns: int) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = [
        f"# E7 — Conversational Memory Stress — results\n",
        f"*Run: {now}*\n",
        f"Corpus: {n_turns} turns across 4 sessions (Mon-Fri auth-refactor dialog). "
        f"{len(QUERIES)} queries across 6 axes.\n",
    ]
    axes = sorted({q.axis for q in QUERIES})
    lines.append("## Summary by axis\n")
    header = "| system | " + " | ".join(axes) + " | overall | ingest ms |"
    sep = "|" + "---|" * (len(axes) + 3)
    lines.append(header)
    lines.append(sep)
    for name, sr in results.items():
        cells = []
        for ax in axes:
            ok, n = sr.score_by_axis(ax)
            cells.append(f"{ok}/{n}")
        lines.append(
            f"| **{name}** | " + " | ".join(cells) +
            f" | **{sr.correct}/{sr.total}** | {sr.ingest_ms} |"
        )
    lines.append("")
    for name, sr in results.items():
        lines.append(f"## {name}\n")
        lines.append("| qid | axis | expected | correct | answer |")
        lines.append("|---|---|---|---|---|")
        for r in sr.results:
            mark = "✓" if r.correct else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:180]
            lines.append(
                f"| {r.qid} | {r.axis} | {r.expected} | {mark} | {ans} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    turns = all_turns_sorted()
    print(f"E7 — {len(turns)} turns across 4 sessions")
    print(f"      {len(QUERIES)} queries across "
          f"{len({q.axis for q in QUERIES})} axes")
    print()

    client = LLMClient()
    systems = {
        "hybrid_flat": HybridFlat(client),
        "zep_lite": ZepLite(client),
        "mem0_lite": Mem0Lite(client),
        "supermemory_lite": SupermemoryLite(client),
        "m_flow_lite": MFlowLite(client),
        "prototype": PrototypeMemory(client),
        "multitier": MultiTierMemory(client, episode_size=200),
        "epistemic_prototype": EpistemicPrototype(client),
        "gapaware_prototype": GapAwarePrototype(client),
    }

    results: dict[str, SystemResult] = {}
    for name, system in systems.items():
        print(f"[{name}] ingesting {len(turns)} turns...")
        ingest_ms = _ingest(name, system, turns)
        print(f"[{name}] ingest done in {ingest_ms}ms")
        print(f"[{name}] running queries...")
        qrs = _run_queries(name, system)
        results[name] = SystemResult(
            name=name, ingest_ms=ingest_ms, results=qrs,
        )
        print()

    print("=" * 72)
    print("SUMMARY BY AXIS")
    print("=" * 72)
    axes = sorted({q.axis for q in QUERIES})
    for name, sr in results.items():
        parts = [f"{ax}={sr.score_by_axis(ax)[0]}/{sr.score_by_axis(ax)[1]}"
                 for ax in axes]
        print(f"  {name:18s} " + "  ".join(parts) + f"  | overall {sr.correct}/{sr.total}")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(results, len(turns)), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

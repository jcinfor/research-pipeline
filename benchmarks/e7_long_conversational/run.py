"""Orchestrator for E7-long — conversational memory at 100-turn scale.

Usage:
    uv run python -m benchmarks.e7_long_conversational.run

Extends E7's 23-turn auth-refactor into an 8-session, ~80-turn arc over
8 weeks. Tests whether zep's E7 win (6/6 on 23 turns) survives at scale
where:
    - zep's triples accumulate (context length may blow up)
    - pronouns span 80+ turns from antecedent
    - preferences flip multiple times across weeks
    - entity roles change (Alice transferring teams)
    - some topics never resolve
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

    def score_by_axis(self, axis: str) -> tuple[int, int]:
        matching = [r for r in self.results if r.axis == axis]
        return (sum(1 for r in matching if r.correct), len(matching))


def _ingest(name: str, system, turns) -> tuple[int, int]:
    t0 = time.time()
    errs = 0
    for turn in turns:
        try:
            system.ingest(turn)
        except Exception as e:
            errs += 1
            if errs <= 3:
                print(f"  [{name}] ingest error on {turn.id}: {str(e)[:120]}")
    return int((time.time() - t0) * 1000), errs


def _run_queries(name: str, system) -> list[QueryResult]:
    out: list[QueryResult] = []
    for q in QUERIES:
        t0 = time.time()
        try:
            answer = system.query(q.question)
        except Exception as e:
            answer = f"(error: {str(e)[:120]})"
        dur = int((time.time() - t0) * 1000)
        correct = score(answer, q)
        out.append(QueryResult(
            qid=q.id, question=q.question, axis=q.axis,
            turns_distance=q.turns_distance, expected=q.correct_key,
            answer=answer, correct=correct, duration_ms=dur,
        ))
        mark = "✓" if correct else "✗"
        print(f"  [{name}] {q.id} ({q.axis}, d={q.turns_distance}) {mark} ({dur}ms) exp={q.correct_key!r}: {answer[:100]}")
    return out


def _render(results: dict[str, SystemResult], n_turns: int) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = [
        f"# E7-long — Conversational Memory at 100-turn scale — results\n",
        f"*Run: {now}*\n",
        f"Corpus: {n_turns} turns across 11 sessions (8 weeks). "
        f"{len(QUERIES)} queries across "
        f"{len({q.axis for q in QUERIES})} axes.\n",
    ]
    lines.append("## Summary\n")
    axes = sorted({q.axis for q in QUERIES})
    header = "| system | " + " | ".join(axes) + " | overall | ingest ms |"
    sep = "|" + "---|" * (len(axes) + 3)
    lines.append(header)
    lines.append(sep)
    for name, sr in results.items():
        cells = [f"{sr.score_by_axis(a)[0]}/{sr.score_by_axis(a)[1]}" for a in axes]
        lines.append(
            f"| **{name}** | " + " | ".join(cells)
            + f" | **{sr.correct}/{sr.total}** | {sr.ingest_ms} |"
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
    print(f"E7-long — {len(turns)} turns across 11 sessions (8 weeks)")
    print(f"          {len(QUERIES)} queries across "
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
        ingest_ms, errs = _ingest(name, system, turns)
        print(f"[{name}] ingest done in {ingest_ms}ms ({errs} errors)")
        print(f"[{name}] running queries...")
        qrs = _run_queries(name, system)
        results[name] = SystemResult(
            name=name, ingest_ms=ingest_ms, results=qrs,
            error=f"{errs} ingest errors" if errs else None,
        )
        print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for name, sr in results.items():
        print(f"  {name:18s} overall {sr.correct}/{sr.total}  ingest {sr.ingest_ms}ms  "
              f"{sr.error or ''}")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(results, len(turns)), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

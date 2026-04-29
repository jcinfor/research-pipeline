"""Orchestrator for E1-TTL — test whether supermemory's TTL + chunk fallback
preserves or evicts older-but-still-current facts under an interleaved hot
stream.

Usage:
    uv run python -m benchmarks.e1_ttl.run

Scenario: Alice gets one cold fact at t=0. Server Prod-01 gets 20 status
updates from t=7d onwards. Queries:
    Q_cold: "What is Alice's favourite_color?" (expected: blue — never
            superseded)
    Q_hot:  "What is Server Prod-01's current status?" (expected: green)

Systems:
    mem0_lite                        — no TTL (baseline)
    supermemory_lite_ttl=none        — no TTL (should match mem0)
    supermemory_lite_ttl=1h          — short TTL, fires on cold doc
    supermemory_lite_ttl=30d         — long TTL, should not fire
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

from benchmarks.e1_blackboard_stress.systems import Mem0Lite, SupermemoryLite

from .corpus import STREAM


@dataclass
class QueryResult:
    label: str
    question: str
    expected: str
    wrong: tuple[str, ...]
    answer: str
    fidelity: int
    query_ms: int


@dataclass
class SystemResult:
    name: str
    ingest_ms: int = 0
    query_results: list[QueryResult] = field(default_factory=list)

    @property
    def fidelity(self) -> int:
        return sum(r.fidelity for r in self.query_results)

    @property
    def total(self) -> int:
        return len(self.query_results)


def _score(answer: str, expected: str, wrong: tuple[str, ...]) -> int:
    if not answer:
        return 0
    a = answer.lower()
    if expected.lower() not in a:
        return 0
    for w in wrong:
        if w.lower() != expected.lower() and w.lower() in a:
            return 0
    return 1


def _run(name: str, system, stream) -> SystemResult:
    t0 = time.time()
    for doc in stream.docs:
        try:
            system.ingest(doc)
        except Exception as e:
            print(f"  [{name}] ingest error on {doc.id}: {e}")
    ingest_ms = int((time.time() - t0) * 1000)
    print(f"[{name}] ingest done in {ingest_ms}ms")

    cold_expected = stream.cold_value
    hot_expected = stream.hot_values[-1]
    hot_wrong = tuple(v for v in stream.hot_values[:-1] if v != hot_expected)

    queries = [
        (
            "Q_cold",
            f"What is {stream.cold_entity}'s {stream.cold_attribute}?",
            cold_expected,
            tuple(),
        ),
        (
            "Q_hot",
            f"What is the current {stream.hot_attribute} of {stream.hot_entity}?",
            hot_expected,
            hot_wrong,
        ),
    ]

    sr = SystemResult(name=name, ingest_ms=ingest_ms)
    for label, q, expected, wrong in queries:
        t1 = time.time()
        try:
            answer = system.query(q)
        except Exception as e:
            answer = f"(error: {e})"
        dur = int((time.time() - t1) * 1000)
        fid = _score(answer, expected, wrong)
        sr.query_results.append(QueryResult(
            label=label, question=q, expected=expected, wrong=wrong,
            answer=answer, fidelity=fid, query_ms=dur,
        ))
        mark = "✓" if fid else "✗"
        print(f"  [{name}] {label} {mark} ({dur}ms) expected={expected!r}: {answer[:100]}")
    return sr


def _render(results: dict[str, SystemResult]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [f"# E1-TTL — results\n", f"*Run: {now}*\n",
             f"Scenario: 1 cold doc for Alice's favourite_color (never superseded) "
             f"+ 20 interleaved hot docs for Prod-01 starting 7 days later.\n"]
    lines.append("## Summary\n")
    lines.append("| system | Q_cold | Q_hot | total | ingest ms |")
    lines.append("|---|---|---|---|---|")
    for name, sr in results.items():
        cold_mark = "✓" if sr.query_results[0].fidelity else "✗"
        hot_mark = "✓" if sr.query_results[1].fidelity else "✗"
        lines.append(
            f"| **{name}** | {cold_mark} | {hot_mark} | {sr.fidelity}/{sr.total} | {sr.ingest_ms} |"
        )
    lines.append("")
    for name, sr in results.items():
        lines.append(f"## {name}\n")
        lines.append("| label | expected | answer | fidelity |")
        lines.append("|---|---|---|---|")
        for r in sr.query_results:
            mark = "✓" if r.fidelity else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:160]
            lines.append(f"| {r.label} | {r.expected} | {ans} | {mark} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"E1-TTL — {len(STREAM.docs)} docs (1 cold + {len(STREAM.hot_values)} hot)")
    print()
    client = LLMClient()

    # 4 system variants sharing the same extraction prompt, differing only in TTL.
    variants = [
        ("mem0_lite",                       Mem0Lite(client)),
        ("supermem_ttl=none",               SupermemoryLite(client, default_ttl_sec=None)),
        ("supermem_ttl=1h",                 SupermemoryLite(client, default_ttl_sec=3600)),
        ("supermem_ttl=30d",                SupermemoryLite(client, default_ttl_sec=30 * 86400)),
    ]

    results: dict[str, SystemResult] = {}
    for name, system in variants:
        print(f"[{name}] ingesting {len(STREAM.docs)} docs...")
        results[name] = _run(name, system, STREAM)
        print()

    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    for name, sr in results.items():
        print(f"  {name:24s} cold/hot: {sr.fidelity}/{sr.total}  ingest: {sr.ingest_ms}ms")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(results), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

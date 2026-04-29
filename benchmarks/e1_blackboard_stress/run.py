"""Orchestrator for the E1 Blackboard Stress Test.

Usage:
    uv run python -m benchmarks.e1_blackboard_stress.run

Feeds a high-velocity interleaved stream of state-change updates across
three entities into four memory systems (HybridFlat, HybridRecency, ZepLite,
Mem0Lite), then asks each system for the LATEST value of every attribute.

Scoring: fidelity = 1 if the answer contains the final ground-truth value
and none of the superseded values; else 0.

Report: markdown at benchmarks/e1_blackboard_stress/results/run_YYYYMMDD_HHMMSS.md
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

from .corpus import STREAMS, Stream, interleaved_docs
from .systems import (
    EpistemicPrototype, GapAwarePrototype,
    HybridFlat, HybridRecency, MFlowLite, Mem0Lite, MultiTierMemory,
    PrototypeMemory, SupermemoryLite, ZepLite,
)


@dataclass
class StreamResult:
    stream_entity: str
    stream_attribute: str
    expected: str
    superseded: tuple[str, ...]
    answer: str
    fidelity: int  # 1 or 0
    query_ms: int


@dataclass
class SystemResult:
    name: str
    ingest_ms: int = 0
    chat_calls_ingest: int = 0
    chat_calls_query: int = 0
    stream_results: list[StreamResult] = field(default_factory=list)

    @property
    def fidelity(self) -> int:
        return sum(r.fidelity for r in self.stream_results)

    @property
    def total(self) -> int:
        return len(self.stream_results)


def _score(answer: str, expected: str, superseded: tuple[str, ...]) -> int:
    if not answer:
        return 0
    a = answer.lower()
    if expected.lower() not in a:
        return 0
    for s in superseded:
        # A superseded value appearing in the answer counts as a failure
        # (e.g. "was 101.2, now 99.0" is ambiguous — we want ONLY the latest).
        if s.lower() != expected.lower() and s.lower() in a:
            return 0
    return 1


def _run_ingest(name: str, system, docs) -> tuple[int, int]:
    # Count LLM chat calls (for systems that expose .llm with a counter, we
    # sniff via a lightweight wrapper set up before ingest). Simpler: rely
    # on the LLMClient not exposing a counter — we time-only here, and
    # estimate chat calls by system type.
    start = time.time()
    for doc in docs:
        try:
            system.ingest(doc)
        except Exception as e:
            print(f"  [{name}] ingest error on {doc.id}: {e}")
    dur_ms = int((time.time() - start) * 1000)
    # Chat calls per doc: 0 for hybrid variants, 1 for Zep/Mem0/Supermemory.
    chat_calls = 0 if "hybrid" in name else len(docs)
    return dur_ms, chat_calls


def _run_queries(name: str, system, streams: tuple[Stream, ...]) -> tuple[list[StreamResult], int]:
    out: list[StreamResult] = []
    calls = 0
    for s in streams:
        expected = s.values[-1]
        superseded = tuple(v for v in s.values[:-1] if v != expected)
        question = f"What is the current {s.attribute} of {s.entity}?"
        t0 = time.time()
        try:
            answer = system.query(question)
        except Exception as e:
            answer = f"(error: {e})"
        calls += 1
        dur = int((time.time() - t0) * 1000)
        fid = _score(answer, expected, superseded)
        out.append(StreamResult(
            stream_entity=s.entity, stream_attribute=s.attribute,
            expected=expected, superseded=superseded,
            answer=answer, fidelity=fid, query_ms=dur,
        ))
        mark = "✓" if fid else "✗"
        print(f"  [{name}] {s.entity}/{s.attribute} {mark} ({dur}ms) expected={expected!r}: {answer[:100]}")
    return out, calls


def _render_report(results: dict[str, SystemResult], n_docs: int, n_streams: int) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append(f"# E1 Blackboard Stress Test — results\n")
    lines.append(f"*Run: {now}*\n")
    lines.append(
        f"Corpus: {n_docs} docs across {n_streams} interleaved streams "
        f"({n_docs // n_streams} updates per stream)\n"
    )
    lines.append("## Summary\n")
    lines.append("| system | fidelity | ingest ms | avg query ms | write LLM calls |")
    lines.append("|---|---|---|---|---|")
    for name, sr in results.items():
        avg_q = (sum(r.query_ms for r in sr.stream_results) / sr.total) if sr.total else 0
        lines.append(
            f"| **{name}** | {sr.fidelity}/{sr.total} | {sr.ingest_ms} | "
            f"{avg_q:.0f} | {sr.chat_calls_ingest} |"
        )
    lines.append("")
    for name, sr in results.items():
        lines.append(f"## {name}\n")
        lines.append("| entity | attribute | expected | fidelity | answer |")
        lines.append("|---|---|---|---|---|")
        for r in sr.stream_results:
            mark = "✓" if r.fidelity else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:160]
            lines.append(
                f"| {r.stream_entity} | {r.stream_attribute} | {r.expected} | "
                f"{mark} | {ans} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    docs = interleaved_docs(STREAMS)
    print(f"E1 benchmark — {len(docs)} interleaved docs across {len(STREAMS)} streams")
    print(f"  stream sizes: {[len(s.docs) for s in STREAMS]}")
    print()

    client = LLMClient()
    systems: dict = {
        "hybrid_flat": HybridFlat(client),
        "hybrid_recency": HybridRecency(client),
        "zep_lite": ZepLite(client),
        "mem0_lite": Mem0Lite(client),
        "supermemory_lite": SupermemoryLite(client),
        "m_flow_lite": MFlowLite(client),
        "prototype": PrototypeMemory(client),
        "multitier": MultiTierMemory(client, episode_size=200),
        "epistemic_prototype": EpistemicPrototype(client),
        "gapaware_prototype": GapAwarePrototype(client),
    }
    # Optionally include real mem0 if requested (closes Gap 1: lite vs real).
    import os
    if os.environ.get("RP_BENCH_INCLUDE_MEM0_REAL"):
        from benchmarks._real_products.mem0_real import Mem0Real
        systems["mem0_real"] = Mem0Real(collection="e1_bench")
    if os.environ.get("RP_BENCH_INCLUDE_MEM0_REAL_V3"):
        # Same Mem0Real adapter — the active mem0 package version determines
        # the algorithm. Assert the v3 marker so a v2 install (PyPI default)
        # can't silently produce v2 numbers labeled as `mem0_real_v3`.
        try:
            from mem0.configs.prompts import ADDITIVE_EXTRACTION_PROMPT  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "RP_BENCH_INCLUDE_MEM0_REAL_V3 set but installed mem0 lacks v3 markers "
                "(ADDITIVE_EXTRACTION_PROMPT not found in mem0.configs.prompts). "
                "Install v3 from mem0 git mainline via "
                "`uv pip install git+https://github.com/mem0ai/mem0.git@693e7093` "
                "(or via the [tool.uv.sources] path pin in pyproject.toml + a local clone). "
                "See BENCHMARKS.md → Reproducing v3 vs v2."
            )
        from benchmarks._real_products.mem0_real import Mem0Real
        systems["mem0_real_v3"] = Mem0Real(collection="e1_bench_v3")

    results: dict[str, SystemResult] = {}
    for name, sys_obj in systems.items():
        print(f"[{name}] ingesting {len(docs)} docs...")
        ingest_ms, chat_calls_ingest = _run_ingest(name, sys_obj, docs)
        print(f"[{name}] ingest done in {ingest_ms}ms ({chat_calls_ingest} chat calls)")
        print(f"[{name}] running queries...")
        qrs, chat_calls_q = _run_queries(name, sys_obj, STREAMS)
        results[name] = SystemResult(
            name=name, ingest_ms=ingest_ms,
            chat_calls_ingest=chat_calls_ingest,
            chat_calls_query=chat_calls_q,
            stream_results=qrs,
        )
        print()

    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    for name, sr in results.items():
        print(f"  {name:16s} fidelity: {sr.fidelity}/{sr.total}  ingest: {sr.ingest_ms}ms  write_llm: {sr.chat_calls_ingest}")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(
        _render_report(results, len(docs), len(STREAMS)), encoding="utf-8",
    )
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Orchestrator for E5 — Noisy Extraction.

Tests whether supermemory's chunk fallback rescues fidelity when extraction
fails on the LATEST docs of each stream (the case its design anticipates).

Usage:
    uv run python -m benchmarks.e5_noisy_extraction.run

Setup:
    Same 3 × 20 stream corpus as E1 (60 docs interleaved).
    A FaultyLLMClient wraps the real LLMClient and returns empty
    extraction JSON for the LAST `tail_fail_k` docs of each stream.
    Chat calls that are NOT extractions (i.e. queries) pass through.
    Embed calls always pass through — chunks are unaffected.

Predictions:
    mem0_lite        — relies solely on profile; with tail failures the
                       profile holds a stale value. Expected: near-0 fidelity.
    supermemory_lite — profile also holds stale value BUT the chunk store
                       has the latest docs. The LLM sees both and should
                       prefer the most recent passage. Expected: higher
                       fidelity than mem0.
    hybrid_flat      — baseline: chunks only, no extraction to corrupt.
                       Expected: same as E1 (1/3 or so).
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

from benchmarks.e1_blackboard_stress.corpus import STREAMS, interleaved_docs
from benchmarks.e1_blackboard_stress.systems import (
    EpistemicPrototype, GapAwarePrototype,
    HybridFlat, Mem0Lite, MultiTierMemory, PrototypeMemory, SupermemoryLite,
)


# ---------------------------------------------------------------------------
# Faulty LLM wrapper — injects extraction failures on tail docs
# ---------------------------------------------------------------------------


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class FaultyLLMClient:
    """Wraps a real LLMClient. Returns empty extraction JSON for docs whose
    pub_date is in the `fail_pub_dates` set. Queries pass through.

    Detects "extraction" calls by checking whether the user message includes
    'Extract'. Embed calls always pass through.
    """
    def __init__(self, inner: LLMClient, fail_pub_dates: set[str]):
        self.inner = inner
        self.fail_pub_dates = fail_pub_dates

    def chat(self, role, messages, **kwargs):
        user = next(
            (m.get("content", "") for m in messages if m.get("role") == "user"),
            "",
        )
        system_prompt = next(
            (m.get("content", "") for m in messages if m.get("role") == "system"),
            "",
        )
        is_extract = "Extract" in system_prompt and "DOCUMENT" in user
        if is_extract:
            matched = any(pub in user for pub in self.fail_pub_dates)
            if matched:
                # Return an empty fact list — simulates LLM extraction failure.
                return _Resp(choices=[_Choice(message=_Msg(content='{"facts": [], "triples": []}'))])
        return self.inner.chat(role, messages, **kwargs)

    def embed(self, role, texts):
        return self.inner.embed(role, texts)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class StreamResult:
    entity: str
    attribute: str
    expected: str
    superseded: tuple[str, ...]
    answer: str
    fidelity: int
    query_ms: int


@dataclass
class SystemResult:
    name: str
    ingest_ms: int = 0
    stream_results: list[StreamResult] = field(default_factory=list)

    @property
    def fidelity(self) -> int:
        return sum(r.fidelity for r in self.stream_results)

    @property
    def total(self) -> int:
        return len(self.stream_results)


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


def _tail_failure_pub_dates(streams, k: int) -> set[str]:
    """Pub_dates of the LAST `k` docs of each stream."""
    out: set[str] = set()
    for s in streams:
        for d in s.docs[-k:]:
            out.add(d.pub_date)
    return out


def _run(name: str, system, docs) -> SystemResult:
    t0 = time.time()
    for doc in docs:
        try:
            system.ingest(doc)
        except Exception as e:
            print(f"  [{name}] ingest error on {doc.id}: {e}")
    ingest_ms = int((time.time() - t0) * 1000)
    print(f"[{name}] ingest done in {ingest_ms}ms")

    sr = SystemResult(name=name, ingest_ms=ingest_ms)
    for s in STREAMS:
        expected = s.values[-1]
        superseded = tuple(v for v in s.values[:-1] if v != expected)
        q = f"What is the current {s.attribute} of {s.entity}?"
        t1 = time.time()
        try:
            answer = system.query(q)
        except Exception as e:
            answer = f"(error: {e})"
        dur = int((time.time() - t1) * 1000)
        fid = _score(answer, expected, superseded)
        sr.stream_results.append(StreamResult(
            entity=s.entity, attribute=s.attribute,
            expected=expected, superseded=superseded,
            answer=answer, fidelity=fid, query_ms=dur,
        ))
        mark = "✓" if fid else "✗"
        print(f"  [{name}] {s.entity}/{s.attribute} {mark} ({dur}ms) expected={expected!r}: {answer[:100]}")
    return sr


def _render(results: dict[str, SystemResult], tail_k: int) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [f"# E5 — Noisy Extraction (tail-failure) — results\n",
             f"*Run: {now}*\n",
             f"Fault: extraction LLM returns empty facts for the LAST {tail_k} docs of each stream "
             f"(so the profile's final snapshot is stale by {tail_k} updates). Chunks unaffected.\n"]
    lines.append("## Summary\n")
    lines.append("| system | fidelity | ingest ms |")
    lines.append("|---|---|---|")
    for name, sr in results.items():
        lines.append(f"| **{name}** | {sr.fidelity}/{sr.total} | {sr.ingest_ms} |")
    lines.append("")
    for name, sr in results.items():
        lines.append(f"## {name}\n")
        lines.append("| entity | attribute | expected | fidelity | answer |")
        lines.append("|---|---|---|---|---|")
        for r in sr.stream_results:
            mark = "✓" if r.fidelity else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:160]
            lines.append(
                f"| {r.entity} | {r.attribute} | {r.expected} | {mark} | {ans} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    docs = interleaved_docs(STREAMS)
    tail_k = 5  # last 5 updates per stream have extraction failures
    fail_dates = _tail_failure_pub_dates(STREAMS, tail_k)
    print(f"E5 benchmark — {len(docs)} docs; tail-failure k={tail_k} "
          f"({len(fail_dates)} fault-injected pub_dates)")
    print()

    real = LLMClient()
    faulty = FaultyLLMClient(real, fail_dates)

    # hybrid_flat uses REAL client (no extraction to corrupt)
    # mem0/supermemory use FAULTY client
    systems = {
        "hybrid_flat": HybridFlat(real),
        "mem0_lite": Mem0Lite(faulty),  # type: ignore[arg-type]
        "supermemory_lite": SupermemoryLite(faulty),  # type: ignore[arg-type]
        "prototype": PrototypeMemory(faulty),  # type: ignore[arg-type]
        "multitier": MultiTierMemory(faulty, episode_size=200),  # type: ignore[arg-type]
        "epistemic_prototype": EpistemicPrototype(faulty),  # type: ignore[arg-type]
        "gapaware_prototype": GapAwarePrototype(faulty),  # type: ignore[arg-type]
    }

    results: dict[str, SystemResult] = {}
    for name, system in systems.items():
        print(f"[{name}] ingesting {len(docs)} docs...")
        results[name] = _run(name, system, docs)
        print()

    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    for name, sr in results.items():
        print(f"  {name:20s} fidelity: {sr.fidelity}/{sr.total}  ingest: {sr.ingest_ms}ms")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(results, tail_k), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

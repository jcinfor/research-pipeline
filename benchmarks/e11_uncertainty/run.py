"""Orchestrator for E11 — Uncertainty Calibration.

Usage:
    uv run python -m benchmarks.e11_uncertainty.run

Tests whether memory systems honestly say "I don't know" when asked about
facts that were never recorded — or hallucinate plausible answers.

Five systems × ten queries (2 control + 3 missing-attribute + 2 missing-entity
+ 3 never-happened). Substring-based scoring with uncertainty markers + a
hallucination-value blocklist.

This is the gap nobody in our suite addressed across E1-E10. Every system
hallucinates "no" or a confident answer when fact wasn't recorded.
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
    EpistemicPrototype, GapAwarePrototype, IntentRoutedZep, MFlowLite,
    MFlowRich, Mem0Lite, MultiTierMemory, PrototypeMemory, SupermemoryLite,
    ZepLite, ZepRich,
)
from benchmarks.e10_scale_out.corpus import populate_mem0, populate_zep
from benchmarks.e10_scale_out.run import populate_mflow, populate_prototype

from .corpus import CORPUS
from .queries import QUERIES, Query, score


@dataclass
class QueryResult:
    qid: str
    category: str
    answer: str
    correct: bool
    duration_ms: int


@dataclass
class SystemResult:
    name: str
    populate_ms: int = 0
    results: list[QueryResult] = field(default_factory=list)

    @property
    def correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    @property
    def total(self) -> int:
        return len(self.results)

    def score_by_category(self, category: str) -> tuple[int, int]:
        matching = [r for r in self.results if r.category == category]
        return sum(1 for r in matching if r.correct), len(matching)


def _populate_supermemory(system, triples) -> None:
    """SupermemoryLite stores both profile + chunks. We synthesize from
    triples directly: profile-row per (entity,attribute,latest), no chunks
    (since we're skipping extraction). This mirrors what its real ingest
    would produce."""
    for t in triples:
        ek, ak = t.entity.lower(), t.attribute.lower()
        prior = system.memory.setdefault(ek, {}).get(ak)
        if prior is None or t.valid_from >= prior["updated_at"]:
            system.memory[ek][ak] = {
                "value": t.value, "entity": t.entity, "attribute": t.attribute,
                "updated_at": t.valid_from, "source_doc": t.source_doc,
                "ttl_sec": None,
            }


def _new_system_and_populate(name: str, client: LLMClient, triples):
    if name == "mem0_lite":
        s = Mem0Lite(client)
        populate_mem0(s, triples)
    elif name == "zep_lite":
        s = ZepLite(client)
        populate_zep(s, triples)
    elif name == "zep_rich":
        s = ZepRich(client)
        populate_zep(s, triples)
    elif name == "intent_routed_zep":
        s = IntentRoutedZep(client)
        populate_zep(s, triples)
    elif name == "supermemory_lite":
        s = SupermemoryLite(client)
        _populate_supermemory(s, triples)
    elif name == "m_flow_lite":
        s = MFlowLite(client)
        populate_mflow(s, triples)
    elif name == "m_flow_rich":
        s = MFlowRich(client)
        populate_mflow(s, triples)
    elif name == "prototype":
        s = PrototypeMemory(client)
        populate_prototype(s, triples)
    elif name == "multitier":
        s = MultiTierMemory(client, episode_size=200)
        populate_prototype(s, triples)
    elif name == "gapaware_prototype":
        s = GapAwarePrototype(client)
        # Substrate parity: same triple-set as base prototype.
        populate_prototype(s, triples)
        # Architectural parity: also exercise gap detection by feeding a
        # synthesized text per triple. E11's corpus has no rich source-doc
        # text, so this is the only way the gap-detect LLM call can fire.
        # Expected: short structured triple-text rarely raises gaps, so the
        # gap-detection feature is genuinely under-tested by E11's design.
        # That's a corpus-shape limitation, not a wiring shortcut.
        for t in triples:
            text = (
                f"On {t.valid_from}, {t.entity}'s {t.attribute} = {t.value}."
            )
            s.detect_gaps_from_text(
                text, source_id=t.source_doc, pub_date=t.valid_from,
            )
    elif name == "epistemic_prototype":
        s = EpistemicPrototype(client)
        populate_prototype(s, triples)
    else:
        raise ValueError(name)
    return s


def _run(name: str, client: LLMClient, triples) -> SystemResult:
    t0 = time.time()
    system = _new_system_and_populate(name, client, triples)
    populate_ms = int((time.time() - t0) * 1000)
    sr = SystemResult(name=name, populate_ms=populate_ms)
    print(f"[{name}] populated in {populate_ms}ms")
    for q in QUERIES:
        t1 = time.time()
        try:
            answer = system.query(q.question)
        except Exception as e:
            answer = f"(error: {str(e)[:120]})"
        dur = int((time.time() - t1) * 1000)
        ok = score(answer, q)
        sr.results.append(QueryResult(
            qid=q.id, category=q.category,
            answer=answer, correct=ok, duration_ms=dur,
        ))
        mark = "✓" if ok else "✗"
        print(f"  [{name}] {q.id} ({q.category}) {mark} ({dur}ms): {answer[:120]}")
    return sr


def _render(rows: dict[str, SystemResult]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    cats = sorted({q.category for q in QUERIES})
    lines = [
        f"# E11 — Uncertainty Calibration — results\n",
        f"*Run: {now}*\n",
        f"3 entities × 3 attributes × 3 obs = {len(CORPUS)} triples. "
        f"{len(QUERIES)} queries: control / missing_attribute / missing_entity / never_happened.\n",
    ]
    lines.append("## Summary by category\n")
    header = "| system | " + " | ".join(cats) + " | overall |"
    sep = "|" + "---|" * (len(cats) + 2)
    lines.append(header)
    lines.append(sep)
    for name, sr in rows.items():
        cells = [
            f"{sr.score_by_category(c)[0]}/{sr.score_by_category(c)[1]}"
            for c in cats
        ]
        lines.append(f"| **{name}** | " + " | ".join(cells) + f" | **{sr.correct}/{sr.total}** |")
    lines.append("")
    for name, sr in rows.items():
        lines.append(f"## {name}\n")
        lines.append("| qid | category | correct | answer |")
        lines.append("|---|---|---|---|")
        for r in sr.results:
            mark = "✓" if r.correct else "✗"
            ans = r.answer.replace("\n", " ").replace("|", "\\|")[:200]
            lines.append(f"| {r.qid} | {r.category} | {mark} | {ans} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"E11 — Uncertainty Calibration")
    print(f"     {len(CORPUS)} triples, {len(QUERIES)} queries")
    print()
    client = LLMClient()
    triples = CORPUS

    rows: dict[str, SystemResult] = {}
    for name in ("mem0_lite", "zep_lite", "zep_rich",
                 "intent_routed_zep", "supermemory_lite",
                 "m_flow_lite", "m_flow_rich", "prototype", "multitier",
                 "epistemic_prototype", "gapaware_prototype"):
        sr = _run(name, client, triples)
        rows[name] = sr
        print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    cats = sorted({q.category for q in QUERIES})
    for name, sr in rows.items():
        parts = [f"{c}={sr.score_by_category(c)[0]}/{sr.score_by_category(c)[1]}" for c in cats]
        print(f"  {name:20s} " + "  ".join(parts) + f"  | overall {sr.correct}/{sr.total}")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(rows), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

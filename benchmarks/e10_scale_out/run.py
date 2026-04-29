"""Orchestrator for E10 — Scale-Out Test.

Usage:
    uv run python -m benchmarks.e10_scale_out.run

Tests query-time behavior at increasing corpus sizes. Skips LLM extraction
(populates each system's storage directly) so we can run multiple scales
without burning hours of LLM calls. The scale-relevant variable is what
each system's .query() does at N triples — extraction cost is a separate
linear-scaling concern that's not the interesting question.

Scales: 100, 500, 1000, 2500, 5000 triples.

Predicted breakpoints:
  - mem0_lite:        constant cost (only stores latest); always answers
                      current correctly; always fails historical.
  - zep_lite:         linear in triples but always collapses query → only
                      current works; historical impossible.
  - zep_rich:         linear cost, accuracy degrades as context fills up;
                      may crash at 5000 triples (~250K tokens) on a 256K
                      context window.
  - intent_routed_zep: best of both — current via collapse (cheap, fast),
                      historical via full-history (slow at scale but correct).
                      THE workload designed to show routing's value.
  - hybrid_flat:      not run here; cosine retrieval over chunks isn't
                      directly comparable (it has its own scaling story).

Per scale level, we record: fidelity, avg query latency, max query latency,
estimated input tokens (from triple count), success/failure to complete.
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
    IntentRoutedZep, MFlowLite, MFlowRich, Mem0Lite, MultiTierMemory,
    PrototypeMemory, ZepLite, ZepRich,
)

from .corpus import make_triples, populate_mem0, populate_zep
from .queries import Query, build_queries, score


def populate_prototype(system, triples):
    """Populate PrototypeMemory's append-only log + hot index directly,
    skipping LLM extraction (matches the protocol used for the other
    systems in E10)."""
    for t in triples:
        system.add_triple(
            entity=t.entity, attribute=t.attribute, value=t.value,
            valid_from=t.valid_from, source_doc=t.source_doc,
        )


def populate_mflow(system, triples):
    """Directly populate MFlowLite/MFlowRich's cone — skips LLM extraction.
    Each triple becomes a FacetPoint under (entity, attribute) with an
    Episode tag. Same data structure as MFlowLite.ingest would produce."""
    for t in triples:
        ek, ak = t.entity.lower(), t.attribute.lower()
        episode_id = f"ep_{t.source_doc}"
        fp = {
            "value": t.value, "entity": t.entity, "attribute": t.attribute,
            "pub_date": t.valid_from, "doc_id": t.source_doc,
            "episode_id": episode_id,
        }
        system.cone.setdefault(ek, {}).setdefault(ak, []).append(fp)
        system.episodes.append({
            "id": episode_id, "source_doc": t.source_doc,
            "pub_date": t.valid_from, "facetpoints": [fp],
        })


SCALES: tuple[int, ...] = (100, 500, 1000, 2500, 5000)


@dataclass
class QueryResult:
    qid: str
    intent: str
    expected: str
    answer: str
    correct: bool
    duration_ms: int


@dataclass
class SystemAtScale:
    name: str
    scale: int
    populate_ms: int
    results: list[QueryResult] = field(default_factory=list)
    error: str | None = None

    @property
    def correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def avg_query_ms(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.duration_ms for r in self.results) / len(self.results)

    @property
    def max_query_ms(self) -> int:
        return max((r.duration_ms for r in self.results), default=0)

    def score_by_intent(self, intent: str) -> tuple[int, int]:
        matching = [r for r in self.results if r.intent == intent]
        return sum(1 for r in matching if r.correct), len(matching)


def _new_system(name: str, client: LLMClient):
    if name == "mem0_lite":
        return Mem0Lite(client)
    if name == "zep_lite":
        return ZepLite(client)
    if name == "zep_rich":
        return ZepRich(client)
    if name == "intent_routed_zep":
        return IntentRoutedZep(client)
    if name == "m_flow_lite":
        return MFlowLite(client)
    if name == "m_flow_rich":
        return MFlowRich(client)
    if name == "prototype":
        return PrototypeMemory(client)
    if name == "multitier":
        return MultiTierMemory(client, episode_size=1000)
    if name == "epistemic_prototype":
        return EpistemicPrototype(client)
    if name == "gapaware_prototype":
        return GapAwarePrototype(client)
    raise ValueError(name)


def _populate(name: str, system, triples) -> int:
    t0 = time.time()
    if name == "mem0_lite":
        populate_mem0(system, triples)
    elif name in ("m_flow_lite", "m_flow_rich"):
        populate_mflow(system, triples)
    elif name in ("prototype", "epistemic_prototype", "multitier"):
        # epistemic_prototype rides on the same triple-substrate; its
        # _maintain_hot_index override fires automatically through add_triple.
        # multitier inherits add_triple from PrototypeMemory and triggers
        # episode compression on its own once episode_size is hit.
        populate_prototype(system, triples)
    elif name == "gapaware_prototype":
        # Same triple-substrate as prototype, plus seed gap detection on
        # synthesized text per triple so the architectural feature actually
        # exercises (populate_prototype skips ingest()).
        populate_prototype(system, triples)
        for t in triples:
            text = (
                f"On {t.valid_from}, {t.entity}'s {t.attribute} = {t.value}."
            )
            system.detect_gaps_from_text(
                text, source_id=t.source_doc, pub_date=t.valid_from,
            )
    else:
        populate_zep(system, triples)
    return int((time.time() - t0) * 1000)


def _run_at_scale(
    name: str, client: LLMClient, scale: int, triples, queries: list[Query],
) -> SystemAtScale:
    system = _new_system(name, client)
    populate_ms = _populate(name, system, triples)
    sas = SystemAtScale(name=name, scale=scale, populate_ms=populate_ms)

    for q in queries:
        t0 = time.time()
        try:
            answer = system.query(q.question)
        except Exception as e:
            answer = f"(error: {str(e)[:160]})"
            # If we hit a context-overflow at large scale, mark and continue
            sas.error = sas.error or f"query failure: {str(e)[:80]}"
        dur = int((time.time() - t0) * 1000)
        ok = score(answer, q, triples)
        sas.results.append(QueryResult(
            qid=q.id, intent=q.intent, expected=q.correct_key,
            answer=answer, correct=ok, duration_ms=dur,
        ))
        mark = "✓" if ok else "✗"
        print(f"  [{name}@{scale}] {q.id} ({q.intent}) {mark} ({dur}ms): {answer[:80]}")
    return sas


def _render(rows: list[SystemAtScale]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        f"# E10 — Scale-Out Test — results\n",
        f"*Run: {now}*\n",
        f"Scales tested: {SCALES}. Five systems × {len(SCALES)} scales = "
        f"{5 * len(SCALES)} runs. Storage populated directly (no LLM extraction).\n",
    ]

    by_system: dict[str, list[SystemAtScale]] = {}
    for r in rows:
        by_system.setdefault(r.name, []).append(r)

    lines.append("## Fidelity by scale\n")
    header = "| system | " + " | ".join(f"{s} triples" for s in SCALES) + " |"
    sep = "|" + "---|" * (len(SCALES) + 1)
    lines.append(header)
    lines.append(sep)
    for name in by_system:
        cells = []
        for scale in SCALES:
            sas = next(
                (r for r in by_system[name] if r.scale == scale), None,
            )
            if sas is None:
                cells.append("—")
            else:
                cells.append(f"{sas.correct}/{sas.total}")
        lines.append(f"| **{name}** | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Avg query latency (ms) by scale\n")
    lines.append(header)
    lines.append(sep)
    for name in by_system:
        cells = []
        for scale in SCALES:
            sas = next((r for r in by_system[name] if r.scale == scale), None)
            cells.append("—" if sas is None else f"{sas.avg_query_ms:.0f}")
        lines.append(f"| **{name}** | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Per-intent fidelity (collapsed across scales)\n")
    intents = sorted({r.intent for sas in rows for r in sas.results})
    lines.append("| system | scale | " + " | ".join(intents) + " | error |")
    lines.append("|" + "---|" * (len(intents) + 3))
    for name in by_system:
        for sas in by_system[name]:
            cells = [
                f"{sas.score_by_intent(i)[0]}/{sas.score_by_intent(i)[1]}"
                for i in intents
            ]
            lines.append(
                f"| {name} | {sas.scale} | " + " | ".join(cells)
                + f" | {sas.error or ''} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"E10 — Scale-Out Test")
    print(f"     scales: {SCALES}")
    print(f"     systems: mem0_lite, zep_lite, zep_rich, intent_routed_zep")
    print()

    client = LLMClient()
    all_rows: list[SystemAtScale] = []

    for scale in SCALES:
        print(f"\n=== SCALE: {scale} triples ===")
        triples = make_triples(scale)
        queries = build_queries(triples)
        print(f"  generated {len(triples)} triples, {len(queries)} queries")

        for name in (
            "mem0_lite", "zep_lite", "zep_rich", "intent_routed_zep",
            "m_flow_lite", "m_flow_rich", "prototype", "multitier",
            "epistemic_prototype", "gapaware_prototype",
        ):
            sas = _run_at_scale(name, client, scale, triples, queries)
            all_rows.append(sas)
            ok = sas.correct
            print(
                f"  [{name}@{scale}] {ok}/{sas.total}  "
                f"avg_q={sas.avg_query_ms:.0f}ms  max_q={sas.max_query_ms}ms"
            )

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    by_system: dict[str, list[SystemAtScale]] = {}
    for r in all_rows:
        by_system.setdefault(r.name, []).append(r)
    for name, runs in by_system.items():
        cells = [f"{r.scale}={r.correct}/{r.total}" for r in runs]
        print(f"  {name:20s} " + "  ".join(cells))

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(all_rows), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

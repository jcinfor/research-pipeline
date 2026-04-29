"""Orchestrator for E10-XL — Extreme Scale (10k / 20k triples).

Usage:
    uv run python -m benchmarks.e10_xl_extreme_scale.run

Tests where intent_routed_zep / prototype themselves break under context
overflow on historical queries. At 10k triples × ~50 tokens each = ~500K
tokens, exceeds the 256K context window. Current-value queries should
still work via the hot-index / latest-per-key path.

Five systems: mem0_lite, zep_lite, zep_rich, intent_routed_zep, prototype.
Skips m_flow_rich (E10 already showed cone hierarchy degrades fastest).

Catches context-overflow exceptions per-query rather than crashing the run.
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
    IntentRoutedZep, Mem0Lite, MultiTierMemory, PrototypeMemory, ZepLite, ZepRich,
)
from benchmarks.e10_scale_out.corpus import make_triples, populate_mem0, populate_zep
from benchmarks.e10_scale_out.queries import build_queries, score
from benchmarks.e10_scale_out.run import populate_prototype


def populate_multitier(system: MultiTierMemory, triples) -> None:
    """Bulk-populate MultiTierMemory triggering compression at episode_size."""
    for t in triples:
        system.add_triple(
            entity=t.entity, attribute=t.attribute, value=t.value,
            valid_from=t.valid_from, source_doc=t.source_doc,
        )


# Bigger scales than E10. 50k skipped — 50000 × ~50 tokens = 2.5M context,
# clearly past any reasonable backend; we don't gain signal.
SCALES: tuple[int, ...] = (10000, 20000)


@dataclass
class QueryResult:
    qid: str
    intent: str
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

    def score_by_intent(self, intent: str) -> tuple[int, int]:
        m = [r for r in self.results if r.intent == intent]
        return sum(1 for r in m if r.correct), len(m)


def _new_system(name: str, client: LLMClient):
    if name == "mem0_lite":
        return Mem0Lite(client)
    if name == "zep_lite":
        return ZepLite(client)
    if name == "zep_rich":
        return ZepRich(client)
    if name == "intent_routed_zep":
        return IntentRoutedZep(client)
    if name == "prototype":
        return PrototypeMemory(client)
    if name == "multitier":
        # episode_size = 1000 → ~10 episodes at 10k, ~20 episodes at 20k.
        # Each episode digest is ~30 lines; total ctx for historical query
        # at 20k is ~600 lines = well under the 256K token window.
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
    elif name in ("prototype", "epistemic_prototype"):
        populate_prototype(system, triples)
    elif name == "multitier":
        populate_multitier(system, triples)
    elif name == "gapaware_prototype":
        populate_prototype(system, triples)
        # Seed gap detection on synthesized text per triple. NOTE: at 20k
        # triples this adds ~20k LLM calls — practically prohibitive on
        # local Gemma. The default loop below excludes gapaware_prototype
        # at this scale; add it explicitly via --only-systems if you have
        # the budget. The wiring is left intact for future runs against
        # faster backends.
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
    name: str, client: LLMClient, scale: int, triples, queries,
) -> SystemAtScale:
    system = _new_system(name, client)
    populate_ms = _populate(name, system, triples)
    sas = SystemAtScale(name=name, scale=scale, populate_ms=populate_ms)
    print(f"  [{name}@{scale}] populated in {populate_ms}ms")

    for q in queries:
        t0 = time.time()
        try:
            answer = system.query(q.question)
            err = None
        except Exception as e:
            answer = f"(error: {str(e)[:160]})"
            err = str(e)[:80]
            sas.error = sas.error or err
        dur = int((time.time() - t0) * 1000)
        ok = score(answer, q, triples)
        sas.results.append(QueryResult(
            qid=q.id, intent=q.intent, answer=answer, correct=ok, duration_ms=dur,
        ))
        mark = "✓" if ok else "✗"
        flag = " [ERR]" if err else ""
        print(f"  [{name}@{scale}] {q.id} ({q.intent}) {mark}{flag} ({dur}ms): {answer[:80]}")
    return sas


def _render(rows: list[SystemAtScale]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        f"# E10-XL — Extreme Scale (10k/20k triples) — results\n",
        f"*Run: {now}*\n",
        f"Scales: {SCALES}. 5 systems. Skipped 50k (clearly past backend limits).\n",
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
        for sc in SCALES:
            sas = next((r for r in by_system[name] if r.scale == sc), None)
            cells.append("—" if sas is None else f"{sas.correct}/{sas.total}")
        lines.append(f"| **{name}** | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Errors observed\n")
    lines.append("| system | scale | errors? |")
    lines.append("|---|---|---|")
    for r in rows:
        lines.append(f"| {r.name} | {r.scale} | {r.error or '—'} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"E10-XL — Extreme Scale Test")
    print(f"     scales: {SCALES}")
    print()

    client = LLMClient()
    all_rows: list[SystemAtScale] = []

    for scale in SCALES:
        print(f"\n=== SCALE: {scale} triples ===")
        triples = make_triples(scale)
        queries = build_queries(triples)
        print(f"  generated {len(triples)} triples, {len(queries)} queries\n")

        # gapaware_prototype intentionally excluded from default loop at this
        # scale (per-triple gap-detection LLM cost is prohibitive at 10k+).
        # Add via --only-systems if you have the budget.
        for name in ("mem0_lite", "zep_lite", "zep_rich",
                     "intent_routed_zep", "prototype", "multitier",
                     "epistemic_prototype"):
            sas = _run_at_scale(name, client, scale, triples, queries)
            all_rows.append(sas)
            print(
                f"  [{name}@{scale}] {sas.correct}/{sas.total}  "
                f"err={sas.error or 'none'}\n"
            )

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    by_system: dict[str, list[SystemAtScale]] = {}
    for r in all_rows:
        by_system.setdefault(r.name, []).append(r)
    for name, runs in by_system.items():
        cells = [f"{r.scale}={r.correct}/{r.total}" for r in runs]
        errs = [f"{r.scale}_err={'Y' if r.error else 'N'}" for r in runs]
        print(f"  {name:20s} " + "  ".join(cells) + "  " + "  ".join(errs))

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{stamp}.md"
    report.write_text(_render(all_rows), encoding="utf-8")
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

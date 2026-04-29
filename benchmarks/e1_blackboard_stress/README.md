# E1 — Blackboard Stress Test

*Minimum viable benchmark for memory architectures under high-velocity state changes. Designed by the research pipeline itself (project 7) as the first experiment needed before claiming architectural winners across Hybrid / Zep / Mem0 / M-Flow.*

## What it measures

**When an entity's state changes many times in rapid succession, which memory architecture still returns the latest value — and at what cost?**

Four systems under test:

| system | write-time LLM | retrieval mechanism | predicted weakness |
|---|---|---|---|
| **hybrid_flat** | none (embed only) | cosine top-k over all chunks | near-identical chunks compete for top-k slots; latest may be missed |
| **hybrid_recency** | none | top-M most recent, then cosine top-k within | tests whether recency-first prior rescues hybrid without paying LLM cost |
| **zep_lite** | 1 extract per doc | latest triple per (entity, attribute) | extraction must be reliable; cost = N LLM calls per stream |
| **mem0_lite** | 1 extract per doc | consolidated (entity, attribute) → value map | same cost as Zep; simpler retrieval; tests consolidation vs accumulation |

Corpus: 3 parallel streams of 20 updates each (60 docs total, interleaved by pub_date) — temperature of User Alice, status of Server Prod-01, lead of Project Nova. Each stream ends on a specific value that is the "current truth" after all updates.

Scoring: **fidelity** — answer must contain the latest value and must NOT contain any superseded value.

## Running it

```bash
cd research-pipeline
uv run python -m benchmarks.e1_blackboard_stress.run
```

Expected runtime with the local vLLM backend: ~5-8 minutes (mostly Zep + Mem0 extractions: 2 × 60 = 120 LLM calls plus the 12 query calls).

Output: `benchmarks/e1_blackboard_stress/results/run_YYYYMMDD_HHMMSS.md`.

## What this benchmark doesn't prove

- Single trial — no variance estimates.
- Substring scoring — an answer like "temperature fluctuated between 98.6 and 99.0" would score 0 even if it's arguably accurate.
- 20 updates per stream — still trivial compared to real blackboard volumes.
- Synthetic text pattern ("{entity}'s {attribute} is {value}") — extraction is unrealistically easy. Real docs have noise.
- Mem0-lite is a simplification of the published Mem0 architecture (no async consolidation, no graph-memory variant).
- M-Flow is not included — the four-level cone + coreference indexing is out of scope for an MVP. The agents' recommended E3 (latency-density scaling) would require it.
- Hybrid variants tested with a single recency_window and top_k. A sweep would show where hybrid_flat's top-k stops being enough.

## Hypotheses being tested (from project 7 synthesis)

- **C1**: Mem0/Zep's LLM extraction causes "semantic smoothing" under frequent writes.
  - Falsified if: Mem0/Zep retrieve the exact latest value with no drift.
- **C3**: Hybrid's top-k retrieval loses precision when many near-identical chunks compete (implicit in the "flat" variant test).
  - Falsified if: hybrid_flat matches hybrid_recency.
- **Implicit**: Recency-first filtering rescues hybrid without write-time LLM cost.
  - Confirmed if: hybrid_recency ≥ zep_lite and hybrid_flat < zep_lite.

## Interpreting results

- **If hybrid_flat loses but hybrid_recency matches zep/mem0**: our architecture's predicted weakness is real AND fixable with a ~10-line retrieval change. No write-time LLM cost needed.
- **If zep_lite and mem0_lite both win fidelity**: write-time extraction is a genuine insurance policy; the LLM cost is the price of guaranteed temporal accuracy.
- **If mem0_lite > zep_lite**: consolidation (overwrite) beats accumulation (triples) for pure "current value" queries.
- **If all four are close**: stream length is too short to stress the systems; rerun with 100+ updates per stream.

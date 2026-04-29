# Agent Memory — What We Decided and Why

*Companion to [agent-memory-benchmarks.md](./agent-memory-benchmarks.md). Converts the empirical findings across E1–E11b into a shortlist for the broader agent-platform memory question (Claude Code, Claude Work, etc).*

> **Boundary note:** product-side decisions for the research-pipeline itself (wiki/blackboard architecture, shipped improvements, etc.) live alongside the source in [`src/research_pipeline/`](../src/research_pipeline/) and the [CHANGELOG](../CHANGELOG.md). This file is purely about the generic agent-memory question that we investigated using the pipeline as a research substrate.

## 1. Findings to share externally (Claude Code / Claude Work teams) — updated through E9

### 1.1 The primary architectural issue (project 8 + E8 + E9, fully grounded)

> **All five existing solutions collapse information at some layer** — at ingest (mem0/Karpathy overwrite), at storage (no history retention), or at query (ZepLite's latest-per-key default). Any collapse at any layer makes historical and cross-entity queries unanswerable. From the user's perspective, lossy storage and lossy query surface are indistinguishable: mem0 and ZepLite tied at 2/6 on E8 and 5/9 on E9.

### 1.2 Minimum viable architecture for correctness (E6 → E9)

**Append-only storage + full-chronological-history query surface.** That's it. ZepRich scored 5/6 on E8 and 9/9 on E9 with no router, no chunks, no TTL. At our benchmark scales (60–400 triples), nothing more complex is needed for correctness.

**Intent routing was empirically refuted as a correctness mechanism.** E8 and E9 tied zep_rich and intent_routed_zep at the same scores with identical answers. The router does nothing on small-to-medium workloads.

### 1.3 Scale-honest production architecture (theoretical, untested)

**The "expose all history" recommendation does NOT scale.** Math:

| corpus | triples | tokens | fits 256K? |
|---|---|---|---|
| E7-XL (124 turns / 16 weeks) | ~300 | ~15K | yes |
| 1 month of Claude Code (~3000 turns) | ~9,000 | ~450K | **no** |
| 1 year | ~100,000 | ~5M | very no |

A user reaches 9,000+ triples within ~6 weeks of active use. Even before hitting the context limit, scanning thousands of triples per query is slow and expensive.

**The honest production architecture is multi-tier:**

| tier | content | query path | purpose |
|---|---|---|---|
| **Hot index** | Latest-per-(entity,attribute) cache | O(1) lookup | Fast path for "what is X currently?" |
| **Append-only triple log** | All `(entity, attribute, value, valid_from, source)` | Filtered scan | Historical and cross-entity queries; substrate of truth |
| **Episode summaries** | LLM-compressed weekly/monthly digests | Vector retrieve summaries first | Compression for cold history |

Same data lives in hot index AND log — the index is materialized, never destructive (this is the key difference from mem0). The router becomes a **cost-management layer**, not a correctness layer — it picks the right tier so the LLM doesn't scan 9,000 triples for a simple "what is X currently?" question.

**Real database parallel:** write-ahead log + materialized view + indexes. Memory systems haven't reached this maturity — most ship one tier and call it the architecture.

### 1.4 Specific anti-patterns to flag

- **Mem0's overwrite-on-update.** Hard ceiling on cross-entity historical queries (E6: 0/3, E8: 2/6, E9: 5/9). Cannot be rescued by any router.
- **Zep's default latest-per-key query** (without rich-history mode). Equivalent in user-visible failure to mem0's overwrite (E8 + E9 both showed mem0 = ZepLite ties). The storage is preserving history but the query layer is collapsing it before the LLM ever sees it.
- **Hybrid_flat (chunks only).** Cosine retrieval cannot do structured temporal reasoning over oscillating values (E8: 1/6; E9: 3/9). Chunk-only memory is unsuitable for agent-platform structured-state tracking.
- **Supermemory's "prefer profile" arbitration prompt.** Causes the chunk fallback to stay dormant when profile is stale (E5). Even with the prompt fixed, cosine retrieval can't surface latest values when many similar chunks compete.

## 2. What we haven't answered (honest open list, post-E11)

| question | experiment needed | priority |
|---|---|---|
| Does intent_routed_zep itself break at 10k-50k triples? | **E10-XL — extreme scale** | high if pursuing innovation |
| Do systems handle open-world state-update queries ("Is X resolved?" when X was raised but no resolution recorded)? | **E11b — open-world status** | medium |
| Does a multi-tier prototype (hot index + log + summaries) match zep_rich on E1–E9 with sublinear cost growth + handle 10k+ triples gracefully? | **Multi-tier prototype** | high |
| Are findings trial-variance artifacts? | 5-trial repeats | low (would confirm not change conclusions) |
| Do gaps reopen at smaller extractor (Haiku-class)? | Re-run with smaller backend | medium |
| Do real commercial SDKs match our Lite reimplementations? | Integration benchmark | medium |

## 3. Recommended next actions (priority order, post-prototype)

1. **(Done — 2026-04-25)** Multi-tier prototype shipped. PrototypeMemory at `benchmarks/e1_blackboard_stress/systems.py` — append-only log + hot index + intent router + programmatic count + open-world prompts. **Strictly Pareto-best on E10/E8/E11/E6**; only system to hit 6/6 on E8. Documented in [agent-memory-prototype.md](./agent-memory-prototype.md).
2. **E10-XL scale-out (10k-50k triples).** Test where the prototype's hot-index advantage becomes decisive. At 50k triples (~2.5M tokens), historical queries exceed 256K context — episode summarization tier becomes necessary.
3. **E11b — open-world state-update test.** Focused follow-up to the E7 q6 pattern that tripped supermemory: events raised but resolution silent. Cheap to build.
4. **Run prototype on E1, E4, E5, E7-XL** to fill in the remaining cells of the comparison matrix. Predicted: matches best-of-class on each.
5. **Ship documentation as-is.** Conclusions are defensibly grounded across 11 experiments at five scales, with a synthesis prototype validated against four discriminating benchmarks.

## 4. My personal architectural take (revised through E10)

**E10 changed the conclusion. My intent-routing proposal was empirically refuted at small scale (E8, E9) and empirically vindicated at production scale (E10).** The full picture:

- **Substrate primacy is real and necessary** at every scale (mem0 / ZepLite cap at 4/7 across all of E10's scales). Append-only storage is non-negotiable.
- **Rich query surface is necessary for correctness on small/medium scale** (ZepRich beats ZepLite by exposing history).
- **Intent routing is necessary for both correctness AND cost at production scale** (E10: at 5000 triples, zep_rich got 6/7 with one query taking 5.4 minutes; intent_routed_zep got 7/7 with current queries in 295ms — 1000× faster).
- **Multi-tier with hot index** is the natural extension. None of the five reference products ships this exact pattern.

The right product looks more like a database than any of the memory products we benchmarked: append-only log of truth + materialized hot index for fast paths + intent router for query dispatch + summary compression for cold data beyond ~10000 triples. Memory systems haven't reached this maturity — they ship one tier and pretend it's the architecture.

**This is now grounded by 10 benchmarks at scales from 10 to 5000 triples.** The multi-tier prototype is the natural next step to validate the full architecture, but the constituent claims have evidence behind them.

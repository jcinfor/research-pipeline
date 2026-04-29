# Agent Memory Benchmark Series (E-series)

*Empirical comparison of six memory architectures against two distinct workloads: our research-pipeline product AND general agent platforms (Claude Code / Claude Work). As-run reference, updated 2026-04-24.*

## 1. Research goal

We are evaluating memory architectures for **two targets**, not one:

1. **Research pipeline** — our own product. Document corpora with sparse contradictions (wiki / narrative) AND attribute-churn on named entities (blackboard state).
2. **General agent platforms** — exemplified by Claude Code and Claude Work. Conversational memory with pronouns, multi-session continuity, granularity spectrum (broad ↔ precise), cross-entity temporal joins, long-horizon forgetting.

Recommendations must be **split by target**. E1 is the right benchmark for research pipeline blackboard; it is the wrong benchmark for agent-platform memory.

## 2. Architectures under test

| short name | pattern | write-time LLM | retrieval | license |
|---|---|---|---|---|
| **HybridFlat** | raw chunks + t_ref, cosine top-k | none (embed only) | cosine KNN, LLM synthesizes answer | our product |
| **HybridRecency** | chunks + global recency window, then cosine top-k | none | recency filter → cosine KNN | our product (variant) |
| **ZepLite** | entity-attribute-value triples with valid_from (accumulating) | 1 extract per doc | latest triple per (entity, attribute) | Zep (conceptual) |
| **Mem0Lite** | extract + consolidate; overwrite on (entity, attribute) | 1 extract per doc | latest value in dict | Mem0 (conceptual) |
| **SupermemoryLite** | consolidated profile + chunks + optional TTL expiry | 1 extract + 1 embed per doc | profile if match; else chunk fallback (cosine) | Supermemory (conceptual) |
| **MFlowLite** | 4-level cone (Entity > Facet > FacetPoint, Episode tags) | 1 extract per doc | navigate cone, latest FacetPoint | M-Flow (conceptual) |

All "Lite" variants are clean-room simplifications for controlled comparison, not reference implementations. Each was written in ~50-150 LOC and shares the same LLM adapter, embedding backend, and prompt style; the architectures differ only in storage and retrieval.

Backend used for live runs: local vLLM (google/gemma-4-26B at spark-dc95:9999) + Ollama qwen3-embedding:0.6b. Fake-LLM tests validate mechanical logic.

## 3. The experiments (E1–E7)

### E1 — Blackboard Stress Test *(built & run 2026-04-24)*

**What:** 3 parallel streams of 20 updates each (60 interleaved docs) covering User Alice's temperature, Server Prod-01's status, Project Nova's lead. Each stream ends on a specific final value.

**What it measures:** when an entity's state changes many times in rapid succession, which architecture returns the latest value, and at what cost?

**Ground truth:** the LAST value in each stream is "current truth"; all earlier values are superseded.

**Scoring:** substring match — answer must contain the final value and must not contain any superseded value.

**Workload regime:** dense per-entity attribute churn. Single-entity queries. No pronouns, no coreference, no cross-entity joins.

**Scope this benchmark does not test:** cross-entity queries, conversational pronouns, granularity-aligned retrieval, active forgetting, noisy extraction.

### E4 — Query-Time Repair *(built & run 2026-04-24; predates E1 in design, kept number from project 6)*

**What:** 10-doc synthetic corpus about Alpha Corp with 3 embedded contradictions (CEO succession Alice→Bob, experiment status in progress→failed, project lead David→Carol). 6 queries split into 3 "current state" and 3 "as-of-historical-date" (temporal).

**What it measures:** whether a memory system correctly returns the current OR historical answer when the corpus contains explicit supersession.

**Scoring:** substring match for correct answer, rejection if superseded answer appears.

**Workload regime:** sparse contradictions over long time spans. Wiki / narrative-style documents.

**Scope this benchmark does not test:** high-velocity churn, cross-entity joins, conversational memory.

### E1-TTL — Cold-Fact Survival under TTL *(built & run 2026-04-24)*

**What:** Alice's `favourite_color=blue` updated once at t=0. Server Prod-01 gets 20 status updates starting 7 days later. Two queries: (1) Alice's favourite_color (expected: blue — never superseded); (2) Prod-01 current status.

**What it measures:** whether supermemory's chunk fallback rescues a cold-but-still-current fact after TTL evicts it from the consolidated profile.

**Motivation:** the agent hypothesis (C5 from project 7) predicted supermemory's TTL would reproduce the `hybrid_recency` catastrophic-forgetting failure — evicting older-but-still-current data when a hot-entity flood dominates.

**Scope this benchmark does not test:** forgetting of data that SHOULD be forgotten (the positive case for TTL).

### E5 — Noisy Extraction *(built & run 2026-04-24)*

**What:** same 60-doc E1 corpus, but a `FaultyLLMClient` wrapper returns empty extraction for the LAST 5 docs of each stream. Chunks (embeddings) are unaffected.

**What it measures:** whether supermemory's chunk fallback rescues fidelity when the extraction layer fails on the most recent docs — the exact case the hybrid design anticipates.

**Motivation:** supermemory's "consolidated profile + chunks in one query" claims to be a strict superset of mem0. E5 tests whether that claim holds under extraction degradation.

**Scope this benchmark does not test:** random (non-tail) extraction failures, misextractions (wrong value extracted vs. no value extracted).

### E6 — Cross-Entity Temporal Correlation *(proposed, not yet built)*

**What:** same 60-doc E1 corpus, but queries are cross-entity. Example: "What was Prod-01's status when Alice's temperature peaked at 101.5?" (answer requires finding Alice's peak timestamp, then looking up Prod-01's status AT that timestamp).

**What it measures:** whether m-flow's graph-path retrieval — traversing from one Entity's FacetPoint to another Entity's FacetPoints at matching timestamps — outperforms flat mem0/supermemory that lack cross-entity indexing.

**Predicted outcome:** m-flow ≥ zep > supermemory > mem0 ≈ 0/N. Mem0's overwriting consolidation DESTROYS the history needed to find "when Alice's temp peaked." Zep's valid_from chain preserves history and can do it in two LLM steps. M-flow does it in one graph traversal.

**Scope this benchmark does not test:** pronouns / coreference (that's E7).

### E7 — Conversational Memory Stress *(proposed, building next)*

**What:** a multi-session dialog (~50 turns across simulated sessions) with:
- **Pronouns requiring resolution** — "she said...", "the bug we found", "that file"
- **Cross-session references** — "what did we decide last week?", "where did we leave off?"
- **Granularity spectrum** — broad ("summarize our collaboration on auth") AND specific ("what was the exact error at 3pm Tuesday?")
- **Evolving user preferences** — user changes their mind about a design choice; asks later for their CURRENT preference

**What it measures:** exactly the Claude Code / Claude Work workload. Whether m-flow's coreference pre-indexing + cone granularity + supermemory's TTL for preference versioning provide measurable wins over mem0's flat consolidation and zep's triple history on **conversational** memory.

**Scoring:** substring + LLM-judge on broad-summary queries where substring is too strict.

**Why this is the hinge experiment for the platform thesis:** all prior experiments are document- or attribute-oriented. E7 is the first that matches the real agent-platform workload. If m-flow / supermemory don't win here, they don't win anywhere for this target. If they do, we have evidence for adopting the cone + TTL + chunk-fallback pattern for Claude-Code-style memory.

## 4. Findings to date

### 4.1 E4 (2026-04-24, 10 docs, 6 queries)

| system | current (3) | temporal (3) | overall | ingest | avg query |
|---|---|---|---|---|---|
| karpathy_lite | 3/3 | 1/3 | 4/6 | 16.5s | 494ms |
| **zep_lite** | 3/3 | 3/3 | **6/6** | 20.1s | 222ms |
| hybrid_flat | 3/3 | 2/3 | 5/6 (scoring artifact) | **2.6s** | 940ms |

**Takeaways:**
- Zep wins on raw correctness, hybrid wins on cost (8× cheaper writes).
- Hybrid's one miss was a scoring edge: semantically correct answer contained both correct and superseded entity names.
- Karpathy confirms "no temporal awareness" design limit — refuses temporal queries gracefully rather than hallucinating.

### 4.2 E1 (2026-04-24, 60 interleaved docs, 3 streams)

| system | fidelity | ingest | write LLM | differentiator |
|---|---|---|---|---|
| hybrid_flat | 1/3 | 11s | 0 | cheapest; loses latest under churn |
| hybrid_recency | 0/3 | 7s | 0 | global recency evicts cold entity data |
| zep_lite | 3/3 | 91s | 60 | verbose triples schema 2× cost |
| mem0_lite | 3/3 | **44s** | 60 | cost floor for extraction-based |
| supermemory_lite | 3/3 | 53s | 60 | +embed for chunk fallback |
| m_flow_lite | 3/3 | **44s** | 60 | cone's extra storage doesn't hurt cost |

**Takeaways:**
- Fidelity is binary on E1: either you extract+consolidate (3/3) or you rely on chunk retrieval (0-1/3).
- Among extraction-based systems, cost is the tie-breaker: mem0 & m-flow at the floor (44s), zep 2× due to verbose schema.
- Our hybrid is **unsafe for per-entity high-velocity updates**. Simple recency reranking made it WORSE because global recency evicts older-but-still-current entity data on multi-entity interleaved streams.

### 4.3 E1-TTL (2026-04-24, 21 docs)

| system | Q_cold (blue) | Q_hot (green) | total |
|---|---|---|---|
| mem0_lite (no TTL) | ✓ | ✓ | 2/2 |
| supermem_ttl=none | ✓ | ✓ | 2/2 |
| **supermem_ttl=1h** | **✓** | ✓ | **2/2** |
| supermem_ttl=30d | ✓ | ✓ | 2/2 |

**Takeaways:**
- Chunk fallback rescues Alice's 7-day-old fact even when TTL evicts it from the profile.
- Architectural reason: chunk retrieval is attribute-aware (cosine matches "favourite_color"). `hybrid_recency`'s failure was due to a GLOBAL recency window, not recency per se.
- **Falsifies agent hypothesis C5** (TTL reproduces catastrophic forgetting in interleaved streams).

### 4.4 E5 (2026-04-24, 60 docs with tail-extraction failures)

| system | fidelity | notes |
|---|---|---|
| hybrid_flat | 1/3 | baseline, chunks unaffected |
| mem0_lite | 1/3 | Alice by coincidence (doc-14 value = doc-19 value) |
| **supermemory_lite** | **1/3** | IDENTICAL answers to mem0 — chunk fallback DORMANT |

**Takeaway — the root cause is NOT the arbitration prompt:**
- Initial reading (2026-04-24 first run): supermemory's `"Prefer the PROFILE if it directly answers"` prompt blocked the chunk fallback from firing.
- **Re-run 2026-04-24 with revised `"prefer MOST RECENT across both"` prompt: still 1/3.** Answers changed (Prod-01 rescued to ✓ green, Alice regressed to ✗ 98.7), but the overall fidelity didn't improve.
- **True root cause:** cosine top-k over 20 near-identical chunks misses the most-recent chunk — the same failure that broke `hybrid_flat`. Supermemory's chunk fallback inherits this weakness because its retrieval is cosine-only.
- **To actually rescue E5**, supermemory would need recency-weighted cosine OR per-entity chunk partitioning — architectural changes, not prompt edits.
- **The chunk fallback does rescue E1-TTL** (cold-fact preservation when profile is empty) because there only ONE chunk matches the attribute — cosine can't miss what has no competitors. On dense-churn E5 with 20 chunks per attribute competing, cosine recency-blindness wins.

### 4.5 E7 (2026-04-24, 23-turn multi-session auth-refactor dialog)

| system | pronoun (2) | cross_session (1) | preference_evolution (1) | granularity_precise (1) | forgetting (1) | overall |
|---|---|---|---|---|---|---|
| hybrid_flat | 2/2 | 0/1 | 1/1 | 0/1 | 1/1 | 4/6 |
| **zep_lite** | **2/2** | **1/1** | **1/1** | **1/1** | **1/1** | **6/6** |
| mem0_lite | 1/2 | 1/1 | 0/1 | 1/1 | 1/1 | 4/6 |
| supermemory_lite | 2/2 | 1/1 | 1/1 | 1/1 | 0/1 | 5/6 |
| m_flow_lite | 1/2 | 1/1 | 1/1 | 1/1 | 1/1 | 5/6 |

Ingest times: hybrid 5s, zep 27s, mem0 25s, supermemory 25s, m-flow 21s.

**Takeaways — this overturned my architectural prediction:**
- **Zep wins 6/6** on conversational workload. My pre-run prediction had m-flow/supermemory leading; the data said otherwise.
- Why zep wins: conversations discuss MULTIPLE aspects of the same entity (Alice's role, Alice's bug, Alice's suggestion). Zep's accumulating triples-with-valid_from preserve all of it; mem0's overwrite loses the later context.
- **mem0's specific failure** on q3 (`"mutex or event-queue"` — includes the intermediate preference): overwrite semantics lost the sequential ordering of the user's preference flip-then-revert.
- **m-flow's specific failure** on q2 (`"the mutex approach"` — wrong Facet): the cone surfaced multiple attribute-Facets for Alice (her concern, her suggestion, her team). The LLM picked the wrong one. The architectural strength (rich structure) became a weakness (disambiguation burden).
- **supermemory's specific failure** on q6 (`"no"` instead of `"unknown"`): the profile+chunks prompt preferred answering over deferring. This is the same class of issue as E5's "prefer profile even when stale" — arbitration prompt matters.
- **Zep's cost premium shrinks on conversation**: 27s for 23 turns (~1.2s/turn) vs 91s for 60 E1 docs (~1.5s/turn). Per-turn extraction is cheap when turns are short.

### 4.6 E7-long (2026-04-24, 73 turns across 8 weeks, 10 queries)

Extending E7's auth-refactor storyline into 8 weekly sessions with additional threads (CI infrastructure, passkey rollout, Alice's team transfer, Frank's flaky-test triage).

| system | overall | ingest | architecturally-meaningful failure |
|---|---|---|---|
| hybrid_flat | 7/10 | 12s | cosine top-k misses decision-point turns at scale (q3, q8) |
| zep_lite | 9/10 | 110s | none (q6 was a scoring substring edge) |
| mem0_lite | 9/10 | 96s | **q8 overwrite failure**: newer "approach" fact (passkey) evicted earlier "mutex" — real architectural bug |
| supermemory_lite | 9/10 | 108s | none (q10 was a scoring edge) |
| m_flow_lite | 9/10 | 95s | none (q6 was a scoring substring edge) |

**Takeaways — my predictions were mostly wrong, and zep's E7 win was partly regime-specific:**
- **Four extraction-based systems converged to 9/10 at 73 turns.** E7's zep-dominates pattern does NOT hold at scale.
- **Zep's context-length concern didn't manifest on 26B Gemma (google/gemma-4-26B via vLLM at spark-dc95) at 73 turns.** ~100 triples fit in context cleanly.
- **Mem0's overwrite bug DID manifest** on q8 — when "approach" as an attribute is reused across threads (refresh approach vs passkey binding approach), the latest value evicts the earlier. This matches the predicted weakness but on a different query pattern than E7 showed.
- **Hybrid improved to 7/10** — scale helped because more diverse facts means cosine retrieval has more to work with on easier queries; still loses on the decision-point queries (q3, q8).
- **Ingest cost spread narrowed at scale**: zep 110s, supermemory 108s, mem0 96s, m-flow 95s. Hybrid still 12s (no extraction).

**Revised conclusion for the agent-platform goal:**
- **Zep is no longer the clear winner.** At 73 turns, any extraction-based system reaches 9/10.
- **Mem0 has a real architectural failure mode** (cross-thread attribute-key collision) that will only grow at 200+ turns.
- **M-flow or supermemory look best positioned for scale** — both 9/10 here, slightly cheaper than zep, and both have untested structural capacity (cone for m-flow, chunks for supermemory) that should help on still-harder queries.
- **Not yet tested:** 200+ turn scale (E7-XL), cross-entity temporal (E6), multi-user isolation. The pick among m-flow vs supermemory depends on those.

### 4.7 E6 (2026-04-24, 30 docs across 3 overlapping 10-step streams)

Scenario: Alice's temperature, Prod-01's status, Nova's lead all updated at each of 10 timesteps. Queries test cross-entity temporal joins ("what was X when Y had value Z?").

**First-pass result (Lite variants only):** ALL 4 extraction systems scored **0/3 on cross-entity queries**. Hybrid got 1/3 by cosine luck. This surfaced a design flaw in my Lite implementations.

**Root cause:** zep_lite and m_flow_lite both STORE full history (triples with valid_from; FacetPoints with timestamps) but their query() methods COLLAPSE to latest-per-key at retrieval. The LLM never sees the history the storage preserves.

**Second pass — added ZepRich and MFlowRich** (same storage, query layer exposes full chronological history):

| system | cross-entity | controls | overall |
|---|---|---|---|
| hybrid_flat | 1/3 | 2/2 | 3/5 |
| zep_lite (collapsed query) | 0/3 | 2/2 | 2/5 |
| **zep_rich** | **2/3** | 2/2 | **4/5** |
| mem0_lite | 0/3 | 2/2 | 2/5 |
| supermemory_lite | 0/3 | 2/2 | 2/5 |
| m_flow_lite (collapsed query) | 0/3 | 1/2 | 1/5 |
| **m_flow_rich** | **2/3** | 2/2 | **4/5** |

**Takeaways:**
- **Zep and M-Flow can handle cross-entity reasoning when the query surface exposes history.** 2/3 isn't 3/3 — the missed q3 was query-wording ambiguity ("first exceeded 100"), not architecture.
- **Mem0's 0/3 is a hard architectural ceiling.** Its STORAGE has no history; no query surface can recover what was never kept.
- **Supermemory's chunk fallback didn't rescue at cosine-only retrieval.** Would need explicit temporal retrieval (chunks near timestamp T) — a richer retrieval strategy.
- **Real commercial Zep and M-Flow likely default to rich query surfaces;** my Lite collapse was an artifact of MVP simplicity. E6 first-pass "all fail" result should NOT be cited as evidence against those products — it's evidence my implementations were too lite.
- **Practical implication for Claude Code / Work:** if cross-session queries like "what was I working on when Alice pinged me?" matter, mem0 is structurally incapable. Zep-style triples with rich query are the minimum viable architecture.

### 4.8 What we have NOT yet tested

- **E7-XL** — 200-500 turns. Does mem0's overwrite-collision rate grow linearly with distinct entity-attribute pairs? Does zep's context cost start biting? Does supermemory's chunk fallback become more valuable as profile ambiguity grows?
- **Real commercial SDKs** — our "Lite" variants are 50-150 LOC each. Real mem0 / zep / supermemory / m-flow may behave differently.
- **Retrieval-side temporal filtering for supermemory** — adding "retrieve chunks near timestamp T" to supermemory's query path should let it handle cross-entity queries. Not yet tested.

## 5. Recommendations

### 5.1 For our research pipeline (evidence-backed)

- **Blackboard state (frequent attribute updates):** adopt the **mem0 pattern** — extract + consolidate with overwrite. Cheapest ingest (44s/60 docs), 3/3 on E1. Our current hybrid is unsafe here.
- **Per-user wiki (narrative / document):** keep our current **Karpathy+Zep hybrid**. E4 confirmed 5/6 at 8× cheaper writes than zep.
- **Optional upgrade for blackboard:** layer supermemory-style chunk fallback ON TOP of mem0 only if you want insurance against noisy extraction. Requires recency-aware arbitration prompt (E5 lesson). +20% ingest time, no E1 fidelity benefit, confirmed E1-TTL benefit for cold-attribute survival.

### 5.2 For agent platforms (Claude Code / Claude Work) — E7 + E7-long grounded

**At 23 turns (E7):** zep wins 6/6, mem0 fails at 4/6 due to preference-flip overwrite.

**At 73 turns (E7-long):** four extraction-based systems converge at 9/10. Cost spread is the differentiator.

- **Zep's clear lead was partly regime-specific.** At 73 turns, mem0/supermemory/m-flow catch up. The "temporal triple accumulation wins conversations" hypothesis is partially refuted: it wins at short conversation scale where mem0's overwrite bites; at longer scale the overwrite failures are rarer per query and the gap closes.
- **Mem0 still has a real architectural failure mode:** q8 on E7-long — cross-thread attribute-key collision (the "approach" attribute was reused for refresh and passkey, newer evicted older). Expected to grow with scale.
- **Revised pick: m-flow or supermemory** — both 9/10 at 73 turns, ~14% cheaper than zep (95s vs 110s), no overwrite failures. Pick m-flow if you want graph-path retrieval for cross-entity queries; pick supermemory if you want chunk fallback for cold-attribute insurance.
- **Caveats:** 73 turns is still short vs real Claude Code 100-500. Single trial. 26B Gemma (google/gemma-4-26B via vLLM at spark-dc95). The choice between m-flow and supermemory needs E6 (cross-entity) or E7-XL (longer scale) to separate.

### 5.3 What we do NOT recommend

- **Don't extrapolate E1 results to agent-platform memory.** E1's single-entity structured queries are the WORST possible test for m-flow and supermemory's claimed differentiators.
- **Don't ship a single architecture for all workloads.** The research-pipeline and agent-platform targets are different problems.

## 6. Reproducing the benchmarks

Each benchmark lives under `benchmarks/e*/` with corpus, systems, run.py, README, and result reports. All are driven by the same `LLMClient` adapter; swap backends via `~/.research-pipeline/models.toml`.

```bash
cd research-pipeline
uv run python -m benchmarks.e4_query_time_repair.run
uv run python -m benchmarks.e1_blackboard_stress.run
uv run python -m benchmarks.e1_ttl.run
uv run python -m benchmarks.e5_noisy_extraction.run
# E6 — not built
# E7 — building next
```

Tests: `uv run pytest tests/test_e4_benchmark.py tests/test_e1_stress.py` (30 tests, all fake-LLM mechanical logic).

## 7. Honest caveats

- Single trial per experiment. No variance estimates.
- Substring scoring. An answer like "Alice was at 101.5°F which caused concern before recovering to 99.0" scores 0 even if factually accurate.
- Local 26B Gemma (frontier-scale). Extraction reliability at this scale is strong — likely partly responsible for E7-long's 9/10 convergence across architectures. On a smaller extractor, architectural differences might be more pronounced.
- "Lite" reimplementations, not the real products. Real mem0 has async consolidation; real supermemory likely has smarter arbitration than my MVP; real m-flow has full coreference + face-recognition partitioning.
- 60-120 docs per experiment. Real blackboards and real conversations are 10-1000× larger.

**None of this is a serious benchmark.** It is a minimum viable empirical comparison that replaces "we haven't measured anything" with "we have 4 data points on 4 axes for our workload and 0 data points for the platform workload — E7 is next."
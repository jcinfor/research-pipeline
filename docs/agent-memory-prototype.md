# PrototypeMemory — synthesis of E1-E11 learnings

*An evidence-grounded reference architecture for agent memory, synthesizing the failure modes E1–E11 surfaced across every existing pattern. Lives at `benchmarks/e1_blackboard_stress/systems.py:PrototypeMemory` so it can be benchmarked alongside the conceptual re-implementations of mem0 / zep / m-flow / supermemory. NOT part of the research-pipeline product; this is generic agent-memory research.*

## 1. What the benchmark series proved

| finding | evidence | what it implies for the prototype |
|---|---|---|
| Substrate primacy | E6, E8, E9, E10: mem0/zep_lite/m_flow_lite tied at architectural ceilings | Storage MUST be append-only — never overwrite |
| Query-collapse equivalence | E8: mem0 = ZepLite = 2/6; E10: same three tied at 4/7 every scale | Query layer must expose history when needed; collapsing latest-per-key at the layer is the same failure as overwriting at storage |
| Routing pays only at scale | E8/E9: routing = no benefit; E10@5000: routing = 1000× latency win + correctness rescue | Need an intent classifier, but only worth it once corpus exceeds ~500 triples |
| Hierarchy is a liability at scale | E10: m_flow_rich went 7/7 → 4/7 as cone hierarchy confused LLM | Use flat triple lists, not nested entity > facet > facetpoints |
| LLMs can't count | E8 q3: zep_rich said 16, intent_routed said 17 (true: 19) | Count queries must be programmatic, not LLM-arithmetic |
| Prompt arbitration matters | E5, E7: supermemory's "prefer profile" prompt blocked rescue from chunks | Open-world prompts: explicit "if not in table, say so" instructions |
| Closed-world absence is fine | E11: 7/7 systems 10/10 | No special architectural support needed for "what is X's salary?" when X has no salary record |
| Cross-entity needs full history + alignment | E6: rich variants beat lite; collapsed query loses the join | Cross-entity queries must expose chronological triples and instruct LLM to align timestamps |

## 2. Architecture

```
                     ┌──────────────────────────────────────┐
                     │  Append-only triple log              │
                     │  (entity, attribute, value,           │
                     │   valid_from, source_doc)             │
                     │  Never overwrite. Substrate of truth. │
                     └────────────┬─────────────────────────┘
                                  │
                  ┌───────────────┴────────────────┐
                  │                                │
       ┌──────────▼──────────┐         ┌──────────▼──────────┐
       │  Hot index           │         │  (future tier:       │
       │  latest-per-(e,a)    │         │   episode summaries  │
       │  Materialized,       │         │   for cold history,  │
       │  non-destructive.    │         │   needed >10k triples)│
       │  O(1) lookup.        │         └──────────────────────┘
       └─────────┬────────────┘
                 │
   ┌─────────────▼─────────────────────────────────────────┐
   │                 Query intent router                    │
   │  Keyword pre-routing (count / cross_entity)            │
   │   → bypass LLM classifier on unambiguous signals       │
   │  LLM classifier fallback for ambiguous cases           │
   └──┬───────┬───────┬──────────┬────────────┬─────────────┘
      │       │       │          │            │
      ▼       ▼       ▼          ▼            ▼
   current  hist.  cross-     count       current
   query    query  entity     handler     w/ context
      │       │       │          │            │
      │       │       │      programmatic    │
      │       │       │      filter +        │
      │       │       │      regex word-     │
      │       │       │      boundary match  │
      │       │       │      (NO LLM         │
      │       │       │      arithmetic)     │
      ▼       ▼       ▼          ▼            ▼
   Hot    Full   Full triples  Direct     Hot index +
   index  log    + alignment   integer    last K recent
   only   exposed instructions answer      triples
   ──────────────────────────────────────────────────────
   All paths use OPEN-WORLD prompts:
     "If queried entity/attribute not present, say 'no record' / 'unknown'.
      Do NOT fabricate."
```

## 3. Benchmark scoreboard (full E1-E11b + E10-XL coverage)

| benchmark | prototype | best of others | notes |
|---|---|---|---|
| E1 blackboard stress | 3/3 | 3/3 (4-way tie) | matches extraction-based ceiling |
| E4 wiki temporal | 5/6 | 6/6 (zep_lite) | one substring scoring miss; lost to zep_lite's full-triple temporal handling |
| E5 noisy extraction | 1/3 | 1/3 (universal ceiling) | no system rescues tail-failure extraction |
| E6 cross-entity | 4/5 | 4/5 (zep_rich, m_flow_rich) | tied; one wording-ambiguity miss |
| E7-XL conversation | 10/12 | 11/12 (3 systems) | behind hybrid_flat / zep_rich / mem0_lite |
| **E8 non-monotonic** | **6/6 ✓** | 5/6 (others) | **only winner** — programmatic count |
| E10 @ scale 5000 | 7/7 | 7/7 (intent_routed_zep) | tied |
| **E10-XL @ 10k/20k** | **4/7** | 5/7 (mem0/zep_lite at 10k) | not first but **only system with hot index that doesn't crash** at 20k |
| E11 closed-world absence | 10/10 | 10/10 (most) | universal sweep |
| **E11b open-world status** | **10/10 ✓** | 10/10 (zep_rich, m_flow_rich) | **3-point lead over intent_routed_zep** thanks to open-world prompts |

**Pareto-mixed.** Not strictly best on every benchmark — E4 favors zep_lite's full-triple temporal handling, E7-XL favors simpler systems on the specific query mix. But the prototype is the only system that:
- Hits 6/6 on E8 (programmatic count)
- Hits 10/10 on E11b (open-world prompts) without zep_rich's 0/7 collapse at scale
- Provides current-query latency in 200-600ms at 20k triples while zep_rich completely crashes

## 4. The two non-obvious bug fixes that mattered

Both surfaced in the first prototype run and were fixed before the final sweep:

### 4.1 Keyword pre-routing for count queries
First E8 run: prototype scored 5/6 because the LLM intent classifier mis-routed "how many times was Alice on project C?" to `historical` instead of `count`. The historical path then asked the LLM to count, which produced "60" (wrong).

Fix: keyword-based fast-path bypasses the LLM classifier on unambiguous signals (`how many times`, `how often`, `count of`, etc.). The classifier remains for ambiguous queries.

### 4.2 Word-boundary matching in count handler
After fixing pre-routing, the count handler still produced "60" because criterion `"C"` substring-matched every value (E8 docs had values like "project A", "project B", "project C" — all contain `c` inside the word "project").

Fix: regex word-boundary match (`\bC\b`) instead of substring `in`. Now `"C"` matches the word C in `"project C"` but not the `c` inside `"project"`.

Both fixes are tiny (5-10 LOC each) but the difference between 5/6 and 6/6 on E8.

## 5. What the prototype does NOT include (and what E10-XL proved is missing)

### 5.1 Episode summarization — empirically validated as the missing tier
**E10-XL at 10k+ triples revealed the prototype's hard ceiling on historical queries.** ALL "expose all triples" approaches (zep_rich, intent_routed_zep historical path, prototype historical path) hit HTTP 400 context overflow. zep_rich crashes completely (0/7); the prototype gracefully degrades on historical queries while keeping current/cross-attribute queries fast (4/7).

The fix is **episode summarization**: at write time, periodically compress cohorts of related triples into LLM-generated digests; at query time, retrieve the digest first and only drill into the raw triple log when the digest doesn't suffice. This is the architectural component the prototype currently lacks. E10-XL is the empirical case for adding it.

### 5.2 Other deliberate non-goals
- **Distributed storage / sharding.** Out of scope; this is a memory architecture, not a database.
- **Real-time / streaming consolidation** (mem0's async approach). Our benchmarks run in batch; streaming is an orthogonal concern.
- **Embeddings / cosine retrieval.** Hybrid_flat showed cosine doesn't help on structured temporal queries (E1: 1/3, E6: 1/5, E8: 1/6). Could be added later for "find entries semantically similar to X" queries, but not for the temporal/structured workload tested here.
- **Multi-user isolation.** Untested; would need a separate per-user partition layer.
- **Tail-failure extraction recovery.** E5 showed every system caps at 1/3 when the LLM extraction fails on the most-recent docs. Would need either chunk fallback + recency-aware retrieval, or extraction-failure detection + retry logic.

## 6. Code map

| component | location | purpose |
|---|---|---|
| `PrototypeMemory.triples` | `benchmarks/e1_blackboard_stress/systems.py` | Append-only log; substrate of truth |
| `PrototypeMemory.hot_index` | (same) | Materialized latest-per-key, O(1) lookup |
| `_classify_intent` + `_COUNT_KEYWORDS` + `_CROSS_ENTITY_KEYWORDS` | (same) | Hybrid keyword + LLM intent router |
| `_current_query` / `_historical_query` / `_cross_entity_query` / `_count_query` / `_current_with_context_query` | (same) | Five intent-dispatched query paths |
| `_PROTOTYPE_*_QUERY_SYSTEM` constants | (same) | Open-world-aware prompts |
| Tests | `tests/test_prototype_memory.py` | 13 mechanical tests covering storage, routing, count fixes, prompt invariants |

## 7. How to use

```python
from benchmarks.e1_blackboard_stress.systems import PrototypeMemory
from research_pipeline.adapter import LLMClient

mem = PrototypeMemory(LLMClient())

# Write — either via Doc-based ingest (LLM extraction) or direct add_triple
mem.ingest(some_doc)
mem.add_triple(entity="Alice", attribute="role", value="lead",
               valid_from="2026-04-25T10:00:00", source_doc="conv_001")

# Read — intent automatically routed
mem.query("What is Alice's current role?")        # → hot index
mem.query("What was Alice's first observed role?") # → historical
mem.query("How many times was Alice in 'lead'?")  # → programmatic count
mem.query("What was Alice when Bob was reviewer?") # → cross-entity
```

## 8. What this prototype IS and IS NOT

**It is:** an evidence-grounded reference architecture that synthesizes the lessons from E1-E11. Every component traces back to a specific benchmark finding.

**It is not:** a production memory system. Real systems would need: persistent storage (currently in-memory), concurrent-write safety, multi-user isolation, larger-scale handling (episode summaries beyond 10k triples), embedding-backed semantic search alongside the structured triples, and so on.

**It is also not:** part of the research-pipeline product. The product has a different architecture (kind-typed blackboard + Karpathy+Zep wiki — see `agent-memory-architecture.md`) suited to its specific workload (50-200 entries per project, append-only by nature). The prototype lives in `benchmarks/` as generic agent-memory research, separate from the product.

## 9. What's still open

- **Phase B optimization roadmap** — extraction-quality + retrieval gaps surfaced by LoCoMo §7.1 (n=11 disagreements) + LongMemEval §7.2 (n=11 disagreements). Concrete prompt/context-engineering work targeting prototype 57% → ~70% on LongMemEval temporal-reasoning is tracked separately as Phase B follow-up; the relevant comparator on temporal-reasoning under the current taxonomy is `mem0_real_v3` (mainline + full nlp), which currently leads at 34/54 (63%) vs prototype's 31/54 (57%) on the canonical n=100 oracle run.
- **(Empirically grounded — needs implementation)** Episode summarization tier. E10-XL at 10k+ triples crashed zep_rich (0/7) and capped the prototype at 4/7 due to context overflow on historical queries. Adding LLM-generated digests of triple cohorts + retrieval over digests would extend the architecture past this ceiling.
- **E7-XL revealed prototype slightly trails simpler systems (10/12 vs 11/12 leaders)** on conversational workload. The two losses are scoring artifacts, not architectural failures. But it does mean prototype isn't strictly Pareto-best on every workload.
- **Smaller extractor model** — at Haiku-class or smaller, the intent classifier and criteria extractor will be less reliable. The keyword pre-routing already hardens against the most common misclassification; more fallbacks may be needed.
- **Tail-failure extraction recovery** (E5: universal 1/3 ceiling) — orthogonal to the architecture; needs extraction-quality monitoring and retry logic. Partly addressed by Phase B §2.1 (robust JSON-parse + retry) above.

# Agent-memory prototype — innovation directions

*Two prototype variants designed as architectural experiments, not benchmark patches. Aim: depart from the "ingest → store → retrieve → synthesize" template that every existing memory system (mem0, zep, supermemory, m_flow, our own PrototypeMemory) currently shares.*

## What every existing memory system shares (and why patches won't break out of it)

mem0, zep, supermemory, m_flow, our `PrototypeMemory` and `MultiTierMemory` — different storage units (chunks, triples, episodes, graphs) but **the architecture is identical**:

1. Memory is *passive storage* queried at answer-time.
2. Memory's job is to *recall what was said* — not to reason about what wasn't said, what's contradicted, or what should come next.
3. Nothing happens between ingest and query. There is no "memory process" — only a memory store.

Patches like "add a description field," "add cosine retrieval," "add an aggregation prompt path" sharpen the same axe. They move LongMemEval scores up but don't change what kind of object the memory is.

## Three innovation directions (from earlier analysis)

1. **Memory that reasons about its own gaps.** When ingesting "user has a Honda Civic," note the unknowns: year, mileage, prior owner. Future agent turns get a "known unknowns" panel. Retrieval becomes bidirectional — recall + interrogate.

2. **Epistemic-state memory.** Every fact carries lineage and conviction. `(claim, source, support, contradicted_by, conviction, last_revisited)`. Conviction updates as evidence arrives. Retrieval can return *contradicting bundles* (case for X; case against), the natural shape of scientific reasoning. Today's lifecycle (`proposed → supported → refuted`) gestures at this but flattens to one state.

3. **Memory as a scheduled process.** Between agent turns, a consolidation tick runs: cluster near-duplicate claims, surface contradictions, identify under-explored corners, write conclusions back as new claims (machine-derived). The next round of agents sees things no agent stated explicitly. Closest analogue to biological memory consolidation.

## The two variants we're building

### Variant A — `EpistemicPrototype` (idea 2)

**The architectural change:** `PrototypeMemory` keeps a single "latest" value per `(entity, attribute)` via the hot index — earlier observations are preserved in the append-only log but never surfaced at query time. `EpistemicPrototype` opens up the value space: every value ever observed for a given key is kept as an `EpistemicClaim` with its own conviction trajectory.

**Data model:**

```python
@dataclass
class EpistemicClaim:
    entity: str
    attribute: str
    value: str
    sources: list[str]            # source_doc ids supporting this value
    seen_count: int               # times this exact (e, a, v) has been ingested
    conviction: float             # 0.0–1.0
    first_seen_at: str
    last_seen_at: str
    history: list[dict]           # [{action, source, valid_from}, ...]

# claims[(entity_lower, attr_lower)] = list[EpistemicClaim]
```

**Conviction rules (deliberately simple, no LLM):**

- Same `(e, a, v)` re-ingested → existing claim's `conviction += 0.1` (capped at 1.0), `seen_count += 1`, source appended.
- New `v` for existing `(e, a)` → new claim at `conviction = 0.5`, *peer to* existing claims (no overwrite).
- Explicit refutation (future work, would require LLM at query time) → `conviction -= 0.2`.

**Query change:** when `_current_query` looks up keys relevant to the question, it surfaces the full multi-claim picture, not just the latest. Prompt shape:

```
(user, car_model):
  ▸ "Honda Civic" [conviction 0.8, 4 mention(s)]
    competing: "Toyota Camry" [conviction 0.5, 1 mention(s)]
```

The answer-LLM is told: high-conviction wins unless the question explicitly asks for contested or older values.

**What this enables that no existing system does:**

- Returns *contradicting bundles*, not single answers. Useful for any agent that has to reason about disagreement.
- Conviction is a measurable signal that grows over time — agents can ask "what am I most confident about?"
- The trajectory isn't lost when a new observation arrives, so questions like "did the user ever say X?" remain answerable.

**What this is NOT:** it is not "store the description field," not "add a confidence threshold," not "rerank by recency." Those are patches. Conviction is a *first-class storage primitive* that changes what retrieval can return.

### Variant B — `GapAwarePrototype` (ideas 1 + 3)

**The architectural change:** `PrototypeMemory` knows what it knows. `GapAwarePrototype` also knows *what it doesn't know but should*. After each ingest, an LLM identifies unknowns raised by the doc — facts that are mentioned but not specified — and stores them as `Gap` entries. A consolidation tick runs periodically and writes derived conclusions back into the store.

**Data model:**

```python
@dataclass
class Gap:
    question: str             # natural-language form ("What year is the user's Civic?")
    related_entity: str       # the entity the gap is about
    related_attribute: str    # the missing attribute
    introduced_at: str        # source_doc that triggered the detection
    resolved_by: str | None   # source_doc that filled the gap (None = open)
    resolved_value: str | None
```

**Ingest pipeline change (extends parent's):**

1. Parent's extraction runs as usual, populating triples + hot_index.
2. **New:** check open gaps — if a new triple matches an open gap's `(entity, attribute)`, mark it resolved.
3. **New:** call LLM to identify 0–5 specific unknowns raised by this doc. Store as `Gap` entries.
4. **Periodic (every K ingests):** consolidation tick — cluster near-duplicate triples, surface contradictions (same `(e, a)` with conflicting values within a short window), and write the contradictions as a special record.

**Query change:** `_current_query` injects an extra `KNOWN UNKNOWNS` panel into the LLM prompt for any gaps relevant to the question's entities. The LLM is told to honestly say "no record of X" when the question maps to a known unknown — *abstention becomes principled rather than defensive*.

**What this enables that no existing system does:**

- The agent can answer "what should I clarify with the user?" — that's a query the memory was built to answer, not just a side effect of retrieval failing.
- Hallucination has a brake: if the question targets a known unknown, the system has explicit evidence not to make up an answer.
- Consolidation between turns means the next agent can see things derived from prior agents' observations even when no individual agent said them.

**What this is NOT:** it is not "increase the retrieval threshold," not "add a 'no info' classifier prompt." Those make the synthesizer more cautious. This makes the memory itself *aware of its own coverage*.

## Where they fit in the stack

Both are lean subclasses of `PrototypeMemory` (in [benchmarks/e1_blackboard_stress/systems.py](../benchmarks/e1_blackboard_stress/systems.py)):

- Reuse the parent's extraction pipeline, intent classifier, chunk-fallback retrieval, embedding cache.
- Override only the storage primitive (`_maintain_hot_index`) and the read path (`_current_query`) where the innovation lives.
- Register in [benchmarks/longmemeval/run.py](../benchmarks/longmemeval/run.py) `_new_system` so they're testable via `--only-systems epistemic_prototype` / `--only-systems gapaware_prototype`.

This way the benchmark plumbing doesn't need to change, and we can A/B them against the base `PrototypeMemory` on the same haystack.

## What we're explicitly NOT doing

- **No description-field hybrid.** That's a patch, well-understood, easy to add later if measurements justify it. We want to know if the architectural change carries weight on its own.
- **No frontier-LLM swap.** Local Gemma 4 26B for everything. Comparing variants on the same backbone makes the architectural difference visible.
- **No graph rewrite.** m_flow shows graphs work but cost ~28 min per question on our hardware and require their full pipeline. Stays out of scope.
- **No new retrieval primitive.** Reuses parent's cosine + Jaccard cascade. The variants change what gets *exposed* from storage to the LLM, not how candidates are found.

## How we'll measure

LongMemEval scores recall, not reasoning-about-memory. So scores are a *floor check* — does the architectural change break recall? If a variant scores within 5pt of `PrototypeMemory` on a 5-question oracle smoke, we keep it; if it tanks recall by 10pt+, the architectural shape needs rethinking before scaling to n=100.

The *real* test of these variants belongs in the research-pipeline simulation loop — does an agent given an `EpistemicPrototype` produce better-reasoned scientific artifacts than one given a flat triple store? That's a separate evaluation effort we'll design after the smoke confirms recall isn't broken.

## Levers we're not using (and why)

A handful of "obvious" optimizations sit just outside the scope of these two variants. Recording them here so we don't keep rediscovering them and reflexively reaching for them when scores wobble.

### Embedding dimension

It's tempting to think bumping qwen3-embedding-0.6b (1024d) to a higher-dimensional encoder would help. The empirical floor below ~256d is real but we're well past it; above ~768-1536d the curve plateaus for dense passage retrieval. MTEB-style benchmarks consistently show *which model* dominates *which dimension* — a 768d sentence-transformer routinely beats a 4096d generic encoder on retrieval, despite being 5× smaller.

What actually limits our memory's recall is **what gets embedded**, not the vector size:

- We embed full doc text and match a single question against it. A LongMemEval session is ~30 dialog turns; only one is relevant. Averaging into one 1024-d vector drowns the signal.
- Per-turn or per-sentence chunk embedding (even at 384d) beats per-doc embedding at 1024d.
- Phase B's `_chunk_fallback` already started this direction. Making chunk retrieval the default path instead of fallback is a higher-leverage move than swapping the embedder.

Also: qwen3-embedding-0.6b is general-purpose multilingual. LongMemEval is English conversational dialog — text it wasn't strongly tuned on. A specialized conversational-retrieval embedder (e.g., `BAAI/bge-large-en-v1.5`, also 1024d) would likely outperform qwen3 at the same dimension. *Embedder training distribution dominates dimension* in practice.

We don't pursue any of this here because it's a retrieval-quality patch, not an architectural change. Both variants reuse the parent's embedder unchanged so we measure the architectural change cleanly.

### Sequence-length truncation

qwen3-embedding's max length is ~8K tokens. If a session document exceeds that, the tail is silently dropped. Worth verifying; would explain a class of "context doesn't have it" failures on the longest LongMemEval sessions. Same retrieval-quality bucket as above — out of scope for the variants, but worth checking before any future "why did recall plateau" analysis.

### Reranker

A cross-encoder reranker on top of the K candidates retrieved by either variant would predictably lift scores by 3-8pt. We don't add one because (a) it doesn't change what storage represents, only how candidates are ordered, and (b) it adds an LLM call per query, slowing the simulation loop by ~5×.

## Status

- [ ] Implement `EpistemicPrototype` in `systems.py`
- [ ] Implement `GapAwarePrototype` in `systems.py`
- [ ] Register both in LongMemEval `_new_system`
- [ ] 5q LongMemEval smoke for each
- [ ] If smoke ≥45% (within 11pt of base prototype's 56%), run n=100 against the same oracle dataset
- [ ] Design the research-pipeline-loop evaluation that actually tests the architectural innovation

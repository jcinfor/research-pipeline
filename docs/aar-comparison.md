# AAR Comparison & PGR Proxies

*Comparison of `research-pipeline` to Anthropic's Automated Alignment Researchers, and the design rationale for the PGR-proxy metric (`rp project score`) — what the proxies approximate, why three pieces, and where each one stops being a faithful proxy.*

Upstream: <https://www.anthropic.com/research/automated-alignment-researchers>

---

## Part 1 — What Anthropic Built

From the paper, the AAR setup:

- **9 copies of Claude Opus 4.6**, each with *"a slightly different (but intentionally ambiguous) starting place"* — one was told to "use some interpretability tools", another to "think about reweighting the data"
- **Infrastructure** (four pieces):
  1. Sandbox for individual work
  2. **Shared forum** to circulate findings
  3. **Code storage** for uploaded implementations
  4. **Remote PGR scorer** — Performance Gap Recovered, 0 = weak model, 1 = strong-model ceiling
- **Divergence was critical** (paper):
  > "giving each AAR a different starting point helped a lot... Without this, they all quickly settled on similar ideas, making much less progress overall."
- **No structured long-term memory, no hypothesis lifecycle** — coordination was emergent through the forum + PGR feedback
- **Results**: best method achieved PGR **0.97 on training**, generalizing to **0.94 math / 0.47 coding** on held-out data

## Part 2 — Side-by-Side

| axis | Anthropic AAR | research-pipeline (ours) |
|---|---|---|
| **Agent population** | 9 Claude instances (homogeneous model, heterogeneous prompts) | 8 archetypes (scout, hypogen, experimenter, critic, replicator, statistician, writer, reviewer) with role-distinct prompts |
| **Seeding strategy** | "Slightly different ambiguous starting places" per instance | Per-archetype `seed_angle` pointing each to a distinct cognitive stance (underappreciated source / counterintuitive hypothesis / biggest blindspot / …) |
| **Shared forum** | Single forum | Two channels: flat **Twitter** (≤280 char with `[src #N]` + `[hyp #N]` refs) + threaded **Reddit** rounds |
| **Shared storage** | Code storage | **Blackboard** (kind-typed: evidence / hypothesis / critique / experiment / result / draft / review) with embedding dedup, echo clustering, provenance |
| **Objective signal** | Single scalar PGR per idea | Multi-dim: **LLM-judged rubric** (relevance / novelty / rigor / citation_quality) + project **counters** (coverage, evidence_density, idea_diversity, echo_rate) + **per-agent 6-dim rubric** (adds role_consistency + collaboration_signal) |
| **Feedback loop** | PGR fed back as numerical score per idea | Last-turn rubric injected into each agent's system context |
| **Ground-truth source** | Remote PGR evaluator | User-ingested PDFs via MarkItDown → embedded chunks → `[src #N]` citations at generation time |
| **Hypothesis tracking** | None — free-form discussion | Explicit **lifecycle**: `proposed → under_test → supported / refuted` via `[hyp #N]` references |
| **Persistent memory** | None (each run starts fresh) | Per-user **Karpathy wiki** compounding across projects, auto-promoted on healthy runs |
| **Adaptation** | Self-adaptation via prompting (Claude designs cheap experiments before intensive testing) | **Explicit optimization loop** — per-agent rubric → weakest-agent decision tree → config mutation → re-run until plateau |
| **Output** | Method implementations scoring 0.47–0.97 PGR | Prose report **+ 5 structured artifacts**: claims (with falsifier), hypothesis matrix, verification experiments, recommended decision, risks |
| **Model tier** | Frontier (Opus 4.6) × 9 | Any OpenAI-compatible endpoint (local vLLM Gemma 26B tested) |

## Part 3 — Which Is Better?

**Honest answer: Anthropic's, for the class of problem they picked. Ours, for the class we picked. Theirs is more rigorous; ours is more general.**

### Why theirs on the merits

1. **Validated against ground truth.** PGR 0.97 is a real number. The system produced methods that actually worked. Our "70 tests green" is system-integrity, not research-output quality — we have no PGR-equivalent proving the pipeline produces *better* research than a single Claude prompt.
2. **Simpler.** Four pieces vs our ~20 modules. Every line of code we added is a line the AAR system avoided.
3. **Closes the loop to reality.** Agents propose methods → scorer returns PGR → agents iterate. Our agents generate prose, the judge grades prose, agents adapt based on prose grade. No ground truth anchors the whole thing.
4. **Scales to their claim.** 9 Opus 4.6 instances parallel reached 0.94 on held-out math — a strong-model phenomenon we can't replicate with local 26B Gemma.

### Why ours on the merits

1. **Most research has no PGR.** You can't PGR-score "evaluate Zep TKG as a memory layer" or "find KRAS inhibitors beyond sotorasib". For these, a multi-dim rubric + structured artifacts is the only option.
2. **Captures the process, not just output.** AAR output is method + score. Ours is method + falsifier + predicted outcome + risks + citation trail. More useful for human researcher workflows; unnecessary when there's an oracle.
3. **Compounds across projects.** The Karpathy wiki means project 3 starts with project 2's learnings. AAR was stateless across runs.
4. **Works on commodity hardware.** Local vLLM, any Ollama endpoint.

### The real tradeoff

| choose… | when… |
|---|---|
| **AAR** | You have a measurable benchmark and frontier-model budget. The question reduces to "can LLMs autonomously find the best method?" |
| **Ours** | The question is open-ended, output must be human-consumable, there's no oracle, research compounds over time |

### What we'd need to be *rigorous-better*

- A **verification loop** (run proposed experiments, get real feedback)
- Replace the LLM rubric with task-specific scorers when available
- Empirical validation: "on benchmark X, our optimize loop recovers Y% more than single-shot"

Without those, our pipeline is an *architectural bet* — theirs is a *proven result*. Our claim that the scaffolding pays off for general research is unvalidated.

### Personal take

The right synthesis is **AAR's kernel + our scaffolding** — use their proven kernel (divergent seeds + scalar feedback) wherever a scorer exists, fall back to our multi-dim structure where no scorer exists, always produce structured artifacts, always compound in a wiki. That's what phase 3 should become.

## Part 4 — The Key Insight We Adopted

Early in the project, after reading the AAR paper, we implemented the divergent-seed insight directly:

> "Giving each AAR a different starting point helped a lot... Without this divergence, they all quickly settled on similar ideas."

This became our `seed_angle` per archetype. **Empirically verified**: our first run (uniform seeds) saw 3 agents converge on "pivot to non-covalent allosteric" with near-identical wording. The fix (distinct seed_angles targeting *underappreciated source / counterintuitive hypothesis / biggest blindspot*) produced 3 genuinely distinct directions with zero convergence collapse.

This is the single most important design decision we made, and it came from their paper.

## Part 5 — PGR Proxies for Research Without a Scorer

The central question: **can we design a PGR-proxy for arbitrary research projects?**

Five families, ranked by how cheaply they bolt onto our pipeline.

### Proxy 1 — Citation-trace verifiability ★ ship first

**Idea:** for every `[src #N]` citation in the final artifacts, an LLM judge reads the claim + the cited chunk and answers "does this chunk actually support this claim?"

```
PGR_cite = fraction_of_cited_claims_where_source_actually_supports_claim
```

- **Range:** 0–1. Weak baseline: 0 (hallucinated citations all fail). Ceiling: 1.
- **Cost:** one LLM call per citation. A 10-claim report with 3 cites each = 30 cheap judge calls.
- **Catches:** hallucinated citations, partial-support citations, citations where the source says the *opposite* of the claim. This is the single biggest credibility failure mode in our current output.
- **Limitation:** can't detect claims that are *well-cited but wrong* — the source may itself be incorrect. Acceptable for academic research; for high-stakes domains stack with Proxy 3.

### Proxy 2 — Held-out evidence alignment

**Idea:** at ingestion time, hash-partition chunks into `visible` (80%) and `held-out` (20%). Agents only see the visible set. After the report, an LLM judge checks whether the report's claims are *consistent with* the held-out chunks.

```
PGR_heldout = support_fraction - contradict_fraction
```

- **Cost:** |held_out_chunks| × |top_claims| judge calls. ~50–200 LLM calls end-of-run.
- **Catches:** overfitting to presented evidence, claims that collapse when new-but-related information is introduced. **This is directly the AAR train/held-out split applied to evidence.**
- **Limitation:** depends on having enough ingested content to partition meaningfully. Works for lit-review and domain-evaluation projects; fails for minimal-source projects.

### Proxy 3 — Adversarial critique (Red Team)

**Idea:** end-of-run, spin up a dedicated Red Team agent (different model tier if possible, otherwise same model with a "find every hole" prompt) whose sole job is to undermine the report's claims. Each undermining attempt is scored by a separate judge.

```
PGR_adv = 1 - fraction_of_claims_successfully_undermined
```

- **Cost:** one Red Team pass over N claims + judge pass. ~20–30 LLM calls.
- **Catches:** claims that *look* supported but crumble under adversarial pressure — the most common failure mode of plausible-sounding research.
- **Limitation:** if Red Team and original agents share a model, they share a blindspot. Mitigate by using a different model family for Red Team.

### Proxy 4 — Triangulation / reproducibility

**Idea:** run the same project N times with different random seeds (temperature jitter + seed_angle rotation). Measure whether independent runs converge on the same top claims.

```
PGR_repro = pairwise_claim_overlap(runs)
```

- **Cost:** N× full simulation runs. Very expensive.
- **Catches:** runs that are *lucky* rather than *skilled* — the pipeline fooling itself.
- **Limitation:** only makes sense as a periodic sanity check, not per-run.

### Proxy 5 — Execution-based (when applicable)

**Idea:** where the domain has an actual evaluator — docking scores for drug discovery, unit tests for code, proof verifiers for math, benchmark accuracy for ML — use it directly.

- **Cost:** varies.
- **Catches:** everything PGR was designed to catch.
- **Limitation:** only applies to domains with an oracle.

## Part 6 — Which Proxy Matches Which Research Type

| research type | applicable proxies |
|---|---|
| **Literature synthesis** | 1 (cite-trace), 2 (held-out), 4 (reproducibility) |
| **Method/architecture evaluation** (e.g. Zep vs embeddings) | 1, 3 (Red Team), 5 (if benchmark exists) |
| **Drug/mechanism hypothesis** | 1, 3, 5 (docking scores if available) |
| **Code / ML methods** | **5** (benchmarks) + 1 as backup |
| **Policy / qualitative research** | 3 only (no oracle, no held-out split meaningful) — accept that this is judgment-based |
| **Forecasting** | wait for ground truth (Brier score), or use triangulation as early signal |

## Part 7 — Recommended Phase 3

Ship **Proxy 1 + Proxy 2** as an immediate next phase:

**`rp project score <id>`** — runs all configured proxies, returns:

```
PGR_cite       = 0.82  (14/17 claims have verified citations)
PGR_heldout    = 0.61  (top claims consistent with held-out evidence)
PGR_adv        = 0.75  (11/15 claims survived Red Team)
Composite      = 0.73  (weighted mean)
```

Persist these as project-level KPI rows alongside the existing rubric. Then:

**The optimize loop gains a real objective.** Instead of the LLM judge's rubric (which can drift), optimize against `PGR_cite × PGR_heldout × PGR_adv`. This *is* AAR's pattern, with our multi-dim proxy substituting for PGR.

### What this unlocks

If `PGR_cite` on project 2 is 0.6 — meaning 40% of cited claims don't actually trace back to the cited sources — that's a **concrete, falsifiable hit on output quality** we can measure over time. Phase-2's rubric improvements can be validated: *did they raise `PGR_cite` from 0.6 to 0.85?*

That is the thing we currently cannot measure. Without it, "70 tests green" is system-integrity noise against the actual research-quality signal we care about.

### Scope estimate

- `pgr.py` module with `pgr_cite()`, `pgr_heldout()`, `pgr_adversarial()` — each ~60 lines
- Extend `db.py` with `chunk_partition` column (visible / held_out) on `blackboard_entries`
- Update `ingest.py` to hash-partition on insert
- Extend `kpi_scores` to store pgr metrics (no schema change — just new metric names)
- CLI: `rp project score <id>` + dashboard shows PGR sparklines in KPI trajectory
- Optimize loop switch: `rp project optimize --objective pgr` uses PGR composite instead of rubric mean
- Integration test with fake judge

**~1.5 days of focused work.** Unlocks genuine measurement of research quality for the first time.

## Part 8 — Where Proxies Still Fail

Some research genuinely has no PGR-proxy: **purely qualitative policy analysis, strategic forecasting, creative research directions**. There, the best we can do is stack rubric + adversarial critique + human review. Accept it's judgment-based and make the audit trail strong.

That's a property of the domain, not a failure of the pipeline. A rigorous human researcher in those domains also can't point at a scalar and say "my output is 0.94 correct" — they cite, they anticipate critiques, they disclose limits. Our pipeline can produce the same style of output. It can't fake an oracle that doesn't exist.

## Part 9 — The Metric-Pair Pattern (phase 3.5)

*Added 2026-04-23 after an empirical finding on project 6.*

### The failure mode we hit

When the user (acting as researcher/judge) injected higher-level reframes via `rp project pi-post`, the agents picked them up and produced genuinely better research output — sharper experiment designs, cleaner taxonomic axis, a novel "write-time drift tax" concept that unified the two architectures being compared. **PGR composite dropped from 0.54 → 0.33.**

Breakdown:
- `pgr_cite` 0.86 → 0.43: claims shifted from restating the ingested sources to synthesizing across them. The judge correctly marked the citations as "neutral" — the source *discusses* LLM extraction but doesn't *frame it as a tax*. The new abstraction is in the reader's head, not the chunk.
- `pgr_adv` 0.60 → 0.40: bolder claims have more attack surface, so Red Team undermined more of them.
- `pgr_heldout` 0.20 unchanged — the synthesis transcended the corpus, so held-out chunks can't adjudicate either way.

The pipeline produced better research and the metric said worse. That's a metric failure, not a pipeline failure.

### The tension, named

- **`pgr_cite` rewards traceable restatement. It punishes synthesis.**
- **`pgr_adv` rewards caution. It punishes testable boldness.**
- Together they can flag a genuine intellectual advance as a regression.

A strict citation-trace metric only rewards claims that *literally* appear in the sources. Good research often combines facts from multiple sources into new abstractions that don't appear *anywhere* in the corpus. The claim "both architectures pay a write-time drift tax" is true, useful, and inferable from the sources — but no single chunk contains the phrase. Strict-cite punishes this.

### The fix: metric pairs

Ship `pgr_support` as a *companion* to `pgr_cite`, not a replacement:

| metric | scoring | rewards | punishes |
|---|---|---|---|
| `pgr_cite` | binary (support / contradict / neutral) | literal restatement | synthesis, inference |
| `pgr_support` | 0/1/2 scale (off-topic / partial / direct) | inferential grounding | pure speculation |

Score = `(direct * 2 + partial * 1) / (2 * total)`. Range 0-1.

The judge prompt explicitly says: "Use level=1 generously. If the chunk supplies a relevant fact that a reader could use to build the claim, that's a 1."

### Reading the pair

| pgr_cite | pgr_support | interpretation |
|---|---|---|
| high | high | claims are literal restatement + well-grounded (phase-1 behavior) |
| **low** | **high** | claims are **synthesis** — they go beyond sources but stay inferentially grounded (the interesting research case) |
| low | low | claims are speculative; not grounded in the corpus |
| high | low | paradoxical — shouldn't happen |

The gap `pgr_support - pgr_cite` is diagnostic: > 0.15 means the pipeline is producing synthesis rather than restatement.

### What didn't change

- **Composite still = cite × 0.4 + heldout × 0.3 + adv × 0.3.** `pgr_support` is a *diagnostic*, not a composite component. Keeps the composite conservative while exposing the synthesis signal separately.
- **Existing scores are preserved.** `pgr_cite` still computes the way it always did. `pgr_support` runs alongside.
- **Judge cost adds ~N calls** (one per citation) — same order as `pgr_cite`. No new model, no new infrastructure.

### Phase-4 implication

The Red Team refinement (undermined/survived binary → residual strength 0-2 scale) would be the natural sibling change for `pgr_adv`, but it's deferred. When implemented, `pgr_adv_strength` would reward bold claims that *partially* survive rather than zeroing them.

Pattern: for every strict proxy, design a paired loose proxy. Read them together. Don't average them into a single score — the pair itself is the signal.

## Part 10 — The Karpathy + Zep Hybrid (shipped 2026-04-23)

*Project 6 compared Zep-style temporal knowledge graphs against Karpathy-style LLM Wiki for agent memory. The pipeline refused to pick a winner without running the stress-test experiment. My reading of the evidence is: don't pick between them — hybridize.*

### The honest conclusion from project 6

Neither architecture is "clean." Both pay the **write-time LLM-drift tax**:

- **Karpathy LLM Wiki**: LLM compiles raw sources into structured markdown; extraction errors land in the wiki pages.
- **Zep TKG**: LLM extracts entities and relations; extraction errors land in the graph structure.
- **Flat RAG (Tier A)**: LLM only at query time; no compilation drift, but no recency resolution either.

So "which wins" is a false question at the architecture level. The real differentiators are:

| axis | Karpathy Wiki | Zep TKG |
|---|---|---|
| human-readable / auditable | ✅ markdown files | ❌ graph entries |
| low-ops / local-first | ✅ files on disk | ❌ graph DB required |
| precise temporal reasoning | ❌ no temporal index | ✅ `$t_{ref}$` via bi-temporal model |
| query-time contradiction repair | ❌ needs lint pass | ✅ temporal precedence at retrieval |
| compounding across sessions | ✅ via index.md + log.md | ✅ via graph evolution |

### The hybrid shipped

Karpathy's surface + Zep's temporal signal. Concretely: every `user_wiki_entries` row gets an optional `t_ref` column — an ISO date indicating when the claim is FACTUALLY TRUE (not when ingested).

- **Storage**: `ALTER TABLE user_wiki_entries ADD COLUMN t_ref TEXT` — nullable, migrated idempotently.
- **Derivation**: on promote-to-wiki, `_extract_t_ref(refs)` pulls the max year from the entry's refs (years in [1900, 2099]) and stores it as `YYYY-01-01`. Entries without year-refs stay `t_ref=NULL` (atemporal).
- **Query**: `search_wiki(conn, ..., as_of='2023-06-01')` filters to entries with `t_ref <= as_of OR t_ref IS NULL`. CLI: `rp wiki search "..." --as-of 2023-06-01`.
- **Backwards compat**: existing wiki entries (pre-migration) have `t_ref=NULL` and are treated as atemporal. No backfill — old data stays untouched; new promotions get t_ref where derivable.

### Why this is the right compromise

- **Kept**: markdown storage, human-readability, local-first deployment, no graph DB
- **Gained**: "show me what the wiki knew as of 2023" — Zep's single most useful capability applied at the query layer only
- **Didn't build**: a full knowledge graph, a custom extractor, query-time contradiction resolution, conflict merging. Those are phase-4+ if ever needed.

### What we refused to build

A full Zep-style TKG. Reasons:
1. Adds a graph-database dependency (neo4j, or rolling our own over SQLite). Violates the low-ops constraint.
2. Compilation drift is the same whether you store as markdown or graph — we haven't eliminated the real risk, just structured it differently.
3. The pipeline is single-user, session-scale research — not a production agent with millions of user events. The overhead doesn't earn its keep.

### Pattern to remember

When architectural comparisons dead-end at "it depends," look for the single most useful capability of the losing side and port it as a *feature* on the winner's surface. Don't adopt wholesale; steal the one thing that matters.

Here: Zep's winning capability was temporal disambiguation via `$t_{ref}$`. We stole that (`t_ref` column + `--as-of` filter) without adopting anything else. ~20 lines of code. Test coverage: 9 new tests in `tests/test_wiki_t_ref.py`. Feature earns its weight if any future project ever needs "what did we know at time X?" on the accumulated wiki.

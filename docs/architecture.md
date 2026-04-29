# Architecture

*Single-page reference for the memory + simulation design behind `research-pipeline`. For empirical justification, see [BENCHMARKS.md](../BENCHMARKS.md). For depth on any single piece, the deep-dive docs are linked at the end.*

## The idea in one paragraph

A research project's memory has three timescales: what an agent thinks **right now** (working memory), what a project **has discovered** (project blackboard), and what the **user knows** across all their projects (long-term wiki). We model these as three tiers, all stored in SQLite, all cosine-searchable, all in plain markdown. Information flows up — turn-level posts promote into the blackboard; healthy projects promote into the wiki — and seeds back down when a new project starts. **No graph database, no separate vector store, no custom entity extraction.** The Karpathy LLM-Wiki pattern provides the structure; one capability from Zep (`t_ref` time anchor) provides temporal precedence.

## The three tiers

```
                ┌─────────────────────────────────────┐
                │  T3 — Cross-Project Long-Term       │
                │  user_wiki_entries                  │
                │  Karpathy structure + t_ref         │
                │  cosine + as_of filter              │
                └──────────────┬──────────────────────┘
                               │ promote on healthy run
                               │ (rubric ≥ floor)
                ┌──────────────▼──────────────────────┐
                │  T2 — Per-Project Blackboard        │
                │  blackboard_entries (kind-typed)    │
                │  evidence/hypothesis/critique/      │
                │  experiment/result/draft/review     │
                │  cosine dedup + lifecycle           │
                └──────────────┬──────────────────────┘
                               │ promote per turn
                               │ (archetype → kind)
                ┌──────────────▼──────────────────────┐
                │  T1 — Per-Turn Working Memory       │
                │  in-context prompt block            │
                │    SOURCES       [src #N]          │
                │    HYPOTHESES    [hyp #N]          │
                │    RECENT POSTS  last 12           │
                │    FEEDBACK      last-turn rubric  │
                │  no storage; regenerated each turn  │
                └─────────────────────────────────────┘
```

| tier | scope | table | retrieval | dedup | lifecycle |
|---|---|---|---|---|---|
| **T1 working** | one turn | (in-prompt only) | LLM attention | n/a | ephemeral |
| **T2 project** | one project | `blackboard_entries` | cosine over `embedding_json`, filtered by `kind` and `visibility` | echo cluster (cos ≥ 0.85) | proposed → supported / refuted / verified |
| **T3 long-term** | one user, all projects | `user_wiki_entries` | cosine + optional `as_of=YYYY-MM-DD` | exact-content match on promote | append-only; promote_score = rubric × refs × echo × length |

### T1 — Working memory

No storage. Regenerated every turn. The complete prompt sent to an agent at posting time:

```python
system_msg = (
    archetype.system_prompt          # role
    + specialty_focus_block          # per-agent config
    + role_reinforcement             # anti-convergence nudge
    + kpi_feedback_line              # last-turn rubric
    + citation_policy                # [src #N] must trace
)
user_msg = (
    f"GOAL: {goal}\n"
    f"SOURCES (cite by [src #N]):\n{evidence_block}\n"        # top-6
    f"HYPOTHESES IN PLAY (cite as [hyp #N]):\n{hyps_block}\n"  # top-6
    f"RECENT CHANNEL POSTS:\n{feed_block}\n"                   # last 12
    f"Your task: post ONE tweet ...\n"
)
```

Size-bounded inputs (top-6 evidence, 6 hypotheses, 12 posts) keep each turn within ~2k tokens. Everything else is retrieval.

### T2 — Project blackboard

Single SQLite table. The substrate:

```sql
CREATE TABLE blackboard_entries (
    id                INTEGER PRIMARY KEY,
    project_id        INTEGER NOT NULL,
    agent_id          INTEGER,
    kind              TEXT,           -- evidence/hypothesis/critique/...
    content           TEXT,
    refs_json         TEXT,           -- cited years, DOIs, author tokens
    turn              INTEGER,
    embedding_json    TEXT,           -- 1024-dim qwen3-embedding
    echo_count        INTEGER DEFAULT 0,
    state             TEXT DEFAULT 'proposed',   -- hypothesis lifecycle
    visibility        TEXT DEFAULT 'visible'     -- 'visible' or 'held_out' for PGR
);
```

**Write paths** (in order, every turn):
1. `link_mentions` — `@agent_N` references → `parent_id` backfill on channel posts
2. `promote_project_posts` — agent posts → blackboard, mapping archetype to kind:
   - scout → evidence · hypogen → hypothesis · experimenter → experiment
   - critic → critique · replicator → result · statistician → critique
   - writer → draft · reviewer → review
3. `add_entry_with_dedup` — embed, find cosine ≥ 0.85 neighbors of the same kind, either insert or `echo_count++` on the canonical
4. `resolve_hypothesis_refs` — scan results/critiques for `[hyp #N]`, transition state

**Read paths**:
- `retrieval.search_blackboard(project_id, query, kind, visibility)` — cosine over `embedding_json`. Default `visibility='visible'` so agents can't see held-out chunks.
- `lifecycle.hypotheses_in_play(project_id, limit=6)` — open hypotheses for T1
- `lifecycle.get_state_history(project_id, hypothesis_id)` — full chronological state trail
- `query_helpers.*` — six structured slices (`get_critiques_for`, `get_results_for`, `get_disagreements`, `get_hypothesis_arc`, etc.) so the writer/reviewer don't pattern-match across the whole substrate

The structured query helpers were added 2026-04-25 after E6 surfaced the **storage-vs-query-surface lesson**: preserving information at write isn't enough; the query layer must expose it. Same substrate, six new helpers.

### T3 — Per-user wiki

```sql
CREATE TABLE user_wiki_entries (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL,
    kind                TEXT,             -- same taxonomy as T2
    content             TEXT,
    refs_json           TEXT,
    embedding_json      TEXT,
    source_project_id   INTEGER,
    promoted_score      REAL,
    t_ref               TEXT,             -- ISO date when claim is TRUE
    created_at          TEXT DEFAULT (datetime('now'))
);
```

**Write path**: `wiki.promote_project_to_wiki` runs at end-of-run when project rubric ≥ `auto_promote_rubric_floor` (default 3.0). For each kind, top-K by `_score_entry` (rubric × refs × echo × length). `_extract_t_ref(refs)` pulls the max year in `[1900, 2099]` from the entry's refs → `YYYY-01-01`. Entries without year-refs stay atemporal (`t_ref=NULL`). Embedding copied from blackboard — no re-embedding.

**Read path**:
- `wiki.search_wiki(user_id, query, top_k, kind, as_of)` — cosine + optional temporal filter
- `as_of='YYYY-MM-DD'` returns entries with `t_ref <= as_of OR t_ref IS NULL` (atemporal entries always included)
- `wiki.seed_project_from_wiki` — pre-populate a new T2 with relevant T3 hits as evidence, refs prefixed `source=user_wiki#<id>` for traceability

## How information flows

### Write path — ingest

```
PDF / DOCX / HTML / MD
        │ rp project ingest <id> <files>
        ▼ MarkItDown → markdown
        ▼ chunk (split by heading, size-capped)
        ▼ for each chunk:
              _is_held_out()  → visibility ∈ {visible, held_out}
              extract_refs()  → years, DOIs, arxiv ids, author tokens
              llm.embed()     → 1024-dim qwen3-embedding
        ▼ add_entry_with_dedup
        ▼ blackboard_entries (T2) as kind=evidence, agent_id=NULL
```

### Write path — promotion up the tiers

```
agents post in channel_posts
        │ end-of-turn hooks:
        │   link_mentions, promote_project_posts,
        │   resolve_hypothesis_refs, snapshot_counters
        ▼
blackboard_entries (T2) grows
        │ project finishes; judge_project scores rubric
        │ if rubric ≥ floor:
        ▼
promote_project_to_wiki(top_k_per_kind=3)
        │   rank by _score_entry
        │   _extract_t_ref(refs)
        │   dedup on exact content
        ▼
user_wiki_entries (T3)
```

### Read path — per-agent per-turn

```
agent's turn in simulation._run_prompted_turn
        ▼ _retrieve_evidence(goal, top_k=6)         # search T2 kind=evidence visibility=visible
        ▼ hypotheses_in_play(project_id, limit=6)   # T2 kind=hypothesis state ∈ proposed/under_test
        ▼ _recent_posts_context(project_id, 12)
        ▼ _recent_kpi_scores(project_id)
        ▼ composed T1 prompt
        ▼ llm.achat(temperature=per_agent_config)
        ▼ _generate_unique_post (dedup retry)
        ▼ OASIS env.step(ManualAction(CREATE_POST))
```

### Seed path — T3 → new T2

```
new project created; user wants prior knowledge
        │ rp wiki seed <new_project_id>
        ▼ search_wiki(user_id, project.goal, top_k=6)
        ▼ hits copied as kind=evidence into target T2
            refs prefixed "source=user_wiki#<entry_id>"
            threshold=0.98 dedup (wiki content already vetted)
        ▼
blackboard_entries (T2) of the new project
```

## What we kept from Karpathy

The [Karpathy LLM-Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) provides the structural pattern. We kept it nearly verbatim:

| Karpathy concept | Our implementation |
|---|---|
| `raw/` — immutable sources | `projects/{id}/raw/*.md` (MarkItDown output) |
| `wiki/` — LLM-compiled pages | `user_wiki_entries` table, kind-typed content |
| Cross-linking via backlinks | `[src #N]`, `[hyp #N]`, `source=user_wiki#id` patterns |
| Ingest op (compile sources) | `ingest.py` + promote to wiki |
| Query op (search + synthesize, file back) | `wiki.search_wiki` + `synthesize.py` artifacts |
| Lint op (contradictions, orphans, stale) | partial: `dedup` + `lifecycle` + echo-clustering |
| Persistent compounding | auto-promote on healthy runs + `rp wiki seed` |
| Human-readable markdown | `render_wiki_markdown` + `rp wiki show` |

We skipped the specific toolchain (Obsidian, Marp, Dataview plugins) because our pipeline is code-first, not markdown-file-first. We kept the **pattern** and the **principles**: LLM does bookkeeping, human curates, knowledge compounds.

## What we took from Zep — and what we didn't

We took **exactly one thing**: `t_ref TEXT` column on `user_wiki_entries` — Zep's reference-timestamp pattern, applied as a temporal anchor for the wiki.

```python
def _extract_t_ref(refs: list[Any]) -> str | None:
    """Pull max year [1900, 2099] from refs; return 'YYYY-01-01' or None."""
```

`wiki.search_wiki(as_of=...)` filters by temporal precedence. Null `t_ref` = atemporal (always included).

We **deliberately did not** take:

| Zep feature | Why we passed |
|---|---|
| Bi-temporal model (T and T' timelines) | Single `t_ref` + `created_at` covers 80% at 5% cost |
| Episode subgraph | T2 + `turn` column serves the role |
| Semantic entity subgraph | We don't extract entities; retrieval is cosine over chunks |
| Community subgraph (label propagation) | Kind-typed clustering is sufficient at our scale |
| Graphiti / Neo4j | Local-first low-ops constraint; SQLite wins |
| Structural extraction pipeline | MarkItDown + chunking is the extraction; no KG nodes |
| Query-time contradiction resolution | Deferred; would live as a layer on top of `search_wiki` |

## What we took from Graphify

[Graphify](https://github.com/safishamsi/graphify) (MIT) is a knowledge-graph compiler that extracts EXTRACTED/INFERRED/AMBIGUOUS edge labels and structurally compresses graphs for downstream prompts. We integrate it as an optional KG view (`rp project kg <id>` calls Graphify's CLI) and we lifted two patterns from it into the core pipeline:

| Graphify concept | Our implementation |
|---|---|
| Per-edge `EXTRACTED` / `INFERRED` / `AMBIGUOUS` provenance label | `confidence` column on `blackboard_entries` (added 2026-04-25); per-archetype defaults in `promote.py::confidence_for` (scout → EXTRACTED, hypogen/critic/writer/reviewer → INFERRED, replicator dynamic), `lowest_confidence([...])` helper for inheriting weakest label across cited sources |
| Structural compression of a graph for prompt context | `blackboard_digest.py::render_digest` (added 2026-04-25) — markdown rollup of state matrix, top hypotheses by inbound-ref count, latest state transitions, open disagreements, recent results/critiques, confidence-mix ratio. Prepended to writer + reviewer prompts; ~500-800 tokens per project |

We skipped Graphify's full graph store (it produces an Obsidian/wiki-renderable graph; we use SQLite cosine retrieval for runtime queries) and its 71.5× compression target (only meaningful at much larger corpora than a single research project). We kept the **two patterns** that addressed gaps the benchmarks surfaced — provenance labels for downstream PGR / writer transparency, and structural digest for writer/reviewer grounding.

## The compounding loop

This is what makes the wiki a wiki and not just a results store:

```
project N ends with rubric ≥ floor
        ▼ auto_promote_to_wiki → top-K per kind land in T3 with t_ref
        │
        │ user starts project N+1 on a related topic
        │
        ▼ rp wiki seed <N+1>
        │   search_wiki finds relevant prior entries
        │   filed into T2 with refs='source=user_wiki#<id>'
        │
        ▼ agents in N+1 see prior knowledge in their T1 context
        ▼ discussion builds on prior synthesis (doesn't start from zero)
        ▼ project N+1 produces new claims/artifacts
        ▼ auto_promote_to_wiki → T3 grows
        │
        └─► back to top
```

`--as-of` lets you collapse this cycle and ask "what did T3 know at date X?" — useful for reproducibility checks and historical-state queries.

## Boundary: pipeline product vs PrototypeMemory research artifact

**This repo contains two distinct memory architectures.** They serve different purposes:

| | **research-pipeline product** | **PrototypeMemory (research artifact)** |
|---|---|---|
| Lives in | `src/research_pipeline/` | `benchmarks/e1_blackboard_stress/systems.py` |
| Purpose | Powers the `rp` CLI / dashboard | Synthesis of E1-E11 learnings; benchmarked alongside mem0/zep/m_flow/supermemory |
| Substrate | Kind-typed `blackboard_entries` + `user_wiki_entries` (this doc) | Append-only `(entity, attribute, value, valid_from, source)` triple log + materialized hot index |
| Workload | 50-200 entries per project, append-only by nature | Up to 20k triples with high attribute churn per entity |
| Why distinct | Different workloads → different optimal substrates. Don't conflate. |

The PrototypeMemory architecture is documented separately in [agent-memory-prototype.md](./agent-memory-prototype.md). One-line summary: append-only triple log + materialized hot index + intent-routed query dispatch (programmatic for count, full-history for cross-entity, hot-index for current). The two non-obvious bug fixes that mattered (keyword pre-routing, word-boundary regex matching) are in §4 of that doc.

The architectural recommendation we'd extract for **production agent-platform memory** (Claude-Code-class scale, ~9k+ triples) is in [agent-memory-decisions.md §1.3](./agent-memory-decisions.md). Short version: **multi-tier with hot index + append-only log + episode summaries**, with the router becoming a cost-management layer rather than a correctness layer. None of the five products we benchmarked ships this exact pattern.

### Research-extension variants

Two subclasses of `PrototypeMemory` ship as research artifacts that intentionally depart from the "passive store + query-time retrieval" template every existing memory system shares:

| variant | what it does differently | full design |
|---|---|---|
| `EpistemicPrototype` | Replaces the single-value hot index with a multi-claim store: same `(entity, attribute)` key can hold multiple competing values, each as an `EpistemicClaim` with a conviction trajectory. Retrieval surfaces the contested picture rather than collapsing to "latest". | [agent-memory-prototype-innovations.md](./agent-memory-prototype-innovations.md) §1 |
| `GapAwarePrototype` | After each ingest, an LLM identifies mentioned-but-unspecified facts and stores them as `Gap` entries. A consolidation tick between ingests surfaces contradictions and writes derived conclusions back. Queries see explicit "known unknowns" alongside known facts. | [agent-memory-prototype-innovations.md](./agent-memory-prototype-innovations.md) §2 |

Both pass the floor-check (don't break recall) on E8/E11/E11b. On the **full** LongMemEval (oracle, 100q, 2026-04-29), `epistemic_prototype` is the **top performer** at 58% LLM-judge — beating base `prototype` (56%) by 2pp and the actual current mem0 product (mem0's April-2026 v3 algorithm; we tested two configurations: default `pip install mem0ai` at 53%, and mainline + full nlp extras at 55%) by 3-5pp. The architectural advantage concentrates on multi-session: epistemic 23/40 (58%) vs `mem0_real_v3` (full v3 config) 16/40 (40%) = **+18pp** — the failure mode `EpistemicPrototype` was designed to address (preserve competing claims rather than overwrite). The same architectural insight is what mem0 v3 explicitly cites in its changelog ("single-pass ADD-only extraction; nothing is overwritten"); independent convergence on the design principle, with our implementation winning empirically on Gemma stack. `gapaware_prototype` lands at 52% (4pp behind base) at higher ingest cost — the per-doc gap-detection LLM call doesn't earn its keep on LongMemEval's question shape; that signal would surface on E12/E13 corpora we haven't designed yet.

## What this architecture deliberately doesn't do

- **No graph database.** All relationships are either cosine-similar or reference-based (`[src #N]`, `[hyp #N]`, `source=user_wiki#id`). No traversal, no edges, no inference over structure.
- **No entity extraction.** Chunks are the unit of knowledge. We don't build nodes for "Entity X" across sources.
- **No bi-temporal reasoning.** We have `t_ref` (when claim is TRUE) and `created_at` (when ingested). No T' transactional timeline, no temporal deltas.
- **No shared memory across users.** T3 is per-user. Org-level wiki is a deferred extension.
- **No query-time contradiction repair.** If two T3 entries disagree on the same concept (different `t_ref`), the retriever ranks by cosine — it doesn't pick a winner. The Writer/Reviewer reconciles.
- **No streaming / real-time updates.** Writes happen at end-of-turn (batched). Good enough for research; wrong for conversational agents with live state.

## Empirical anchors

Each design choice traces back to a specific benchmark finding. Selected from [BENCHMARKS.md](../BENCHMARKS.md):

- **Hybrid (Karpathy + t_ref) is correct for the wiki workload.** E4 measured `prototype` at 5/6 vs `zep_lite` at 6/6 — both within 1 question of perfect, on a benchmark designed to expose temporal retrieval errors. Separately, the simplest baseline (`hybrid_flat`) on E4 ingests 6.4× faster than `zep_lite` (3,085ms vs 19,653ms) at 5/6 — confirming the wiki workload doesn't need rich extraction at small scale.
- **The blackboard substrate (kind-typed append-only) suits our actual workload.** E1's high-velocity attribute churn isn't our pattern (we have kind-typed *new facts*, not attribute updates on the same entity).
- **The substrate must be append-only at every layer.** E6/E8/E9 showed mem0/zep_lite all collapse at the query layer regardless of storage. Our `resolutions_json` audit log is append-only by design.
- **The query surface must expose what the substrate retains.** E6's lesson; applied 2026-04-25 via `query_helpers.py`. Substrate unchanged; six new read-only views added.
- **Intent routing is unnecessary at our scale (≤500 triples).** E8 + E9 showed routed and full-expose tied. We don't ship a router for the product. PrototypeMemory adds one because it benchmarks at up to 20k triples.
- **At 10k+ triples, the "expose all" approach hits context limits.** E10-XL crashed `zep_rich` (0/7) and capped PrototypeMemory's historical queries (4/7). Episode summarization is the missing tier — empirically validated, not yet implemented in either architecture.

## Reference map

| Concept | Table | Module | Key functions |
|---|---|---|---|
| T1 working memory | — | `simulation.py` | `_run_prompted_turn`, `_retrieve_evidence`, `hypotheses_in_play`, `_recent_posts_context`, `_recent_kpi_scores` |
| T2 project blackboard | `blackboard_entries`, `channel_posts` | `blackboard.py`, `promote.py`, `dedup.py`, `lifecycle.py`, `retrieval.py`, `query_helpers.py` | `add_entry_with_dedup`, `resolve_hypothesis_refs`, `get_state_history`, `get_disagreements`, `get_hypothesis_arc`, `search_blackboard`, `promote_project_posts` |
| T3 long-term wiki | `user_wiki_entries` | `wiki.py` | `promote_project_to_wiki`, `search_wiki`, `seed_project_from_wiki`, `_extract_t_ref`, `_score_entry` |
| Optimize loop | `optimization_traces` | `optimize.py`, `iteration_summary.py` | `optimize_project`, `propose_adjustment`, `apply_adjustment`, `write_iteration_summary` |
| Ingestion | — | `ingest.py` | `ingest_file`, `_chunk_markdown`, `_is_held_out` |
| Embeddings | — | `adapter.py` | `LLMClient.embed`, `LLMClient.aembed` |

## One-sentence summary

**Three cosine-searchable tiers of markdown-like content in SQLite, with kind-typed per-project memory promoting to a temporally-indexed per-user wiki on healthy runs — Karpathy's wiki pattern as the structure, Zep's `t_ref` as the one stolen capability, no graph DB, no entity extraction, no bi-temporal reasoning.**

## Where to read more

- [BENCHMARKS.md](../BENCHMARKS.md) — empirical comparisons against mem0/zep/supermemory/m_flow
- [agent-memory-architecture.md](./agent-memory-architecture.md) — extended product architecture (data flows, schemas, write/read paths in full detail)
- [agent-memory-prototype.md](./agent-memory-prototype.md) — `PrototypeMemory` reference architecture synthesizing E1-E11 learnings (separate from the product)
- [agent-memory-decisions.md](./agent-memory-decisions.md) — what we recommend for production-scale agent-platform memory (e.g. Claude-Code-class) based on the benchmarks
- [terminology.md](./terminology.md) — canonical definitions: turn / round / iteration / sample / simulation / project
- [WRAP_UP.md](./WRAP_UP.md) — Phase-1 review + roadmap


# Agent Memory Architecture

*As-built reference for the three-tier hybrid memory in research-pipeline: Karpathy + Zep hybrid + Graphify-derived provenance / digest patterns, plus state-history, structured query helpers, and per-iteration summaries — small targeted improvements layered after the E1–E9 benchmark series. For the empirical case behind the design, see [agent-memory-benchmarks.md](./agent-memory-benchmarks.md). For decisions / what-we-did-vs-deferred, see [agent-memory-decisions.md](./agent-memory-decisions.md).*

## 1. Overview

Three cosine-searchable tiers of markdown-like content, with kind-typed per-project memory promoting to a temporally-indexed per-user wiki on healthy runs. All persisted in SQLite. No graph database, no separate vector store, no custom extractor beyond MarkItDown.

The architecture borrows structure from Karpathy's LLM Wiki pattern (markdown-first, human-readable, compounding), a single capability from Zep's temporal knowledge graph (`$t_{ref}$` as a time anchor per entry), and two patterns from [Graphify](https://github.com/safishamsi/graphify) (per-entry `EXTRACTED`/`INFERRED`/`AMBIGUOUS` provenance label + structural digest of the project state for writer/reviewer prompts — both shipped 2026-04-25; see §7).

## 2. The Three Tiers

```
                        ┌─────────────────────────────────────┐
                        │  TIER 3 — Cross-Project Long-Term   │
                        │  user_wiki_entries                  │
                        │  Karpathy structure + t_ref          │
                        │  cosine embedding + as_of filter    │
                        └──────────────┬──────────────────────┘
                                       │ auto-promote (rubric ≥ floor)
                                       │ or rp wiki promote <id>
                        ┌──────────────▼──────────────────────┐
                        │  TIER 2 — Per-Project Blackboard    │
                        │  blackboard_entries (kind-typed)    │
                        │  evidence/hypothesis/critique/      │
                        │  experiment/result/draft/review     │
                        │  state ∈ proposed/verified/refuted  │
                        │  dedup via cosine echo clustering   │
                        └──────────────┬──────────────────────┘
                                       │ promote_project_posts
                                       │ (every turn; archetype → kind)
                        ┌──────────────▼──────────────────────┐
                        │  TIER 1 — Per-Turn Working Memory   │
                        │  in-context prompt block            │
                        │    SOURCES       [src #N]          │
                        │    HYPOTHESES    [hyp #N]          │
                        │    RECENT POSTS  last 12           │
                        │    FEEDBACK      last-turn rubric  │
                        │  no storage; regenerated each turn  │
                        └─────────────────────────────────────┘
```

| tier | table | scope | retrieval primitive | dedup | lifecycle |
|---|---|---|---|---|---|
| **T1 working** | (in-prompt only) | one turn | LLM attention | n/a | ephemeral |
| **T2 project** | `blackboard_entries` | one project | `retrieval.search_blackboard` (cosine on `embedding_json`, `visibility='visible'`) | `dedup.add_entry_with_dedup` (cos ≥ 0.85 → echo on canonical) | `lifecycle.py` → proposed → supported / refuted / verified |
| **T3 long-term** | `user_wiki_entries` | one user, all projects | `wiki.search_wiki(as_of=...)` cosine + optional temporal filter | exact-content match on promote | append-only; promoted_score = rubric × refs × echo × length |

## 3. Tier Details

### 3.1 Tier 1 — Working Memory

No storage. Regenerated every turn by `simulation._run_prompted_turn`:

```python
system_msg = (
    archetype.system_prompt                                 # role
    + specialty_focus_block                                 # from per-agent config
    + role_reinforcement                                    # anti-convergence nudge
    + kpi_feedback_line                                     # last-turn rubric
    + citation_policy                                       # [src #N] must trace
)
user_msg = (
    f"GOAL: {goal}\n"
    f"TURN: {turn}\n"
    f"SOURCES (cite by [src #N]):\n{evidence_block}\n"
    f"HYPOTHESES IN PLAY (cite as [hyp #N]):\n{hyps_block}\n"
    f"RECENT CHANNEL POSTS:\n{feed_block}\n"
    f"Your task: post ONE tweet ...\n"
)
```

Size-bounded inputs (top-6 evidence, 6 hypotheses, 12 posts) keep each turn's prompt within ~2k tokens. This is the entirety of an agent's "memory" at posting time — everything else is retrieval.

### 3.2 Tier 2 — Project Blackboard

Schema (condensed):

```sql
CREATE TABLE blackboard_entries (
    id                INTEGER PRIMARY KEY,
    project_id        INTEGER NOT NULL,
    agent_id          INTEGER,              -- NULL for PI / ingested material
    kind              TEXT,                 -- evidence/hypothesis/critique/...
    content           TEXT,
    refs_json         TEXT,                 -- cited years, DOIs, author tokens
    turn              INTEGER,
    embedding_json    TEXT,                 -- 1024-dim qwen3-embedding
    echo_count        INTEGER DEFAULT 0,
    echo_refs_json    TEXT DEFAULT '[]',
    state             TEXT DEFAULT 'proposed',
    resolutions_json  TEXT DEFAULT '[]',
    visibility        TEXT DEFAULT 'visible'  -- 'visible' or 'held_out' for PGR
);
```

**Write path:**

1. `ingest.py` chunks PDFs/DOCX via MarkItDown. Each chunk becomes a `kind=evidence` row (`agent_id=NULL`). Hash-partitioned 80/20 into `visibility`.
2. Each simulation turn, `promote.py` files agent posts per the archetype → kind map:
   - scout → evidence · hypogen → hypothesis · experimenter → experiment
   - critic → critique · replicator → result · statistician → critique
   - writer → draft · reviewer → review
3. On insert, `dedup.add_entry_with_dedup` embeds the content, finds near-neighbors (cosine ≥ 0.85) in the same kind, and either creates a new row or increments `echo_count` on the canonical.
4. `lifecycle.resolve_hypothesis_refs` scans result/critique posts for `[hyp #N]` references and transitions the hypothesis state.

**Read path:**

- `retrieval.search_blackboard(project_id, query, top_k, kind, visibility)` is the one entry point. Returns `ScoredEntry(entry, score)` tuples. Default `visibility='visible'` — agents never see held-out chunks.
- `lifecycle.hypotheses_in_play` fetches open hypotheses for T1's prompt.
- `lifecycle.get_state_history(conn, project_id, hypothesis_id)` reconstructs the full chronological state trail of a hypothesis from `resolutions_json`. Each transition row captures `prev_state`, `new_state`, `verdict`, `turn`, `from_entry_id`, `agent_id`. Backward-compatible with legacy resolutions (reconstructed via verdict mapping).
- **Structured query helpers in `query_helpers.py`** — single-purpose read-only views that surface specific structural slices without forcing writer/reviewer to scan the whole blackboard:
  - `get_critiques_for(hypothesis_id)` — critiques targeting a hypothesis
  - `get_results_for(hypothesis_id)` — replicator results
  - `get_experiments_for(hypothesis_id)` — verification experiments
  - `get_supporting_evidence(hypothesis_id)` — evidence cited directly by the hypothesis or by results that confirmed it
  - `get_disagreements()` — productive tensions: hypotheses where a refute critique was logged but didn't terminate the hypothesis
  - `get_hypothesis_arc(hypothesis_id)` — composed view (hypothesis + critiques + results + experiments + evidence + state_history) in one call

These helpers borrow the **E6 lesson** (storage preserves history; query surface must expose it) without changing the substrate. New module added 2026-04-25.

### 3.3 Tier 3 — Per-User Wiki

Schema (condensed):

```sql
CREATE TABLE user_wiki_entries (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL,
    kind                TEXT,                 -- same taxonomy as T2
    content             TEXT,
    refs_json           TEXT,
    embedding_json      TEXT,
    source_project_id   INTEGER,
    promoted_score      REAL,
    t_ref               TEXT,                 -- ISO date: when claim is TRUE
    created_at          TEXT DEFAULT (datetime('now'))
);
```

**Write path:**

1. `wiki.promote_project_to_wiki` runs at end-of-run when rubric ≥ floor (default 3.0).
2. For each kind, pick top-K by `_score_entry` (weighted rubric × refs × echo × content length).
3. `_extract_t_ref(refs)` pulls the max year in [1900, 2099] from an entry's refs → `YYYY-01-01`. Entries without year-refs stay atemporal (`t_ref=NULL`).
4. Duplicate-content guard: exact content match on same user → skip.
5. Embedding copied from the blackboard entry (no re-embedding).

**Read path:**

- `wiki.search_wiki(user_id, query, top_k, kind, as_of)` — the one entry point.
- `as_of='YYYY-MM-DD'` filters to `t_ref <= as_of OR t_ref IS NULL`. Null t_refs are atemporal — always included.
- `wiki.seed_project_from_wiki` wraps `search_wiki` and files hits into a new project's blackboard as evidence with `refs=['source=user_wiki#N', ...]`.

## 4. Data Flow Diagrams

### 4.1 Write Path (ingest → blackboard)

```
  PDF / DOCX / HTML / MD / …
    │
    │  rp project ingest <id> <files>
    │
    ▼ MarkItDown.convert() → markdown
    │
    │  _chunk_markdown (split by heading, size-capped)
    │
    ▼ for each chunk:
    │    _is_held_out()        → visibility ∈ {visible, held_out}
    │    extract_refs()        → years, DOIs, arxiv ids, author tokens
    │    llm.embed("embedding") → 1024-dim vector (qwen3-embedding)
    │
    ▼ add_entry_with_dedup (cosine ≥ 0.85 → echo)
    │
    ▼ blackboard_entries (T2)
```

### 4.2 Write Path (promotion up the tiers)

```
  agent posts in channel_posts
    │
    │  end-of-turn hooks (run every turn):
    │    link_mentions          → parent_id backfill
    │    promote_project_posts  → archetype → kind
    │    resolve_hypothesis_refs→ state transitions
    │    snapshot_counters      → KPI bookkeeping
    │
    ▼ blackboard_entries (T2 grows)
    │
    │  [project finishes; judge_project scores rubric]
    │
    │  if rubric ≥ auto_promote_rubric_floor:
    │    promote_project_to_wiki(top_k_per_kind=3)
    │      for each kind: rank by _score_entry, take top-K
    │      _extract_t_ref(refs)
    │      dedup on exact content
    │
    ▼ user_wiki_entries (T3)
```

### 4.3 Read Path (per-agent per-turn)

```
  agent's turn in simulation._run_prompted_turn
    │
    ▼ _retrieve_evidence(project.goal, llm, top_k=6)
    │    → retrieval.search_blackboard
    │         filter: visibility='visible', kind='evidence'
    │    → [ScoredEntry with [src #N] anchors]
    │
    ▼ hypotheses_in_play(project_id, limit=6)
    │    → SELECT FROM T2 WHERE kind='hypothesis' AND state IN ('proposed','under_test')
    │    → [(hyp_id, state, content)]
    │
    ▼ _recent_posts_context(project_id, limit=12)
    │    → SELECT FROM channel_posts ORDER BY id DESC LIMIT 12
    │
    ▼ _recent_kpi_scores(project_id)
    │    → latest rubric row
    │
    ▼ composed T1 prompt
    │    → llm.achat(role='agent_bulk', messages=..., temperature=...)
    │
    ▼ _generate_unique_post (dedup retry if near-duplicate)
    │
    ▼ OASIS env.step with ManualAction(CREATE_POST)
```

### 4.4 Seed Path (T3 → new T2)

```
  new project created; user wants prior knowledge loaded
    │
    │  rp wiki seed <new_project_id>
    │
    ▼ seed_project_from_wiki:
    │    search_wiki(user_id, project.goal, top_k=6)
    │    [hits copied as kind=evidence into target blackboard]
    │    refs get "source=user_wiki#<entry_id>" prefix for traceability
    │    threshold=0.98 dedup (wiki content is already vetted)
    │
    ▼ blackboard_entries (T2) of the new project
```

## 5. The Karpathy Contribution

### 5.1 What we kept literally

| Karpathy gist concept | our implementation |
|---|---|
| `raw/` — immutable sources | `projects/{id}/raw/*.md` (MarkItDown output) |
| `wiki/` — LLM-compiled pages | `user_wiki_entries` table, kind-typed content |
| cross-linking via backlinks | `[src #N]` and `[hyp #N]` ref patterns in content |
| ingest op (compile sources) | `ingest.py` (+ promote to wiki) |
| query op (search + synthesize, file back) | `wiki.search_wiki` + `synthesize.py` artifacts |
| lint op (contradictions, orphans, stale) | partial: `dedup` + `lifecycle` + echo-clustering |
| persistent compounding | auto-promote on healthy runs + `rp wiki seed` |
| human-readable markdown | `render_wiki_markdown` + `rp wiki show` + the claims/hypotheses/experiments/decision/risks artifacts |

### 5.2 What we simplified / skipped

| Karpathy concept | why we skipped |
|---|---|
| separate `index.md` file | derivable from the table on demand; no distinct artifact |
| separate `log.md` file | `created_at` column + `source_project_id` covers the trace |
| Obsidian as the IDE | IDE choice is user's; we stay backend-agnostic |
| Obsidian Web Clipper | ingest via `rp project ingest` + MarkItDown replaces it |
| qmd local search | cosine embedding search covers BM25's role for our scale |
| Marp slide decks | out of scope for a research pipeline |
| Dataview plugin queries | SQL queries over the table cover equivalent needs |

We kept the **pattern** and the **principles** (LLM does bookkeeping, human curates, knowledge compounds). We skipped the specific toolchain because our pipeline is code-first, not markdown-file-first.

## 6. The Zep Contribution

### 6.1 What we stole

Exactly one thing: `user_wiki_entries.t_ref TEXT` column — Zep's reference-timestamp pattern applied to the wiki.

```python
def _extract_t_ref(refs: list[Any]) -> str | None:
    """Pull max year [1900, 2099] from refs; return 'YYYY-01-01' or None."""
```

Used in `wiki.search_wiki(as_of=...)` to filter by temporal precedence. Null `t_ref` = atemporal (always included).

### 6.2 What we refused to steal

| Zep feature | why we passed |
|---|---|
| bi-temporal model (T and T' timelines) | our single `t_ref` + `created_at` covers 80% at 5% cost |
| episode subgraph | T2 blackboard + `turn` column serves the role |
| semantic entity subgraph | we don't extract entities; retrieval is cosine over chunks |
| community subgraph (label propagation) | kind-typed clustering is sufficient at our scale |
| Graphiti / neo4j | local-first low-ops constraint; SQLite wins |
| structural extraction pipeline | MarkItDown + chunking is the extraction; we don't build KG nodes |
| query-time contradiction resolution | deferred (would live in `wiki.search_wiki` as a layer on top) |

## 7. The Graphify Contribution

[Graphify](https://github.com/safishamsi/graphify) (MIT) extracts knowledge graphs with provenance labels and structurally compresses them for downstream prompts. We integrate it as an optional KG view (`rp project kg <id>` shells out to Graphify's CLI) and we lifted two patterns into the core pipeline (both shipped 2026-04-25).

### 7.1 What we stole

| Graphify concept | our implementation |
|---|---|
| Per-edge `EXTRACTED` / `INFERRED` / `AMBIGUOUS` provenance label | `confidence TEXT NOT NULL DEFAULT 'EXTRACTED'` column on `blackboard_entries`. Plumbed through `add_entry_with_dedup`, `BlackboardEntry`, `query_helpers`. Per-archetype defaults in `promote.confidence_for(archetype, refs)`: scout → EXTRACTED; hypogen / critic / writer / reviewer → INFERRED; replicator dynamic (EXTRACTED if cites a DOI/arxiv/author-et-al, else INFERRED). `lowest_confidence([...])` helper for inheriting weakest label across cited sources. |
| Structural compression of a graph for prompt context | `blackboard_digest.render_digest(conn, project_id)` — markdown rollup (~500-800 tokens) of state matrix, top hypotheses by inbound-ref count, recent state transitions, open disagreements (via `query_helpers.get_disagreements`), recent results / surviving critiques, EXTRACTED:INFERRED:AMBIGUOUS confidence-mix ratio. Prepended to writer + reviewer prompts so they see the *shape* of the project, not just top-k cosine retrieval. |

### 7.2 What we refused to steal

| Graphify feature | why we passed |
|---|---|
| Full Obsidian/wiki-renderable graph store | `rp project kg` produces this on demand for inspection, but runtime queries stay on SQLite cosine — no graph traversal in the hot path |
| 71.5× compression target | meaningful only on much larger corpora than a single research project; structural digest at ~500-800 tokens already fits our scale |
| Tree-sitter AST extraction for code artifacts | deferred (roadmap §2.3) — our ingestion is overwhelmingly papers/docs, not code |
| Per-edge weighting of `pgr_cite` by confidence ratio | downstream consumer of the new `confidence` column; deferred until PGR refinement is the bottleneck |

## 8. The Compounding Loop

```
  project N ends with rubric ≥ floor
    │
    ▼ auto_promote_to_wiki → top-K per kind land in T3 with t_ref
    │
    │  [user starts project N+1 on a related topic]
    │
    ▼ rp wiki seed <N+1> (optional)
    │   → search_wiki finds relevant prior entries
    │   → filed into T2 with refs='source=user_wiki#<id>'
    │
    ▼ agents in project N+1 see prior knowledge in their T1 context
    │
    ▼ discussion builds on prior synthesis (doesn't start from zero)
    │
    ▼ project N+1 produces new claims/artifacts
    │
    ▼ auto_promote_to_wiki → T3 grows
    │
    └─> back to top
```

`--as-of` lets you collapse this cycle at any point and ask "what did T3 know at date X."

## 9. What the Architecture Deliberately Doesn't Do

- **No graph database.** All relationships are either cosine-similar (retrieval) or reference-based (`[src #N]`, `[hyp #N]`, `source=user_wiki#id`). No traversal, no edges, no inference over structure.
- **No entity extraction.** Chunks are the unit of knowledge. We don't build nodes for "Entity X" across sources.
- **No bi-temporal reasoning.** We have `t_ref` (when claim is TRUE) and `created_at` (when ingested). That's it. No T' transactional timeline, no temporal deltas, no state-change reasoning.
- **No shared memory across users.** T3 is per-user. Org-level wiki is phase-4.
- **No query-time contradiction repair.** If two T3 entries disagree (different `t_ref`, same concept), the retriever ranks by cosine — it doesn't pick a winner. The caller (Writer / Reviewer) must reconcile.
- **No streaming / real-time memory updates.** Writes happen at end-of-turn (batched). Good enough for research, wrong for conversational agents with live state.

## 10. What We've Measured (E1–E9 benchmark series, 2026-04-24/25)

Originally this section was titled "What We Haven't Proven" — a deliberate hedge against confusing implementation confidence with empirical evidence. **The 2026-04-24/25 benchmark series closed most of those gaps.** Full details in [agent-memory-benchmarks.md](./agent-memory-benchmarks.md); this section is the executive summary as it pertains to the architecture above.

### 10.1 What the hybrid was built on (recap)

1. The critic archetype's argument that Zep and Karpathy both pay a write-time LLM-drift tax.
2. `$t_{ref}$` was judged Zep's single most useful capability for our context.
3. Karpathy's structure was judged the better fit for local-first, low-ops, compounding research.
4. **Steal the one useful capability; don't adopt the losing side wholesale.**

### 10.2 The hybrid IS validated for the wiki workload

E4 (10-doc Alpha Corp corpus, 3 embedded contradictions, 6 queries split current / temporal):

| system | current | temporal | overall | ingest |
|---|---|---|---|---|
| our hybrid (Karpathy + t_ref) | 3/3 | 2/3 | **5/6** (one substring-scoring miss; semantically correct) | **2.6s** |
| zep_lite (full TKG) | 3/3 | 3/3 | 6/6 | 20.1s (~8× more) |
| karpathy_lite (LLM-compiled summaries) | 3/3 | 1/3 | 4/6 | 16.5s |

**Verdict:** the hybrid is the Pareto winner on this regime — near-zep correctness at 8× cheaper writes. The "we don't know if `t_ref` heuristic misfires" concern from the original §9 was not manifested at E4's scale.

### 10.3 The hybrid is NOT the right tool for blackboard attribute churn

E1 (60 docs, 3 entities × 20 attribute updates each, queries for "current value"):

- our hybrid (chunks-only): 1/3 (the one pass was likely luck)
- mem0 (overwrite consolidation): 3/3 at 44s
- zep, supermemory, m-flow: all 3/3, costlier ingest

But **our actual blackboard workload is not E1's pattern** (kind-typed append-only entries, not high-velocity attribute updates on a single entity). E1 is a stress test for a workload we don't have. See [agent-memory-decisions.md §1.2](./agent-memory-decisions.md) for the disposition.

### 10.4 The substrate is correct; the query surface needed enrichment

E6 (cross-entity temporal queries): zep_lite and m_flow_lite both stored full history but their default query surfaces collapsed to latest-per-key — both scored 0/3 until "Rich" variants exposed full history (2/3). This is the **storage-vs-query-surface lesson**: preserving information at write isn't enough; the query layer must surface it.

We applied this lesson to ourselves in 2026-04-25's targeted improvements:

- **Hypothesis state history** (§3.2 read path) — `resolutions_json` was already append-only; we just needed a helper (`get_state_history`) to expose the chronology with `prev_state → new_state` framing.
- **Structured query helpers** — `query_helpers.py` exposes single-purpose views (`get_critiques_for`, `get_disagreements`, `get_hypothesis_arc`, etc.) so the writer/reviewer don't pattern-match the entire blackboard.

No substrate change was needed; only six new helper functions and one audit-log enrichment.

### 10.5 What the architecture deliberately does NOT do, validated

The original §8 listed deliberate non-goals (no graph DB, no LLM compilation, no bi-temporal model, etc.). E1-E9 confirmed:

- **No graph DB needed** at our scale (60-400 triples). Zep_rich on a flat triple store hit 9/9 on E9's cross-thread workload — no graph required for the patterns we care about.
- **Intent routing is unnecessary at our scale** (E8 + E9 confirmed). Below ~500 triples, exposing all history to a frontier-class LLM works as well as any router.
- **At production scale (~9000+ triples/month), routing becomes necessary for cost** — but that's a Claude-Code-style platform-memory problem, not a research-pipeline-product problem. Our typical project produces 50-200 entries.

### 10.6 What remains untested

- **E10 — scale-out (1k / 5k / 10k triples)** to find where zep_rich's "expose all" approach breaks down on cost or accuracy. Out of scope for the pipeline product (we never reach this scale) but valuable for the broader agent-memory research direction.
- **E11 — uncertainty calibration** ("I don't know" vs hallucination). Every system in our suite has this gap; we haven't tested ourselves on it.
- **Real commercial SDK comparisons.** Our "Lite" variants are 50-150 LOC reimplementations.

### 10.7 Honest framing now

- **What we can say with evidence**: the Karpathy+Zep hybrid is the right wiki architecture for our workload — E4 measured it. The blackboard substrate is correct for our workload (kind-typed append-only) — its closest stress test (E1) doesn't match our actual pattern. The structured query helpers added 2026-04-25 are an instance of the E6 lesson (substrate retains, surface must expose) applied to us specifically.
- **What we cannot say**: that any of this scales to production agent-platform memory (Claude Code / Work). The workloads are different and our scale is much smaller. Cross-pollination of architectural ideas only flows in one direction — research-pipeline-tested patterns don't auto-promote to general-purpose memory.

## 11. Extension Points (future)

- **Verification loop** (future): `runnable_json` column on `blackboard_entries` for `kind=experiment` rows; orchestrator executes in sandbox; results flow back as `kind=result` rows that trigger `lifecycle.resolve_hypothesis_refs`.
- **Org-level wiki**: `user_id → org_id` foreign key change on T3; `search_wiki(org_id=...)` as new default scope. All wiki CLI commands gain `--org` flag.
- **Query-time contradiction repair**: when `wiki.search_wiki` returns two near-cosine hits with different `t_ref`, a resolver step (LLM or rule) picks the later one and flags the conflict. Would live as a post-processing step inside `search_wiki`.
- **Entity extraction** (if ever needed): add `entities_json` column to T2; use at retrieval time for "show me all entries mentioning entity X." Adds a small KG-like capability without adopting a KG database.

## 12. Reference Map

| concept | table | module | key functions |
|---|---|---|---|
| T1 working memory | — | `simulation.py` | `_run_prompted_turn`, `_retrieve_evidence`, `_recent_posts_context`, `_recent_kpi_scores`, `hypotheses_in_play` |
| T2 project blackboard | `blackboard_entries`, `channel_posts` | `blackboard.py`, `promote.py`, `dedup.py`, `lifecycle.py`, `retrieval.py`, `query_helpers.py` | `add_entry`, `list_entries`, `add_entry_with_dedup`, `resolve_hypothesis_refs`, `get_state_history`, `get_critiques_for`, `get_supporting_evidence`, `get_disagreements`, `get_hypothesis_arc`, `search_blackboard`, `promote_project_posts` |
| T3 long-term wiki | `user_wiki_entries` | `wiki.py` | `promote_project_to_wiki`, `search_wiki`, `seed_project_from_wiki`, `render_wiki_markdown`, `_extract_t_ref`, `_score_entry` |
| Optimize loop | `optimization_traces` | `optimize.py`, `iteration_summary.py` | `optimize_project`, `propose_adjustment`, `apply_adjustment`, `write_iteration_summary`, `write_optimization_index` |
| Ingestion | — | `ingest.py` | `ingest_file`, `_chunk_markdown`, `_is_held_out` |
| Embeddings | — | `adapter.py` | `LLMClient.embed`, `LLMClient.aembed` |

## 13. One-Sentence Summary

**Three cosine-searchable tiers of markdown-like content, with kind-typed per-project memory promoting to a temporally-indexed per-user wiki on healthy runs, persisted in SQLite, with no graph database, no custom entity extraction, and the Karpathy wiki pattern as the structure + Zep's `$t_{ref}$` as the one stolen temporal capability.**

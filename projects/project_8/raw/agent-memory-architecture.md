# Agent Memory Architecture

*As-built reference for the three-tier hybrid memory in research-pipeline. Updated 2026-04-23 with the Karpathy + Zep hybrid.*

## 1. Overview

Three cosine-searchable tiers of markdown-like content, with kind-typed per-project memory promoting to a temporally-indexed per-user wiki on healthy runs. All persisted in SQLite. No graph database, no separate vector store, no custom extractor beyond MarkItDown.

The architecture borrows structure from Karpathy's LLM Wiki pattern (markdown-first, human-readable, compounding) and a single capability from Zep's temporal knowledge graph (`$t_{ref}$` as a time anchor per entry).

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
| query-time contradiction resolution | deferred to phase 4 (would live in `wiki.search_wiki` as a layer on top) |

## 7. The Compounding Loop

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

## 8. What the Architecture Deliberately Doesn't Do

- **No graph database.** All relationships are either cosine-similar (retrieval) or reference-based (`[src #N]`, `[hyp #N]`, `source=user_wiki#id`). No traversal, no edges, no inference over structure.
- **No entity extraction.** Chunks are the unit of knowledge. We don't build nodes for "Entity X" across sources.
- **No bi-temporal reasoning.** We have `t_ref` (when claim is TRUE) and `created_at` (when ingested). That's it. No T' transactional timeline, no temporal deltas, no state-change reasoning.
- **No shared memory across users.** T3 is per-user. Org-level wiki is phase-4.
- **No query-time contradiction repair.** If two T3 entries disagree (different `t_ref`, same concept), the retriever ranks by cosine — it doesn't pick a winner. The caller (Writer / Reviewer) must reconcile.
- **No streaming / real-time memory updates.** Writes happen at end-of-turn (batched). Good enough for research, wrong for conversational agents with live state.

## 9. What We Haven't Proven

**The hybrid is a design argument with working code and unit tests. It is not a validated architecture.** No head-to-head comparison against pure Karpathy or pure Zep has been run. This section names that gap honestly so future readers don't mistake the confidence of the implementation for evidence that it wins.

### 9.1 What the hybrid was built on

1. The critic archetype's argument that Zep and Karpathy **both pay a write-time LLM-drift tax** (project 6, `[crit #324]`).
2. The judgment that `$t_{ref}$` is **Zep's single most useful capability** for our context — all other Zep features require a graph database we don't want to run.
3. The judgment that Karpathy's structure is **the better fit for local-first, low-ops, compounding research** — Zep's production orientation doesn't match single-user single-laptop scale.
4. The pattern: **steal the one useful capability; don't adopt the losing side wholesale**.

Each link in that chain is plausible. **None was tested.** Project 6's `decision.md` explicitly called for the E4 Query-Time Repair experiment before picking a winner. We built the hybrid anyway because the argument felt strong.

### 9.2 What would actually be proof

A controlled experiment over the same corpus, comparing three systems:

```
  Same source corpus (e.g. 30 chronologically-ordered papers)
    System A: pure Karpathy LLM Wiki
    System B: pure Zep TKG (or faithful reimplementation)
    System C: ours (Karpathy + t_ref)
      │
      ▼ inject N temporal contradiction events (doc_15 supersedes claim in doc_10)
      │
      ▼ run standard query set: "what is the current state of X?"
      │
      ▼ measure per system:
          currency       — fraction returning the latest correct answer
          propagation    — downstream queries affected per contaminated entity
          retrieval cost — $/query + storage overhead
          human-readability — side task: can a new user navigate the store?
      │
      ▼ winner per axis, no winner-take-all
```

Minimum viable version: 10 docs, 3 contradiction events, 5 queries per system, single trial. Would demonstrate the *capability* on one benchmark, not prove it across domains.

**We have not run even the minimum viable version.** No numbers behind the architecture, on any axis, for any corpus.

### 9.3 Specific ways the hybrid could be worse

| failure mode | worse than Karpathy | worse than Zep |
|---|---|---|
| `t_ref` heuristic misattributes dates (publication year ≠ claim-valid-year) | ✅ pure Karpathy doesn't pretend to handle time — no wrong answers about when | — |
| no lint / contradiction-detection pass | ✅ canonical Karpathy lints as a first-class op; we only have embedding dedup | — |
| raw chunk storage vs compiled wiki pages | ✅ canonical Karpathy has the LLM compile raw sources into entity pages; we store chunks and skip the compilation step | — |
| no bi-temporal T' transactional timeline | — | ✅ can't reason about "we learned X at time T₂ but X was valid at T₁" |
| no entity extraction / node traversal | — | ✅ can't query "everything about entity X" as graph traversal |
| no relative-time resolution ("two weeks ago") | — | ✅ Zep resolves these; our `t_ref` is a static date tag, not a reasoner |
| no state-change tracking at entity level | — | ✅ Zep tracks entity state transitions; we only track hypothesis lifecycle in T2 |
| added complexity without measured payoff | ✅ | ✅ |

Any one of these could be the dominant term on a real task. We don't know which.

### 9.4 Fair framing

- **What we can say honestly**: the hybrid is a reasonable bet given our stated constraints (local-first, single-user, research compounding, no ops budget for a graph DB). The `--as-of` filter provides a capability pure Karpathy lacks, at the cost of ~30 lines of code and 9 unit tests.
- **What we cannot say honestly**: that it's "superior" to either pure approach. No measurement supports that claim.
- **What's at stake if it's actually worse**: if `t_ref` heuristic misfires frequently, the `--as-of` filter returns wrong answers silently. We don't know the misfire rate.

### 9.5 How to close the gap

Three paths, ranked by cost:

1. **Keep this section up to date** (0.1 days). Re-read every time someone asks "is this better?" — don't let implementation confidence leak into architectural claims.
2. **Build a minimum viable E4 benchmark** (1 day). Toy corpus of 10 docs, 3 injected contradictions, 5 queries. Measure currency only. Under-powered but produces *some* evidence. Persist as `benchmarks/e4_query_time_repair/` so future runs can compare.
3. **Build a serious benchmark suite** (phase 4, multi-week). Requires reference implementations of pure Karpathy compilation and a Zep-like minimal TKG. Measurement on currency, propagation, cost, and readability. This is the only thing that earns the word "superior."

Path 1 is this section itself. Path 2 is the natural first phase-4 task.

## 10. Extension Points (phase 4+)

- **Verification loop** (phase 4 proposal): `runnable_json` column on `blackboard_entries` for `kind=experiment` rows; orchestrator executes in sandbox; results flow back as `kind=result` rows that trigger `lifecycle.resolve_hypothesis_refs`.
- **Org-level wiki**: `user_id → org_id` foreign key change on T3; `search_wiki(org_id=...)` as new default scope. All wiki CLI commands gain `--org` flag.
- **Query-time contradiction repair**: when `wiki.search_wiki` returns two near-cosine hits with different `t_ref`, a resolver step (LLM or rule) picks the later one and flags the conflict. Would live as a post-processing step inside `search_wiki`.
- **Entity extraction** (if ever needed): add `entities_json` column to T2; use at retrieval time for "show me all entries mentioning entity X." Adds a small KG-like capability without adopting a KG database.

## 11. Reference Map

| concept | table | module | key functions |
|---|---|---|---|
| T1 working memory | — | `simulation.py` | `_run_prompted_turn`, `_retrieve_evidence`, `_recent_posts_context`, `_recent_kpi_scores`, `hypotheses_in_play` |
| T2 project blackboard | `blackboard_entries`, `channel_posts` | `blackboard.py`, `promote.py`, `dedup.py`, `lifecycle.py`, `retrieval.py` | `add_entry`, `list_entries`, `add_entry_with_dedup`, `resolve_hypothesis_refs`, `search_blackboard`, `promote_project_posts` |
| T3 long-term wiki | `user_wiki_entries` | `wiki.py` | `promote_project_to_wiki`, `search_wiki`, `seed_project_from_wiki`, `render_wiki_markdown`, `_extract_t_ref`, `_score_entry` |
| Ingestion | — | `ingest.py` | `ingest_file`, `_chunk_markdown`, `_is_held_out` |
| Embeddings | — | `adapter.py` | `LLMClient.embed`, `LLMClient.aembed` |

## 12. One-Sentence Summary

**Three cosine-searchable tiers of markdown-like content, with kind-typed per-project memory promoting to a temporally-indexed per-user wiki on healthy runs, persisted in SQLite, with no graph database, no custom entity extraction, and the Karpathy wiki pattern as the structure + Zep's `$t_{ref}$` as the one stolen temporal capability.**
# Phase 1 Wrap-up & Phase 2 Proposal

*Date: 2026-04-21.*

## 1. What's Built

A full research-pipeline MVP, 45 passing tests, shipped end-to-end over 2 working days.

### Stack

| layer | tech | why |
|---|---|---|
| LLM adapter | `openai` SDK against any OpenAI-compatible endpoint | local-first (vLLM, Ollama), hosted-compatible, provider-agnostic |
| Embeddings | qwen3-embedding:0.6b via Ollama (1024-dim) | dedup, retrieval, diversity KPI |
| Simulation | CAMEL-AI OASIS (Apache-2.0) via `ModelPlatformType.OPENAI_COMPATIBLE_MODEL` | Twitter platform for state; our own prompted turn loop for control |
| Persistence | SQLite with idempotent ALTER TABLE migrations | single-file, zero-ops |
| Ingest | Microsoft MarkItDown (PDF/DOCX/PPTX/HTML → markdown) | one tool, all formats |
| Frontend | FastAPI + embedded single-page HTML + SSE | no build step, live feed |
| Packaging | uv + pyproject.toml | reproducible |

### Feature Matrix

| capability | CLI | dashboard |
|---|---|---|
| adapter probe (chat & embed) | `rp probe [role]`, `rp probe-embed` | `/health` |
| project CRUD | `rp project create/list/run` | picker, auto-refresh |
| agent selection | `rp project plan`, `--archetypes auto/all` | — |
| ingest PDFs | `rp project ingest <id> files…` | (next: web upload) |
| simulation | `rp project run <id> --turns N --reddit-every M` | live SSE feed |
| HITL | `rp project pi-post`, `rp project redirect` | PI-post input |
| Reddit threads | `rp project reddit-round <id>` | channel tab, threaded rendering |
| blackboard | `rp project blackboard <id>` | grouped by kind, state badges, citation chips |
| report | `rp project report <id>` (with revision loop) | link from export |
| per-user wiki | `rp wiki promote/show/search/seed` | (next: wiki pane) |
| KPI | rubric + counters per turn | sparklines for trajectory |
| hypothesis lifecycle | `[hyp #N]` refs → `proposed → supported/refuted` | color-coded state badges |
| knowledge graph | `rp project kg <id>` (graphify) | static html output |
| export | `rp project export <id>` → zip | — |

### Architecture at a Glance

```
                      +----------------------+
                      |  user Karpathy wiki  |
                      |  (promoted entries)  |
                      +----------+-----------+
                                 | seed/promote
                                 v
  +-------------+   +------------+-------------+   +----------------+
  |  PDFs etc.  +-> |   project blackboard     | <-+  channel posts |
  |  MarkItDown |   |  (kind=evidence/...)     |   |  (Twitter+Reddit) |
  +-------------+   +------------+-------------+   +-------+--------+
                                 ^                         ^
                                 | promote (embedding dedup)
                                 |                         |
                             +---+-------+        +--------+------+
                             |  prompted |        |  OASIS state  |
                             |  turn loop| ------>|  (post table) |
                             +-----+-----+        +---------------+
                                   |
                                   v
                       +-----------+---------+
                       | Writer -> Reviewer  |
                       | (revision loop)     |
                       +-----------+---------+
                                   v
                              report.md
```

## 2. What Works Well

- **Grounded citations**: agents cite `[src #N]` from actual ingested chunks, not hallucinated references. Citation quality jumped from 1–2/5 (phase-1 start) to 5/5 (after Zep PDF ingest).
- **Role divergence preserved**: `seed_angle` per archetype + KPI-feedback loop keeps scout/hypogen/critic distinct across turns. Anthropic AAR "convergence collapse" problem observed and fixed empirically.
- **Post-level dedup**: verbatim copies caught and regenerated with higher temperature + anti-dup nudge.
- **Compounding**: `rp wiki promote` (or auto-promote on healthy runs) builds a growing library; `rp wiki seed` pre-loads new projects from prior learning.
- **Hypothesis lifecycle**: `[hyp #N]` references trigger state transitions. Real example from project 2: `[hyp #193]` transitioned `proposed → refuted` across 3 turns of critic rebuttals.

## 3. What's Weak

1. **Per-user, not org-level wiki.** Currently `user_wiki_entries` is keyed by `user_id`. A research group can't share accumulated knowledge across members.
2. **All agents share identical config.** Temperature, max_tokens, context size — no per-agent specialization. The `weight` field in the `agents` table is unused in the runtime.
3. **No per-agent rubric.** Judge scores the project as a whole (relevance, novelty, rigor, citation). Individual agent quality is counters-only (posts, entries).
4. **Single-shot simulation, no optimization.** We run N turns, record metrics, stop. There's no loop that uses KPIs to *adjust* and re-run.
5. **Output is a report, not a result.** The Writer produces prose. The "meaningful research result" — a falsifiable claim, an experimental protocol, a decision with predicted outcome — isn't a first-class artifact.
6. **Promote classifier is archetype-based.** A hypogen post saying "I refute [hyp #X]" still files as `hypothesis`. Should detect refute patterns and route to `critique`.
7. **Keyword lifecycle classifier is conservative.** Nuanced refutations ("architectural fallacy", "leap of faith" — now caught; but not "the first-order effect is dominated by…") fall through to neutral.
8. **No web-based ingest.** PDFs must go through the CLI.
9. **No integration test.** 45 unit tests cover pieces; no golden-path test with a fake LLM over a fake corpus.

## 4. The Re-iterated Vision

From the user, 2026-04-21:

> Organisation level knowledge base using Karpathy's approach, which can be used by each project. On the project level: seed documents, project brief and research goals, form agent team according to the research goal, generate configuration the agent team, KPIs for each agent and KPIs for the agent team, running simulations to optimise KPIs, the generation reports. **The key is to produce meaning research result, not just a report.**

### Mapping the vision to current state

| Vision element | Current state | Gap |
|---|---|---|
| **Org-level knowledge base** | Per-user wiki only | Add `orgs` table; wiki keyed by `org_id`; users belong to orgs |
| **Seed documents** | ✅ `rp project ingest` | Also: seed from wiki (`rp wiki seed`) already exists |
| **Project brief + research goals** | ✅ project goal | Need richer brief: scope, success criteria, budget, deadline |
| **Form agent team per goal** | ✅ `rp project plan` (weighted archetype subset) | Planner outputs identical-config agents |
| **Generate config for agent team** | ❌ | Per-agent temperature, max_tokens, specialty, token-budget |
| **KPIs per agent** | Counters only (posts/entries/citations) | Rubric per agent; delta vs team average |
| **KPIs for agent team** | ✅ rubric + counters + diversity/echo | Healthy; trajectory charts in place |
| **Run simulations to optimise KPIs** | ❌ single-shot | Optimization loop: run → score → reconfigure weak agents → re-run |
| **Generate reports** | ✅ Writer + Reviewer with revision loop | Prose only |
| **Produce meaningful research results** | ❌ report is the terminal artifact | Structured artifacts: claim cards, experiment cards, decision matrix, risk register |

## 5. Proposed Phase 2 Roadmap

Ranked by research impact.

### Tier A — Pipeline evolution

**A1. Organisation layer** *(foundational)*

- New table `orgs(id, name, created_at)`
- `users.org_id` references `orgs.id`
- `user_wiki_entries` becomes `org_wiki_entries(org_id, …)`
- All wiki CLI commands gain `--org` flag (default: user's org)
- Migration path: create default org "personal", assign all existing users to it

**A2. Agent team configuration**

- New columns on `agents`: `temperature REAL`, `max_tokens INT`, `specialty_focus TEXT`, `token_budget INT`
- Planner output extended to include per-agent config (not just {id, weight})
- `_run_prompted_turn` reads each agent's config when generating
- CLI: `rp project agents <id>` to inspect/tune

**A3. Per-agent rubric**

- New `snapshot_agent_rubrics` in kpi.py that asks the judge to score each agent separately (relevance, novelty, rigor of *their* contributions)
- Extend `kpi_scores` rows with `agent_id NOT NULL` for per-agent rubric
- Dashboard adds per-agent KPI mini-panel per archetype

**A4. Optimization loop** *(the biggest)*

- New command: `rp project optimize <id> --iterations N --budget-tokens M`
- Each iteration: short sim (1-2 turns) → judge → identify weakest agent(s) by rubric → adjust (lower temperature for low-rigor, change specialty for low-relevance) → next iteration
- Terminate on KPI plateau or budget exhaustion
- Record the config delta + KPI delta as the optimization trace
- Deliverable: best agent team config, reproducible

### Tier B — Results beyond reports

**B1. Structured result artifacts**

Instead of one `report.md`, produce a bundle under `projects/{id}/artifacts/`:

- `claims.md` — one falsifiable claim per line with confidence + evidence refs + falsifier
- `hypotheses.md` — the hypothesis matrix (id, state, supporting/refuting entries)
- `experiments.md` — proposed verification experiments (one per leading hypothesis)
- `decision.md` — single recommended next action with predicted outcome
- `risks.md` — top 5 risks to the recommended direction

New module `synthesize.py` with one Writer call per artifact (each with a schema-locked prompt).

**B2. Verification loop** *(stretch)*

For `supported` hypotheses, the Experimenter archetype proposes a concrete verification test. If the test is *runnable* (e.g. a specific calculation, a numerical check against the evidence), execute it via a sandboxed code tool. If the test passes → promote state to `verified`; if it fails → downgrade to `refuted`.

### Tier C — Hygiene

**C1. Promote classifier refinement** — detect refute patterns in post text; route to `critique` even when archetype is hypogen.

**C2. LLM verdict classifier fallback** — on neutral-via-keywords, ask the judge: "Does this text support, refute, or remain neutral on this hypothesis?"

**C3. Integration test** — fake LLM, fake corpus, end-to-end one-turn sim with assertions on blackboard + report shape.

**C4. Web ingest** — dashboard drag-and-drop → `/api/projects/{id}/ingest`.

**C5. Multi-model demo** — `models.toml` with planner+judge on Claude, bulk on Gemma, verify it works.

## 6. Recommendation

If you want to keep the philosophical spirit — "**meaningful research results, not just reports**" — the highest-leverage sequence is:

1. **A4 optimization loop** — turns the pipeline from a one-shot simulator into something that actively improves
2. **B1 structured artifacts** — makes the output consumable as inputs for real research work, not decoration
3. **A3 per-agent rubric** — prerequisite that enables A4 (need to know which agent to adjust)

A1/A2 (org + per-agent config) are foundational but not research-valuable on their own; defer until you have a second user or a concrete need for specialty tuning.

B2 verification is aspirational and the right direction, but gated by having a code-execution sandbox — phase 3.

## 7. Known Bugs to Clean Up

- hypogen promotes "I refute [hyp #X]" posts as new hypotheses (should be critiques) — C1 above
- writer/reviewer mid-run posts sometimes frame for end-of-run reporting context
- rubric ceiling at 5 means healthy runs plateau quickly; consider a finer-grained scale for discriminating excellent runs
- OASIS emits `twhin-bert-base` recsys errors on cold cache (non-fatal, noisy)

## 8. How to Resume

```bash
cd research-pipeline
uv sync --extra sim --extra dev --extra ingest
uv run pytest        # 45 green
uv run rp serve      # dashboard at http://127.0.0.1:8765/
```

Or resume a project:
```bash
uv run rp wiki show                           # see compounded knowledge
uv run rp project plan --goal "…" --n 5      # plan a new team
uv run rp project create --goal "…" --archetypes auto
uv run rp project ingest <id> paper1.pdf paper2.pdf
uv run rp project run <id> --turns 3 --reddit-every 3
```

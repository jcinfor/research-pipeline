# Changelog

All notable changes to `research-pipeline` (`rp`).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once a 1.0 is published.

## [Unreleased]

### Changed — `rp_run_optimize` / `rp project optimize` default objective: `rubric` → `pgr`

The optimization loop now defaults to `objective="pgr"` (citation-trace + held-out evidence + adversarial Red Team) instead of `objective="rubric"`. Motivated by the project-15 self-learning research findings: the rubric objective is pure model-as-judge in the same training distribution as the agents being scored, structurally susceptible to the co-evolutionary collapse the matrix's claims C2/C3 warn about. PGR is a Cross-Modal Anchor — verifies against source-document chunks, a different modality than agent prose — which is the v3 architecture recommendation for verifier design.

- The lazy-synthesize preflight was already in place: if `claims.md` is missing on the first PGR iteration, synthesize is run automatically. No behavior change there.
- `objective="rubric"` is preserved as an explicit opt-in for smoke-tests / fast iteration where PGR's per-iteration scoring cost isn't worth it. Pass `--objective rubric` (CLI) or `objective="rubric"` (Python / MCP).
- Affected surfaces: `optimize_project()` Python API, `rp_run_optimize` MCP tool, `rp project optimize` CLI. The Skill body and `docs/integrations/mcp-server.md` updated to recommend the new default.
- See `docs/internal/findings-derived-prs.md` PR 1 for the full rationale and roll-out plan.

## [0.3.0] — 2026-05-06

Closes the v0.3.0 plan from [docs/internal/rp-mcp-server-plan.md](docs/internal/rp-mcp-server-plan.md): the rp MCP server now exposes the **full pipeline** as MCP tools, with the long-running operations (simulation, optimize, synthesize) routed through an async job-id pattern that handles MCP client timeouts cleanly. The agent can now drive *ingest → run_simulation → run_optimize → synthesize → get_artifacts* without leaving the conversation, polling `rp_get_status` between async stages.

### Added — three new async MCP tools

- `rp_run_simulation` — start a simulation as a background job. Returns `{job_id, status: 'queued'}` immediately. Args: `turns` (default 3), `reddit_every` (default 0).
- `rp_run_optimize` — start the optimization loop. Returns `{job_id, status: 'queued'}` immediately. Args: `iterations` (default 3), `turns_per` (default 2), `objective` (`'rubric'` | `'pgr'`, default `'rubric'`), `plateau_patience` (default 2).
- `rp_synthesize` — produce the five structured artifacts. Returns `{job_id, status: 'queued'}` immediately. Single arg: `project_id`.

All three follow the same shape: synchronous pre-check (project exists + agents assigned + valid args), structured `{error: 'project_in_use', active_job_id, hint}` response when concurrency-forbid trips, otherwise `{job_id, ...}` returned within ~100ms while the runner executes in the background.

### Added — `rp_get_status` extended

`rp_get_status` now surfaces job state alongside the existing project state:

- `active_job`: the current queued/running job for this project, with progress fields (`current_step`, `progress_pct`) — or `null` if idle.
- `recent_jobs`: up to 5 most-recent jobs (any status), newest first.

The agent's polling pattern: submit async job → poll `rp_get_status(project_id)` → when `active_job.status` is terminal (`complete`/`failed`/`cancelled`/`orphaned`), proceed.

### Added — async-job infrastructure

- `src/research_pipeline/jobs.py` — standalone `JobManager` + `ProgressReporter` + SQLite-backed persistence. In-process asyncio task tracking; concurrency invariant enforced at submission (one active job per project); orphan cleanup at server start (stale `running` rows from prior process pids get marked `orphaned`).
- `jobs` table added to schema with indexes on `(project_id, status)` and `(status)`.
- 18 tests under `tests/test_jobs.py` pinning the defining invariants: monotonic status transitions, concurrency-forbid, sync-in-db cancellation (status set BEFORE task.cancel() so racing progress updates can't undo it), orphan cleanup, shutdown-orphans-running-tasks.

### Updated — Skill body teaches the async pattern

[.claude/skills/rp/SKILL.md](.claude/skills/rp/SKILL.md) now teaches the agent the polling cadence (~30s first check, then every 60-120s, surface meaningful transitions only, don't busy-loop in a single response turn) and how to handle terminal-state edge cases (failed → surface error verbatim and offer retry; orphaned → ask user before re-submitting). The "two-mode" section now explicitly recommends MCP for the async ops since the shell fallback blocks the conversation.

### Notes

- Concurrency invariant is **project-level, not kind-level**: a simulation in flight blocks both optimize AND synthesize submissions for the same project. Tested in both directions across all three async tools.
- Module-level imports of `simulation`, `optimize`, `synthesize` use the `from . import X` pattern (not `from .X import f`) so test monkey-patches on `mcp_server.X.f` take effect at runner-call time.
- 321 fast tests pass (was 293 in v0.2.0). 5 phase-2.2 tests + 5 phase-2.3 tests + 18 phase-2.1 jobs tests added.

### Coming in v0.4.0

- Resource URIs (`rp://projects/{id}/artifacts/{name}`) for clients that prefer URI-based fetches.
- SSE progress streaming for clients that support it (richer than poll-based).
- Per-project `delete` tool with audit-log preservation.

## [0.2.0] — 2026-04-30

Adds two new distribution surfaces for `rp`:

1. An **MCP server** so any MCP-aware client (Claude Code, OpenCode, OpenClaw, Cline, Cursor, Goose) can drive the pipeline directly. See [docs/integrations/mcp-server.md](docs/integrations/mcp-server.md) for the registration recipe.
2. A **Claude Skill** at [`.claude/skills/rp/`](.claude/skills/rp/) so Claude Code agents working in this repo (or with the skill installed user-wide at `~/.claude/skills/rp/`) get pre-baked methodology — when to invoke the rp tools, the canonical workflow, and how to present the five artifacts back to the user.

The MCP server gives the agent *access* to rp's tools; the Skill gives it *methodology* for when and how to use them. They're complementary; both ship in v0.2.0.

> **Terminology note.** MCP is the open Model Context Protocol; "Claude Skill" is Anthropic's packaged-capability format (`SKILL.md` + instructions). They're distinct things — earlier drafts of this changelog conflated them.

### Added

- `rp mcp serve` — MCP server over stdio, exposes the pipeline as five tools.
  - `rp_list_projects` — list projects with id, goal, status, archetypes.
  - `rp_create_project` — create with goal + archetypes (Phase-1 default subset, `["all"]`, or an explicit list).
  - `rp_ingest` — convert + chunk + embed a document into a project's blackboard.
  - `rp_get_status` — full project state including blackboard counts and which artifacts are on disk.
  - `rp_get_artifacts` — fetch synthesized artifact bodies inline (markdown).
- [.claude/skills/rp/SKILL.md](.claude/skills/rp/SKILL.md) — project-scoped Claude Skill teaching the agent when to reach for rp, the canonical workflow, the artifact-presentation pattern, and what *not* to do (e.g. don't burn 30 minutes on a multi-agent simulation when the user just wants a quick summary).
- [.claude/skills/rp/examples/canonical-flow.md](.claude/skills/rp/examples/canonical-flow.md) — worked example: user uploads three papers, gets a hypothesis matrix.
- [.claude/skills/rp/examples/resume-existing-project.md](.claude/skills/rp/examples/resume-existing-project.md) — worked example: resuming a prior project with a new paper.
- [docs/integrations/mcp-server.md](docs/integrations/mcp-server.md) — Claude Code registration recipe, troubleshooting, what's coming in v0.3.0.
- 12 tests under `tests/test_mcp_server.py` covering tool registration, the round-trips, validation errors, and the on-disk artifact discovery path.

### Changed

- `mcp>=1.0` is now a runtime dependency (was previously a dev-extra by inheritance).
- README leads with the MCP integration as a first-class surface.

### Coming in v0.3.0

- Async tools for long-running ops (`rp_run_simulation`, `rp_run_optimize`, `rp_synthesize`) via the job-id pattern.
- Resource URIs (`rp://projects/...`) for clients that prefer URI-based fetches over inline content.
- Progress streaming via SSE for clients that support it.

## [0.1.0] — 2026-04-29

First public release. The pipeline product (provider-agnostic LLM adapter, 8 agent archetypes, OASIS-backed simulation with prompted-turn loop, optimization loop with per-agent rubric, five structured artifacts, live SSE dashboard) and the agent-memory benchmark suite (LoCoMo + LongMemEval + 14 in-house stress tests, comparing eight in-house architectures against the actual current mem0 v3 product in both default-install and full-nlp-extras configurations) are stable and reproducible. See [BENCHMARKS.md](BENCHMARKS.md) for the empirical comparison and [docs/architecture.md](docs/architecture.md) for the three-tier memory design.

### Added
- `EpistemicPrototype` and `GapAwarePrototype` — research-extension memory variants. Both subclass `PrototypeMemory`. See [docs/agent-memory-prototype-innovations.md](docs/agent-memory-prototype-innovations.md).
- Both variants registered across all 14 in-house stress tests + LongMemEval + LoCoMo benchmarks.
- `MultiTierMemory` registered in benchmarks where it was previously missing.
- `BENCHMARKS.md` headline doc aggregating LoCoMo + LongMemEval + 14 stress-test results across 8 in-house architectures plus the actual current mem0 product, tested in both default-install and full-nlp-extras configurations against the same Gemma stack.
- `docs/architecture.md` — single-page architecture reference for the three-tier memory model.
- `docs/agent-memory-prototype-innovations.md` — design rationale for the two research variants.
- `CONTRIBUTING.md`, `.github/` issue + PR templates, GitHub Actions test workflow.
- `rp demo` command — bundled end-to-end smoke (probe → create → ingest 3 sample papers → run → optimize → synthesize), output lands in `projects/project_N/artifacts/`.
- Dashboard polish: type-scale CSS tokens, status-dot connection indicator, citation hover tooltips, empty-state for no projects.
- CLI progress: `rp project ingest` shows a Rich progress bar; `rp project run` / `optimize` show live status spinners.
- LoCoMo runner: `--max-workers` flag (default 4) with a ThreadPoolExecutor over (conversation, system) pairs — saturates vLLM continuous batching, ~5h vs ~21h serial for full 10-conv × 4-system runs.

### Removed
- `mflow_real` row from the LongMemEval headline table — the real-product integration didn't fit the per-question fresh-state benchmark protocol cleanly (kuzu graph DB grows globally across questions; OOM at 67/100 with proper config). The integration code is preserved in `benchmarks/_real_products/mflow_real.py` for future revival. In-house `m_flow_lite` and `m_flow_rich` re-implementations remain in the E-series tables.

### Phase 3 milestones (2026-04-25 to 2026-04-28)

- Per-iteration `iter_NN.md` summaries written to `projects/{id}/iterations/`.
- `query_helpers.py` — six structured slices of the blackboard for writer/reviewer agents.
- Hypothesis state-history audit log via `lifecycle.get_state_history`.
- PGR proxies (citation-trace verifiability + held-out evidence alignment + adversarial Red Team) and `rp project optimize --objective pgr`.

### Phase 2 milestones

- Optimization loop (`rp project optimize`): per-agent rubric → targeted config adjustment → re-run → plateau detection.
- Five structured artifacts (`claims.md`, `hypotheses.md`, `experiments.md`, `decision.md`, `risks.md`).
- Writer + Reviewer report with revision loop.
- Per-agent 6-dim rubric with KPI sparklines.

### Phase 1 milestones

- Provider-agnostic LLM adapter (chat + embeddings).
- 8 agent archetypes with divergent seed angles.
- OASIS-backed simulation with prompted-turn loop.
- Twitter + Reddit threaded channels.
- Per-user Karpathy LLM-Wiki with cosine search and Zep-style `t_ref` temporal filter.
- LLM planner for archetype selection.
- Live FastAPI dashboard with SSE streaming.

[Unreleased]: https://github.com/
[0.1.0]: https://github.com/

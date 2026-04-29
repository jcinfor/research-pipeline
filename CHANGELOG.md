# Changelog

All notable changes to `research-pipeline` (`rp`).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once a 1.0 is published.

## [Unreleased]

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

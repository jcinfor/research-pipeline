# Contributing to research-pipeline

Thanks for considering a contribution. The most useful contributions to `rp` cluster around three areas: **new benchmark scenarios** (E12+), **better real-product wrappers** (`benchmarks/_real_products/`), and **agent prompt improvements** (`src/research_pipeline/archetypes.py`).

## Where to start

- **Found a bug?** Open an issue with the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md). Include the command you ran, the failure mode, and `models.toml` (with secrets redacted).
- **Want to add a benchmark scenario?** Open a [scenario proposal issue](.github/ISSUE_TEMPLATE/benchmark_scenario.md) describing the failure mode you want to expose. We're particularly interested in scenarios that probe `EpistemicPrototype` (contradicting bundles, conviction trajectories) or `GapAwarePrototype` (mentioned-but-unspecified facts) — see [docs/agent-memory-prototype-innovations.md](docs/agent-memory-prototype-innovations.md).
- **Want to improve a memory adapter?** PRs against `benchmarks/_real_products/*.py` are welcome. The adapter contract is `ingest(doc) / query(question)` — see existing wrappers for the pattern.

## Development setup

```bash
git clone <repo-url> && cd research-pipeline
cp poc/models.toml models.toml      # edit with your LLM endpoint
uv sync --extra sim --extra ingest --extra dev
.venv/bin/python -m pytest tests/ -q \
    --ignore=tests/test_simulation.py \
    --ignore=tests/test_optimize.py \
    --ignore=tests/test_e7_xl_conversational.py \
    --ignore=tests/test_e8_differential_state.py \
    --ignore=tests/test_e9_cross_thread_routing.py \
    --ignore=tests/test_e10_scale_out.py \
    --ignore=tests/test_e10_xl_scale_out.py \
    --ignore=tests/test_e11_uncertainty.py \
    --ignore=tests/test_e11b_open_world_state.py
```

The `--ignore` set skips heavy LLM-driven integration tests that take ~30+ minutes each. The fast suite (279 tests after the `--ignore` set; 302 tests total when the heavy E-series + simulation/optimize tests are included) finishes in ~30s.

## Code style

- `uv run ruff check src/ tests/ benchmarks/` — pass clean before submitting.
- Type hints on public functions. We use Pyright-friendly typing but the codebase isn't strictly typed end-to-end.
- Comments: explain *why*, not *what*. Hidden constraints, surprising invariants, workarounds for specific bugs. Don't write docstrings that restate the function name.

## Pull requests

Use the [PR template](.github/PULL_REQUEST_TEMPLATE.md). Mention which benchmark/test exercises the change. If the change affects benchmark numbers, re-run the relevant benchmark and include the result file in the PR.

## What we're NOT looking for

- Wholesale architecture refactors. The three-tier memory model is what `rp` measured wins with — see [docs/architecture.md](docs/architecture.md). Local cleanups inside that frame are welcome.
- Dependencies on closed-source services for the core pipeline. Optional integrations live behind extras (`pyproject.toml` `[project.optional-dependencies]`).
- Scope creep into "general agent platform" territory. `rp` is a research-pipeline tool with a benchmark-suite side effect; keeping that scope tight is a feature.

## Questions

Open a [discussion](https://github.com/) (link will work once the repo is public) or an issue with the `question` label.

# E4 — Query-Time Repair benchmark

*Minimum viable benchmark for agent-memory architectures under temporal contradictions. Implements the E4 protocol from project 6's `experiments.md`. Referenced from [docs/agent-memory-architecture.md §9.5](../../docs/agent-memory-architecture.md) path 2.*

## What it measures

**Can the memory system return the current (or as-of-a-given-time) correct answer when the corpus contains explicit contradictions between earlier and later documents?**

Three systems under test:

| system | write-time cost | query-time mechanism | temporal awareness |
|---|---|---|---|
| **karpathy_lite** | 1 LLM compile per entity per doc (merges prior summary + new doc into an updated summary) | LLM answers from latest compiled summary | **none** — summary is "current state" only |
| **zep_lite** | 1 LLM extraction per doc producing `(entity, attribute, value)` triples with `valid_from` | filter triples by `valid_from ≤ as_of`, pick latest per `(entity, attribute)`, LLM answers | **full** — designed for temporal queries |
| **hybrid** (ours) | no LLM at write; embedding only; chunks tagged with `t_ref` | filter chunks by `t_ref ≤ as_of`, top-k cosine, LLM answers | **partial** — via `t_ref` filter; no triple resolution |

Corpus: 10 chronologically-ordered documents about a fictional company (Alpha Corp), a research project (Project X), and an experiment (Experiment Y), with three contradictions woven in (CEO succession, experiment outcome, project lead change).

Queries: 6 total — 3 current-state ("who is the current CEO"), 3 temporal ("who was CEO in mid-2020").

Scoring: substring match — answer must contain the correct entity name and must not contain a superseded entity name.

## Running it

```bash
cd research-pipeline
uv run python -m benchmarks.e4_query_time_repair.run
```

Requires the configured LLM backend to be reachable (see `models.toml`). Expected runtime with the local vLLM backend: ~2-3 minutes.

Output: markdown report at `benchmarks/e4_query_time_repair/results/run_YYYYMMDD_HHMMSS.md`.

## What this benchmark doesn't prove

- Single trial — no variance estimates. Judge stochasticity is bounded by running the score function deterministically (substring match), but LLM query answers are stochastic. Running it multiple times would be more defensible.
- 10-doc corpus — trivially small. Real memory systems face 100s-1000s of docs.
- 3 entities, 3 contradictions — sparse. Doesn't stress cross-entity interactions.
- Synthetic data — all entities/dates are controlled. Real corpora have noise, ambiguity, partial contradictions.
- Pure Karpathy and pure Zep are **simplified reimplementations**, not reference implementations of the original systems. They capture the core mechanism but not every subtlety.
- Scoring is substring match, not semantic judgment. A system that says "the current leadership includes several former executives including Alice Chen" would be scored incorrect on q1 even if it's technically accurate.

**This is a minimum viable demonstration** — its purpose is to replace "we haven't measured anything" with "we have one data point on one corpus on one axis." A serious benchmark is phase-4+.

## Interpreting results

- If **hybrid** wins on current + temporal: the `t_ref` + cosine + LLM-answer combo is carrying its weight.
- If **zep_lite** wins on temporal, hybrid ties on current: Zep's triple structure is more reliable than our chunk-retrieval for temporal reasoning, and the added write-time extraction cost is justified.
- If **karpathy_lite** wins on current but loses temporal: confirms the "no temporal awareness" design limit — Karpathy only carries the latest state.
- If all three are close: the test isn't discriminating; need more contradictions or harder queries.

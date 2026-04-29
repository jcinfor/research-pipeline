# mem0_real_v3 — Tier 2 small-E inline runs

*Run: 2026-04-29 ~19:00 (inline, single system, sequential).*

*mem0 provenance: mem0ai (editable @ 693e7093) v3-algo*

This file documents inline runs of `mem0_real_v3` (full v3 configuration:
mainline mem0 at SHA `693e7093` + `pip install "mem0ai[nlp]"` for
`fastembed` + `spacy` → full multi-signal retrieval engaged) on the
small/medium E-tests that don't currently have a `mem0_real` row in
their full runner output. Skips E5 (universal 1/3 ceiling — adds no
signal).

The full E-runners for these tests do NOT include `mem0_real` in their
default systems list (mem0_real is opt-in via `RP_BENCH_INCLUDE_MEM0_REAL`
or `RP_BENCH_INCLUDE_MEM0_REAL_V3` env vars in the runners that have
those toggles wired). Rather than re-running every system to add a
single mem0_real row to each result file, this inline run instantiates
`Mem0Real` directly and runs each test's corpus + queries.

## Setup

- mem0 install: editable from local clone of [`mem0ai/mem0`](https://github.com/mem0ai/mem0)
  at SHA `693e7093`, with `mem0ai[nlp]` extras (`fastembed`, `spacy`,
  `nltk`) installed → BM25 + entity-store + multi-signal retrieval engaged
- Backend: `google/gemma-4-26B-A4B-it` via vLLM, `qwen3-embedding:0.6b`
  via Ollama (same as all other rows)

## Results

| test | mem0_real_v3 | base prototype | mem0_lite | top score |
|---|---|---|---|---|
| **E4** (query-time repair) | **5/6** | 5/6 | n/a | 6/6 (zep_lite, multitier, gapaware) |
| **E6** (cross-entity) | **2/5** | 4/5 | 2/5 | 4/5 (rich variants + prototype family) |
| **E7** (conversational, 23 turns) | **6/6** ← top tie | 5/6 | 4/6 | 6/6 (zep_lite, gapaware, mem0_real_v3) |
| **E9** (cross-thread routing) | **4/9** | 9/9 | 5/9 | 9/9 (intent_routed_zep, prototype family + multitier + gapaware) |

## Per-test detail

### E4 — Query-time repair

ingest 31,334ms, 5/6 LLM-judge (current 2/3, temporal 3/3). Matches
base prototype + epistemic_prototype at 5/6.

### E6 — Cross-entity correlation

ingest 59,906ms, 2/5 LLM-judge (cross-entity 0/3, controls 2/2). Same
ceiling as `mem0_lite` / `zep_lite` / `supermemory_lite` — chunk-based
architectures don't compose cross-entity correlation regardless of v3's
multi-signal retrieval features.

### E7 — Conversational stress (23 turns)

ingest 53,156ms, 6/6 LLM-judge. **The one E-test where v3 clearly helps
on Gemma stack.** Short-window conversational shape plays to mem0's
historical strengths (chunks + recency + good extraction).

### E9 — Cross-thread routing

ingest 141,503ms, 4/9 LLM-judge (current 2/4, current_with_context 1/1,
historical 1/4). **v3 lands BELOW `mem0_lite` at 5/9** — engaging the
full multi-signal retrieval makes mem0 slightly worse on cross-thread
routing at Gemma scale than the simpler chunks-with-recency
`mem0_lite` baseline.

## Picture across the full E-suite for mem0_real_v3

| | mem0_real_v3 | prototype | gap |
|---|---|---|---|
| E1 | 1/3 | 3/3 | -2 (regression vs lite at 3/3) |
| E4 | 5/6 | 5/6 | 0 |
| E6 | 2/5 | 4/5 | -2 (matches lite ceiling) |
| E7 | 6/6 | 5/6 | +1 (v3 win) |
| E8 | 1/6 | 6/6 | -5 (regression vs lite at 2/6) |
| E9 | 4/9 | 9/9 | -5 (regression vs lite at 5/9) |

**Synthesis:** v3's full multi-signal retrieval on Gemma 26B is a net
*loss* on tests that exercise architectural failure modes (state
churn, differential state, cross-thread routing) — three regressions
where v3 underperforms mem0_lite, our simplest chunks+recency
re-implementation. v3 *helps* on tests with simpler retrieval shapes
(short conversations: E7 +1pp). The pattern is consistent with the
hypothesis that v3's multi-signal scoring (BM25 + entity-linking +
sigmoid threshold) needs a stronger generator than Gemma 26B to
disambiguate competing claims correctly.

## Reproduction

```bash
# Set up the maximal-config install (see BENCHMARKS.md →
# "Reproducing the two configurations" for the full recipe)
git clone https://github.com/mem0ai/mem0.git ../mem0
( cd ../mem0 && git checkout 693e7093 )
cd research-pipeline
uv sync --extra dev
uv pip install "mem0ai[nlp]" fastembed
uv run python -m spacy download en_core_web_sm

# Run the inline tier-2 sweep against mem0_real_v3
PYTHONPATH=$PWD VLLM_BASE_URL=... OLLAMA_BASE_URL=... \
  .venv/bin/python /tmp/mem0_real_v3_tier2.py
```

The inline script lives at [`/tmp/mem0_real_v3_tier2.py`](/tmp/mem0_real_v3_tier2.py) — copy into the repo if you want to keep it; the script just imports each test's `CORPUS` / `QUERIES` / `score` and runs `Mem0Real` against them.

# E1 — Blackboard Stress (mem0_real_v3 inline run)

*Run: 2026-04-29T15:37 (inline, single system).*

*mem0 provenance: mem0ai (editable @ 693e7093) v3-algo*

This file documents an inline run of E1 against `mem0_real_v3` (the full
v3 configuration: mainline mem0 at SHA `693e7093` + `pip install
"mem0ai[nlp]"` for `fastembed` + `spacy` → full multi-signal retrieval
engaged). The earlier full E1 run for all other systems is at
[run_20260425_141415.md](./run_20260425_141415.md); the only addition
here is the v3-configuration row, since re-running every E1 system to
add a single row would have wasted compute.

## Setup

- corpus: 60 interleaved docs across 3 streams (Alice's temperature,
  Prod-01's status, Project Nova's lead) — same as the 2026-04-25 run
- queries: 3 (`What is the current X of Y?` for each stream)
- scoring: fidelity = 1 if the answer contains the final ground-truth
  value AND no superseded value; else 0
- backend: vLLM Gemma at our Gemma stack; Ollama qwen3-embedding for
  embeddings (same as all other E1 rows)
- mem0 install: editable from local clone of [`mem0ai/mem0`](https://github.com/mem0ai/mem0)
  at SHA `693e7093`, with `mem0ai[nlp]` extras (`fastembed`, `spacy`,
  `nltk`) installed → BM25 + entity-store + multi-signal retrieval engaged

## Result

| system | fidelity | ingest ms | avg query ms | write LLM calls |
|---|---|---|---|---|
| **mem0_real_v3** | 1/3 | 126,159 | 475 | 60 |

## Per-stream

| entity | attribute | expected | fidelity | answer |
|---|---|---|---|---|
| User Alice | temperature | 99.0 | ✗ | The memory does not contain the current temperature. |
| Server Prod-01 | status | green | ✗ | red |
| Project Nova | lead | Iris | ✓ | Iris |

## Comparison with the default-install row from the 2026-04-25 run

| query | default-install (`mem0_real`, 2/3) | full-nlp (`mem0_real_v3`, 1/3) |
|---|---|---|
| Alice.temperature | ✗ abstained | ✗ abstained |
| Prod-01.status | ✓ "green" (correct) | ✗ "red" (stale) |
| Nova.lead | ✓ "Iris" | ✓ "Iris" |

The full-nlp configuration *regresses* on Prod-01 from a win to a
stale-pick loss. Both configurations are mem0's v3 algorithm
(`ADDITIVE_EXTRACTION_PROMPT` is in the active extraction path of both);
the difference is whether multi-signal retrieval is engaged. Engaging
it on Gemma 26B shifts the per-query ranking such that the latest
"green" status falls below an earlier "red" — see BENCHMARKS.md E1
section for the architectural read.

## Reproduction

```bash
# Set up the maximal-config install (see BENCHMARKS.md →
# "Reproducing the two configurations" for the full recipe)
git clone https://github.com/mem0ai/mem0.git ../mem0
( cd ../mem0 && git checkout 693e7093 )
cd research-pipeline
# Restore [tool.uv.sources] mem0ai = { path = "../mem0", editable = true }
uv sync --extra dev
uv pip install "mem0ai[nlp]" fastembed
uv run python -m spacy download en_core_web_sm

# Run E1 with the v3 toggle
VLLM_BASE_URL=... OLLAMA_BASE_URL=... \
  RP_BENCH_INCLUDE_MEM0_REAL_V3=1 \
  uv run python -m benchmarks.e1_blackboard_stress.run
```

The runner asserts `from mem0.configs.prompts import ADDITIVE_EXTRACTION_PROMPT`
succeeds when `RP_BENCH_INCLUDE_MEM0_REAL_V3` is set; if it doesn't,
the run aborts with a clear error pointing back to the install
instructions.

# Memory architecture benchmarks

This document is the **experiments + decision artifact** from two of `research-pipeline`'s own projects:

- **Project 7** — *"Compare five agent-memory architectures across realistic workloads."* Wrote in-house re-implementations of the four leading products (mem0, zep, supermemory, m_flow) plus a fresh three-tier design, then ran them through a designed benchmark suite to find where each one breaks.
- **Project 8** — *"Innovate on agent memory by addressing a primary issue with existing solutions."* Two architectural variants — `EpistemicPrototype` (preserves competing claims with conviction trajectories) and `GapAwarePrototype` (tracks "known unknowns" explicitly) — fall out of project 7's findings.

So this is not a separate benchmark suite that happens to live in the repo; it's what `rp` produced when we used `rp` to run a hard research question. The four in-house architectures (`prototype`, `multitier`, `epistemic_prototype`, `gapaware_prototype`), eight in-house re-implementation variants, and **two configurations of the actual mem0 product** — `mem0_real` (default `pip install mem0ai`, v3 algorithm with semantic-only retrieval) and `mem0_real_v3` (mainline + full nlp extras for v3's full multi-signal retrieval) — are evaluated across **two public benchmarks** (LoCoMo ACL 2024, LongMemEval ICLR 2025) and **14 in-house stress tests** (E1–E11b). Wrappers for `zep_real`, `supermemory_real`, and `mflow_real` exist in [`benchmarks/_real_products/`](./benchmarks/_real_products) — `mflow_real` was integrated but excluded from the LongMemEval headline (operational reasons explained below); `zep_real` and `supermemory_real` runs are pending.

All results are reproducible from the code in [benchmarks/](./benchmarks). Run any of them with `uv run python -m benchmarks.<name>.run`.

---

## Testing environment — read this first before comparing to published numbers

Every system in this doc — including `mem0_real`, the actual mem0 product — was evaluated against the **same local LLM stack**:

| role | model | backend |
|---|---|---|
| Generation, extraction, answering | `google/gemma-4-26B-A4B-it` (256K context) | local vLLM, OpenAI-compatible endpoint |
| Judge (LongMemEval + LoCoMo LLM-judge) | `google/gemma-4-26B-A4B-it` | same vLLM endpoint |
| Embeddings | `qwen3-embedding:0.6b` (1024-dim) | local Ollama, OpenAI-compatible endpoint |

**Real-product SDK configurations tested:** mem0's April-2026 v3 algorithm (single-pass ADD-only extraction + entity store + BM25 + multi-signal retrieval) is **already shipped in the PyPI 2.0.0 wheel** as of late April 2026. We test it in two configurations: (1) `mem0_real` = `pip install mem0ai` from PyPI, default deps only — `fastembed` and `spacy` not installed, so v3's multi-signal retrieval auto-falls back to semantic-only (what a typical user gets); (2) `mem0_real_v3` = mem0 mainline at SHA `693e7093` + `pip install "mem0ai[nlp]"` for `fastembed` + `spacy` — full multi-signal retrieval engaged. Both rows are v3 algorithm; the difference between them isolates the impact of (a) the 74-line mainline patch delta and (b) the optional nlp aux deps that gate BM25 + entity store. Both rows report on the same Gemma stack above.

**This is not the environment used in published benchmarks.** mem0's, zep's, supermemory's, and m_flow's published LoCoMo / LongMemEval numbers were produced with GPT-4-class generators and GPT-4-class judges. Our 26B Gemma-class stack is materially weaker on both sides of the pipeline — at extraction time *and* at answering time *and* at judging time.

**What this means in practice — triangulated gap:** mem0's published numbers are GPT-class. We tested mem0's actual v3 product (which already ships in PyPI 2.0.0) on Gemma stack in two configurations:

| LoCoMo source | LLM-judge | environment |
|---|---|---|
| mem0 v3 self-published | 91.6% | `gpt-5-mini` answer, `gpt-4o-mini` judge, full nlp extras (mem0's setup) |
| mem0 reproduced by m_flow (algorithm version unconfirmed; m_flow's `Mem0 Cloud (published)` reference row of 67.1% suggests their tested cloud was running v2-era code) | 50.4% | `gpt-5-mini` answer + `gpt-4o-mini` judge, top-K=30 (independent third-party reproduction; their `Mem0 Cloud (tested)` row). The clean reproduction-protocol gap on this row is 67.1% (m_flow's published reference) − 50.4% (m_flow's tested) = ~17pp. |
| **Our `mem0_real` (v3, default install, semantic-only retrieval)** | **43%** | Gemma 26B everything; `fastembed`/`spacy` not installed |
| **Our `mem0_real_v3` (v3, full nlp extras + mainline patches)** | **42%** | Gemma 26B everything; multi-signal retrieval engaged |

Two independent reproducers (m_flow + us) each measure mem0 below mem0's self-published number. The reproduction-protocol gap from m_flow's data is bounded: m_flow's tested figure (50.4%) vs the self-published reference m_flow cites in the same table (67.1% for `Mem0 Cloud (published)`, likely the v2-era algorithm given the dates) is ~17pp on like-for-like algorithm version. The further model-swap gap (m_flow's 50.4% with GPT-class to our 42-43% on Gemma 26B) is only 7-8pp. We don't try to derive a single number from m_flow's 50.4% vs mem0's *v3* self-published 91.6% because the algorithm version under m_flow's test date can't be confirmed; the v3-specific question (does the +20pp v3-over-v2 jump hold on a different stack?) is addressed in the next paragraph using our own same-stack measurements.

**The two-configuration v3 result is informative:** going from default install (semantic-only retrieval) to full nlp-extras (multi-signal retrieval engaged) on Gemma stack moves LoCoMo overall by *–1pp* (43 → 42). mem0's published +20pp v3 jump over their own v2 baseline (71 → 92) is reported under their preferred deployment (full deps, GPT-class generator); we cannot directly reproduce that comparison because we don't have a true v2 baseline in this suite (PyPI's `mem0ai==2.0.0` already ships v3 code). What we can show: the algorithmic features specific to v3 (BM25 + entity-store + multi-signal retrieval, all gated on the optional nlp deps) don't compound on Gemma 26B the way they do on a stronger generator — v3 gains +2pp on LongMemEval (default→full configuration), +6pp on temporal-reasoning, but loses 3pp on multi-session and is flat on LoCoMo overall.

The takeaway: **self-published memory-system benchmark numbers are not reliable across either reproduction protocols or LLM stacks**. mem0's published +20pp / +26pp gains were measured on their stack, with their preferred configuration; on a different stack we observe much smaller (sometimes negative) gains from the same code's full vs default configuration. Same-stack head-to-head measurement is the only credible comparison, and we don't claim to have decomposed mem0's specific v2 vs v3 algorithm comparison — only that on Gemma 26B, the prototype family beats both v3 configurations.

### Verification — every `mem0_real` row in this doc runs mem0's v3 algorithm

A common reader question: "did some of these `mem0_real` rows test the older v2 algorithm and some test v3?" Answer: **no, all rows run v3**. The variation across `mem0_real` rows reflects (a) the build (PyPI 2.0.0 wheel vs git mainline `693e7093`, a 74-line patch delta) and (b) whether the optional NLP aux deps (`fastembed`, `spacy`) are installed (which gates BM25 + entity-store; v3 gracefully degrades to semantic-only retrieval when missing). Evidence:

1. **`mem0ai==2.0.0` from PyPI ships v3, not v2.** Inspecting the wheel directly: `mem0/configs/prompts.py` defines `ADDITIVE_EXTRACTION_PROMPT` (the v3 single-pass ADD-only extraction prompt mem0's changelog headlines), and `mem0/memory/main.py` imports + uses it at line 725 inside the active extraction path called by `_add_to_vector_store`. mem0 shipped v3 to PyPI under the existing 2.0.0 version number without bumping. Verified against PyPI 2.0.0 wheel: `main.py` MD5 `ca00aef8b59f437640da80f58dfc56aa`, 136,356 bytes.
2. **Cross-machine bit-identical install.** This project was originally developed on a Windows machine (benchmarks pre-2026-04-27 morning) then migrated to Ubuntu. Forensic check (full record + reproduction commands: [`docs/mem0-version-forensics.md`](./docs/mem0-version-forensics.md)): the Windows-era `mem0ai==2.0.0` install (dist-info mtime 2026-04-25 13:49 BST) had `main.py` MD5 `ca00aef8b59f437640da80f58dfc56aa` — bit-identical to the post-migration Ubuntu install. Same wheel, same algorithm, same v3 markers. The Windows pre-migration `mem0_real` benchmark numbers (E1, all LongMemEval Phase B work, LoCoMo single-conversation slice) are v3-class measurements.
3. **Mainline build is a 74-line patch delta.** The mem0 mainline at SHA `693e7093` differs from the PyPI 2.0.0 wheel by 74 lines (whitespace-ignoring diff) — an optional `prompt` parameter passthrough on `_add_to_vector_store` and a `merge_filters` deep-merge helper. The core v3 algorithm (line 725 `system_prompt = ADDITIVE_EXTRACTION_PROMPT`) is identical. So `mem0_real_v3` rows (mainline build) and `mem0_real` rows (PyPI build) are both v3-class; the patches are bug fixes / minor enhancements.
4. **NLP aux-dep state distinguishes the two row types.** Per mem0's migration guide, *"All features are enabled by default with graceful degradation if dependencies missing."* `mem0_real` rows ran with default `pip install mem0ai` (no `fastembed` for BM25, no `spacy` for entity store) → semantic-only retrieval. `mem0_real_v3` rows ran with `pip install "mem0ai[nlp]"` → full multi-signal retrieval engaged.
5. **Empirical divergence between configurations.** Ingest is 55-60% slower per row with full nlp extras (LongMemEval 33,500s vs 21,633s; LoCoMo 27,477s vs 18,349s) — consistent with the additional per-doc work the BM25 + entity-store paths do. Per-category accuracy fingerprints diverge too: open-domain 14→19, multi-session 17→16, temporal 31→34. The two configurations produce two distinct empirical signatures; the labels match the behavior.

Result-file headers (since the helper landed 2026-04-29 ~14:00) include a `mem0 provenance` line auto-generated by [`benchmarks/_real_products/mem0_real.py::mem0_provenance()`](./benchmarks/_real_products/mem0_real.py) — runtime check of installed version + git SHA + v3-marker presence. The earlier 2026-04-28 LongMemEval run and the 2026-04-29 morning LoCoMo base-systems run (`run_20260429_105811.md`) predate this helper; the two afternoon `mem0_real_v3` result files (`run_oracle_20260429_143426.md` and `run_20260429_143913.md`) carry the provenance line and were retroactively annotated for completeness.

### Reproducing the two configurations

```bash
# Clone the workspace structure rp expects
git clone https://github.com/<your-org>/research-pipeline.git
git clone https://github.com/mem0ai/mem0.git ../mem0
( cd ../mem0 && git checkout 693e7093 )   # pin to the SHA we ran for the maximal-config row

cd research-pipeline

# Configuration 1 (`mem0_real` rows): default PyPI install, no nlp aux deps,
# v3 algorithm with retrieval auto-degraded to semantic-only.
# Comment out [tool.uv.sources] mem0ai in pyproject.toml first if you've
# previously run config 2 — otherwise uv will silently redirect to the editable clone.
uv pip install mem0ai==2.0.0
uv run python -m benchmarks.locomo_eval.run --conversations 10 --only-systems mem0_real
uv run python -m benchmarks.longmemeval.run --variant oracle --max-questions 100 --only-systems mem0_real

# Configuration 2 (`mem0_real_v3` rows): mainline build + full nlp extras,
# v3 algorithm with full multi-signal retrieval (BM25 + entity-linking + semantic).
# Restore [tool.uv.sources] mem0ai = { path = "../mem0", editable = true } in pyproject.toml.
uv sync --extra sim --extra ingest --extra dev
uv pip install "mem0ai[nlp]" fastembed
uv run python -m spacy download en_core_web_sm
uv run python -m benchmarks.locomo_eval.run --conversations 10 --only-systems mem0_real_v3
uv run python -m benchmarks.longmemeval.run --variant oracle --max-questions 100 --only-systems mem0_real_v3
```

The runner asserts `ADDITIVE_EXTRACTION_PROMPT` is importable when `mem0_real_v3` is requested and aborts with a clear error if it's not — so an install missing the v3 markers can't silently relabel a non-v3 build as v3.

**What the comparison is therefore measuring:** these are *same-stack, same-judge head-to-head* numbers. The ordering between systems on a fixed local stack is what's meaningful; the absolute percentages should not be compared to numbers reported in mem0's, zep's, etc. papers. If you re-run any system in this doc against GPT-4-class infrastructure, expect every row to move up substantially — and the ordering may shift, because some systems benefit more than others from a stronger generator (in particular, the Lite re-implementations and the Gap-Aware variant likely close more of their gap to richer systems with stronger extractors).

We use a local stack because (a) it's reproducible without paid-API budget, (b) it lets every system play on identical hardware, and (c) the failure modes the in-house stress tests (E1–E11b) are designed to expose are architectural, not generator-dependent — most of those tests show stable ordering across model swaps.

> **What we don't measure: BEAM.** mem0's v3 README also publishes BEAM (1M) and BEAM (10M) — production-scale memory evaluations at 1M and 10M token corpora — at 64.1 / 48.6 respectively. We don't have a BEAM-equivalent in `rp`'s suite, so we don't address those numbers. A BEAM-class workload would also exceed the local-stack scale we're committed to (Gemma 26B's effective context, our embedding throughput); it's open work for a future follow-up rather than a gap in this comparison.

---

## TL;DR

- On **LongMemEval** (oracle, 100 questions), our `epistemic_prototype` architecture achieves **58% LLM-judge** — top of the table. Base `prototype` is 56%; `mem0_real_v3` (mem0's full v3 setup: mainline + nlp extras) is 55%; `mem0_real` (default PyPI install, v3 algorithm with semantic-only retrieval) is 53%. The gap concentrates on multi-session, where epistemic's "preserve competing claims" architecture wins 23/40 (58%) vs `mem0_real_v3` at 16/40 (40%) — a **+18pp architectural lead** on the failure mode the variant was designed for. Independent convergence on the same architectural insight: mem0's v3 changelog explicitly cites "single-pass ADD-only extraction; nothing is overwritten" — the same idea project 8 produced for `EpistemicPrototype` from first principles.
- On **LoCoMo** (full 10-conversation 1542-question protocol), our `prototype` family sweeps the top 3 — `gapaware_prototype` 51%, `epistemic_prototype` 51%, base `prototype` 50% — all clustered **+8-9pp above either mem0 v3 configuration** (`mem0_real_v3` 42% with full nlp extras, `mem0_real` 43% with default deps). The full multi-signal retrieval setup doesn't move the LoCoMo headline on Gemma stack (v3 reports +20pp on GPT-class infrastructure but transfers as roughly +0 here regardless of configuration).
- **The single most defensible architectural claim — LoCoMo multi-hop**: prototype-family **49-50% (158-162/321) vs both `mem0_real` configurations at 6% (20/321) — identical across configurations** — an 8× gap on the question type that exercises connecting facts across sessions. mem0's chunk-based retrieval misses the connecting evidence regardless of whether BM25 + entity-linking are engaged. Append-only triple log + intent-routed retrieval surfaces it. The gap is consistent across all three prototype variants and across both mem0 configurations, ruling out single-system or single-config artifacts.
- **Variants pass the full floor-check on the in-house E-suite.** `gapaware_prototype` ties or beats base prototype on every E-test (1 win on E7 conversational at 6/6 vs base 5/6; everywhere else parity). `epistemic_prototype` ties base on most tests but takes a consistent **scoring-artifact regression** on E1 + E9-current + E5 — its multi-claim output format ("green [conv 1.00, 9 mentions], yellow [6], red [5]") includes the correct latest value at the top *plus* the historical context underneath, and the substring scorers reject any answer containing a superseded mention. This is an **architectural design tradeoff** (epistemic's whole premise is to preserve competing claims rather than collapse to "latest"), not a recall failure — disclosed honestly. *The same root architectural cost surfaces in mem0 v3 too:* both systems share the "preserve all claims, disambiguate at retrieval" design, and on Gemma 26B both pay it in different forms (epistemic in output-format scoring artifacts; mem0 v3 in retrieval-ranking failures returning stale/abstaining values). Strong-generator infrastructure (GPT-class) handles this architectural cost better than Gemma 26B does.
- **mem0 v3's full multi-signal retrieval is a net loss on Gemma 26B for stress workloads.** Engaging the optional NLP extras (`fastembed` for BM25 + `spacy` for entity store) over the default semantic-only setup produces three regressions on the E-suite (E1 1/3 vs lite 3/3; E8 1/6 vs lite 2/6; **E9 4/9 — *below* mem0_lite at 5/9** — engaging more retrieval features makes mem0 *worse* than our simplest chunks-with-recency re-implementation), one tie at architectural ceiling (E4 5/6, matches base prototype), one tie at lite ceiling (E6 2/5), and one win (E7 conversational 6/6, ties top — mem0's chunks-with-timestamps design is well-matched to the 23-turn shape). v3's published gains require GPT-class infrastructure to materialize; on weaker stacks the optional features actively hurt rather than gracefully degrading. This complements the LongMemEval +2pp / LoCoMo +0pp findings: mem0 v3's algorithm doesn't transfer regardless of which benchmark you measure on, and *enabling* the full v3 feature set makes things worse on architectural-stress tests.
- On **extreme-scale stress** (E10-XL: 10k–20k triples), `multitier` is the **only** system to maintain 7/7 fidelity. mem0/zep/m_flow all degrade or hit context-window errors.
- On **non-monotonic state reconstruction** (E8: 60 state changes across 3 values, 6 query intents), our `prototype` family achieves **6/6**, while mem0_lite and zep_lite get 2/6.
- On **conversational at 16-week / 124-turn distance** (E7-XL), `hybrid_flat` (the simplest baseline we test) achieves **11/12** at 1/10th the ingest time of richer systems — a useful negative result about over-engineering.

The full picture is more nuanced — every system wins some tests and loses others — and that's the point. The benchmarks are designed so the tradeoffs are *visible*.

---

## What gets compared

| System | What it is | License |
|---|---|---|
| `prototype` | Three-tier memory (working / project blackboard / user wiki) introduced in this repo. SQLite-only. | MIT (this repo) |
| `multitier` | Variant of prototype with explicit tier routing | MIT (this repo) |
| `mem0_lite` | In-house Mem0-style implementation capturing mem0's **pre-v3 design** (chunks + LLM extraction + recency). mem0's April-2026 v3 algorithm (single-pass add-only extraction + entity store + BM25 + multi-signal retrieval) is a substantial architectural change; faithfully porting it as `mem0_lite_v3` is post-launch follow-up work. Both `mem0_real` rows below benchmark the *actual* mem0 v3 product (which already ships in PyPI 2.0.0); the two rows differ in build (PyPI vs mainline) and aux-dep state (default install vs full nlp extras). | MIT (this repo) |
| `epistemic_prototype` | Prototype variant that preserves competing claims with conviction trajectories — same `(entity, attribute)` key can hold multiple values, each with conviction that grows on reinforcement | MIT (this repo) |
| `gapaware_prototype` | Prototype variant that tracks unknowns explicitly: an LLM identifies mentioned-but-unspecified facts at ingest, a consolidation tick surfaces contradictions, queries see "known unknowns" alongside known facts | MIT (this repo) |
| `zep_lite` | In-house Zep-style implementation (kind-typed entries, time-anchored) | MIT (this repo) |
| `zep_rich` | Zep-style + richer schema | MIT (this repo) |
| `intent_routed_zep` | Zep-style with query-intent-based retrieval | MIT (this repo) |
| `supermemory_lite` | In-house Supermemory-style implementation. See [docs/supermemory_notes.md](./docs/supermemory_notes.md) for the architectural premises behind the original product. | MIT (this repo) |
| `m_flow_lite` | In-house m_flow-style implementation. See [docs/m_flow_notes.md](./docs/m_flow_notes.md) for the bio-inspired cognitive memory engine premises behind the original product. | MIT (this repo) |
| `m_flow_rich` | m_flow-style + richer schema | MIT (this repo) |
| `hybrid_flat` | Simplest baseline: flat chunks + LLM extraction | MIT (this repo) |
| `karpathy_lite` | Karpathy LLM-Wiki pattern | MIT (this repo) |
| **`mem0_real`** | The actual mem0 product as a **default install** — `pip install mem0ai` from PyPI (2.0.0, which already ships mem0's April-2026 v3 algorithm: single-pass add-only extraction). With this install, the optional NLP aux deps (`fastembed` for BM25, `spacy` for entity store) are **not** installed, so v3's multi-signal retrieval gracefully degrades to semantic-only — what the typical PyPI user actually gets. | Apache-2.0 |
| **`mem0_real_v3`** | The actual mem0 product in **maximal v3 configuration** — installed from [mem0ai/mem0](https://github.com/mem0ai/mem0) git mainline at SHA `693e7093` (74 lines of patches past PyPI 2.0.0) plus `pip install "mem0ai[nlp]"` for `fastembed` + `spacy`. With this install, v3's full multi-signal retrieval (semantic + BM25 + entity-linking) is engaged. Both rows below run the v3 algorithm; this one has the full feature set, the row above is the default-deps configuration. | Apache-2.0 |
| **`zep_real`** | The actual Zep product (via [zep-cloud](https://pypi.org/project/zep-cloud/) SDK; underlying server is open-source [zep-graphiti](https://github.com/getzep/zep)) | mixed: open-source server + paid cloud SDK |
| **`supermemory_real`** | The actual Supermemory product (via [supermemory](https://pypi.org/project/supermemory/) SDK) | mixed: API + open SDK |

The "real" wrappers live in [benchmarks/_real_products/](./benchmarks/_real_products) and are thin shims around each product's official SDK.

> **Status of `*_real` adapters.** Three real-product wrappers exist; one is in the headline tables, two aren't:
>
> - **`mem0_real` (default PyPI install, v3 algorithm with semantic-only retrieval)** and **`mem0_real_v3` (mainline @ `693e7093` + full nlp extras → v3's full multi-signal retrieval)**: both in the public-benchmark tables below. Both run mem0's v3 algorithm; the two rows differ in build (PyPI vs mainline) and aux-dep state (default vs full nlp). Pointed at our local Gemma stack via mem0's OpenAI-compatible config. Two rows so readers can see how v3's published gains translate (or don't) across configurations on a non-GPT stack.
> - **`zep_real`**: wrapper exists; not in the tables. Zep's hosted backend uses *its own* extractor and answer LLM with no override path, so a zep_real row would compare zep-cloud's GPT-4-class infrastructure to everyone else on Gemma — not the same-stack head-to-head this comparison is built on.
> - **`supermemory_real`**: same situation as zep_real. Hosted SaaS without a model-override path.
> - **`mflow_real`**: wrapper integrated and run; result wasn't shippable on the LongMemEval protocol (kuzu graph DB grows globally across questions, OOM at 67/100). Code preserved; explanation under the LongMemEval section. The in-house `m_flow_lite` and `m_flow_rich` re-implementations stay in the E-series tables to capture m_flow's architectural ideas at this suite's scale.

---

## Public benchmarks

### LongMemEval (ICLR 2025) — oracle variant, 100 questions

*Phase C run (prototype / multitier / `mem0_real` default install): 2026-04-28. [results/run_oracle_20260428_044526.md](./benchmarks/longmemeval/results/run_oracle_20260428_044526.md).*
*Phase 2 run (variants): 2026-04-29. [results/run_oracle_20260429_010308.md](./benchmarks/longmemeval/results/run_oracle_20260429_010308.md).*
*`mem0_real_v3` run: 2026-04-29. [results/run_oracle_20260429_143426.md](./benchmarks/longmemeval/results/run_oracle_20260429_143426.md).*

| system | substring | LLM-judge | total ingest (s) | n |
|---|---|---|---|---|
| **`epistemic_prototype`** | **42/100 (42%)** | **58/100 (58%)** ← **🥇** | 30,761 | 100 |
| **prototype** | 39/100 (39%) | 56/100 (56%) | 30,457 | 100 |
| **mem0_real_v3** *(mainline + full nlp)* | 34/100 (34%) | 55/100 (55%) | 33,500 | 100 |
| **multitier** | 35/100 (35%) | 53/100 (53%) | 31,034 | 100 |
| **mem0_real** *(default install)* | 31/100 (31%) | 53/100 (53%) | 21,633 | 100 |
| **`gapaware_prototype`** | 37/100 (37%) | 52/100 (52%) | 50,510 | 100 |

Per-type LLM-judge breakdown (answerable):

| system | multi-session (40) | temporal-reasoning (54) |
|---|---|---|
| **`epistemic_prototype`** | **23/40 (58%)** ← top | 31/54 (57%) |
| **prototype** | 21/40 (53%) | 31/54 (57%) |
| **`gapaware_prototype`** | 21/40 (53%) | 26/54 (48%) |
| **mem0_real** *(default install)* | 17/40 (43%) | 31/54 (57%) |
| **multitier** | 16/40 (40%) | 31/54 (57%) |
| **mem0_real_v3** *(mainline + full nlp)* | 16/40 (40%) | **34/54 (63%)** ← top |

**Default-install vs full-nlp configurations of mem0 v3 on this stack:** mem0's v3 algorithm (April 2026: single-pass ADD-only extraction + entity store + BM25 + multi-signal retrieval) is in *both* configurations we test — the difference is whether the optional `fastembed` + `spacy` aux deps are installed (which gates BM25 + entity-store; without them v3 gracefully degrades to semantic-only retrieval). mem0's published numbers report +26pp on LongMemEval (67.8 → 93.4) for their full v3 deployment over their own v2 baseline; **we don't have a true v2 baseline in this suite** (PyPI's `mem0ai==2.0.0` already ships v3 algorithm code), so we can't directly reproduce mem0's v2→v3 comparison. What we *can* show is that engaging v3's full multi-signal retrieval over the default-install (semantic-only) baseline gives only **+2pp overall** (53 → 55) on our stack, with gains concentrated on temporal-reasoning (+6pp) and the multi-session subset slightly *negative* (40% vs 43% — the very category v3's entity-linking is designed to help). Either v3's gains are largely model-class-dependent (mem0's published numbers may need GPT-class infrastructure to materialize) or the algorithm-vs-deps decomposition of mem0's published gain is different from what we tested — we cannot distinguish without a true v2 baseline. What's robust on our data: the prototype family at 23/40 multi-session beats `mem0_real_v3` at 16/40 by **+18pp**, regardless of how mem0's own v2→v3 jump is interpreted.

**Three readings:**

- **`epistemic_prototype` is the top performer** — 58% LLM-judge overall, beating base `prototype` by 2pp, `mem0_real_v3` (mainline + full nlp extras) by 3pp, and `mem0_real` (default install) by 5pp. The architectural advantage shows up cleanly on multi-session: 23/40 (58%) vs `mem0_real_v3` 16/40 (40%) — a **+18pp lead on the failure mode the variant was designed for** (preserving competing claims rather than overwriting). The same architectural insight expressed in `EpistemicPrototype` is what mem0 v3 explicitly cites in its changelog ("Single-pass ADD-only extraction; nothing is overwritten") — independent convergence on the design principle, with our implementation still winning on this stack.
- **`gapaware_prototype` underperforms base** by 4pp at ~67% higher ingest cost — the per-doc gap-detection LLM call adds real overhead (50,510s vs 30,457s) without surfacing wins on this benchmark's question shape. LongMemEval's abstention questions aren't shaped to reward the "tracked but unspecified" pattern gap-aware was built for; that signal would surface on the E12 / E13 corpora we haven't designed yet.
- **mem0 v3's claimed +26pp jump on LongMemEval doesn't transfer to Gemma stack across either configuration** — going from default install to full nlp extras moves the overall by only +2pp (53 → 55), and *negative* on multi-session (43% → 40%, the very category v3's entity-linking architecture was supposed to help most). v3's gain on this stack is concentrated on temporal-reasoning (+6pp). The +26pp number mem0 reports requires GPT-class infrastructure to materialize, even with mem0's full nlp aux deps engaged.

A `zep_real` and `supermemory_real` row will be added when those runs complete.

> **Why no `mflow_real` row?** We integrated m_flow's actual product as a benchmark target and ran it through our LongMemEval pipeline. The result was unshippable for two compounding reasons: (1) m_flow's per-question state isolation is awkward — its `dataset_name` parameter scopes retrieval but doesn't physically isolate the underlying kuzu graph DB, so 100 question-haystacks accumulate in one global store and queries past Q60 spent 30-127 minutes each; (2) running with proper config (`MFLOW_EPISODIC_ENABLE_FACET_POINTS=true`, `MFLOW_EPISODIC_POINT_REFINER=true`, `MFLOW_EPISODIC_RETRIEVER_MODE=bundle`, TRIPLET synthesis) added 1330 size-check parser errors and segfaulted at 67/100 with the kuzu store at 8.6 GB. The integration debugging is preserved in [run_oracle_20260428_044526.md](./benchmarks/longmemeval/results/run_oracle_20260428_044526.md) "Operational note" for anyone who wants to revive the comparison; we're keeping the in-house `m_flow_lite` and `m_flow_rich` re-implementations (which don't depend on the product's full pipeline) as our way of evaluating m_flow's architectural ideas in this suite.

### LoCoMo (ACL 2024) — full protocol, 10 conversations × 1542 questions per system

*Variants run: 2026-04-29 ([results/run_20260429_043145.md](./benchmarks/locomo_eval/results/run_20260429_043145.md)). Base systems run: 2026-04-29 ([results/run_20260429_105811.md](./benchmarks/locomo_eval/results/run_20260429_105811.md)). `mem0_real_v3` run: 2026-04-29 ([results/run_20260429_143913.md](./benchmarks/locomo_eval/results/run_20260429_143913.md)).*

| system | substring | LLM-judge | total ingest (s) | n |
|---|---|---|---|---|
| **`gapaware_prototype`** | 368/1542 (24%) | **782/1542 (51%)** ← **🥇** | 23,078 | 1542 |
| **`epistemic_prototype`** | 353/1542 (23%) | **780/1542 (51%)** | 4,745 | 1542 |
| **prototype** | 369/1542 (24%) | **773/1542 (50%)** | 6,136 | 1542 |
| **mem0_real** *(default install)* | 302/1542 (20%) | 656/1542 (43%) | 18,349 | 1542 |
| **mem0_real_v3** *(mainline + full nlp)* | 307/1542 (20%) | 643/1542 (42%) | 27,477 | 1542 |
| **mem0_lite** | 258/1542 (17%) | 482/1542 (31%) | 9,578 | 1542 |
| **multitier** | 223/1542 (14%) | 426/1542 (28%) | 6,315 | 1542 |

Per-category LLM-judge breakdown:

| system | single_hop (282) | multi_hop (321) | open_domain (96) | temporal (841) | adversarial (2) |
|---|---|---|---|---|---|
| **`gapaware_prototype`** | 98/282 (35%) | 158/321 (49%) | 14/96 (15%) | 511/841 (61%) | 1/2 |
| **`epistemic_prototype`** | 94/282 (33%) | **162/321 (50%)** ← top | 17/96 (18%) | 506/841 (60%) | 1/2 |
| **prototype** | 91/282 (32%) | **162/321 (50%)** ← tie | 13/96 (14%) | 505/841 (60%) | 2/2 |
| **mem0_real** *(default install)* | **104/282 (37%)** ← top | 20/321 (6%) | 14/96 (15%) | **516/841 (61%)** ← top | 2/2 |
| **mem0_real_v3** *(mainline + full nlp)* | 98/282 (35%) | 20/321 (6%) | 19/96 (20%) | 504/841 (60%) | 2/2 |
| **mem0_lite** | 69/282 (24%) | 55/321 (17%) | **24/96 (25%)** ← top | 332/841 (39%) | 2/2 |
| **multitier** | 69/282 (24%) | 54/321 (17%) | 14/96 (15%) | 289/841 (34%) | 0/2 |

**The story:**

- **The prototype family sweeps the top 3** — `gapaware_prototype` 51%, `epistemic_prototype` 51%, base `prototype` 50%, all clustered above mem0's 42-43% (default install or mainline + full nlp). The +7-9pp gap to either mem0 configuration is significant at n=1542.
- **The architectural advantage is multi-hop.** Prototype-family hits 50% on multi-hop questions (which require connecting facts across sessions); both mem0 configurations collapse to 6% (20/321 each, identical). The append-only triple log + intent-routed retrieval surfaces the connecting evidence that mem0's chunk-based retrieval misses, and engaging v3's entity-linking + multi-signal retrieval doesn't move the needle on this stack.
- **mem0 v3's overall LoCoMo score is essentially configuration-independent** on Gemma stack — 42% with full nlp extras vs 43% with default deps, despite mem0's reported +20pp jump on GPT-class infrastructure when the full configuration is engaged. The gain doesn't transfer.
- **`mem0_real` (default install) still wins single-hop and temporal-reasoning narrowly** (104/282 vs prototype's 91/282; 516/841 vs prototype's 505/841). When the answer lives in one chunk and the question is well-formed, mem0's extraction tuning is sharp. The full-nlp configuration ties or slightly trails the default on those categories (98/282, 504/841) but beats default on open-domain (19/96 vs 14/96) — entity-linking's only consistent transferable gain we observed.
- **`mem0_lite` wins open-domain** (24/96) — its chunk-based retrieval is well-suited to open-ended "tell me about X" questions where structured triples lose context.
- **`multitier` is the disappointment of the run** — 28%, last place. Its episode-summarization layer helps long-context conversational state on E10-XL (where it's the only system at 7/7) but the LoCoMo question shape doesn't reward summary-tier retrieval; the routing overhead loses small-fact precision compared to bare prototype.
- **Ingest cost varies 6×** between the fastest variant (`epistemic_prototype` 4,745s) and `gapaware_prototype` (23,078s, the per-doc gap-detection LLM call adds substantial overhead). The full-nlp `mem0_real_v3` configuration is the slowest at 27,477s (entity store + BM25 indexing); the default-deps `mem0_real` is faster at 18,349s. On LoCoMo the extra cost barely moves the headline.

---

## In-house stress tests (E1–E11b)

These are stress tests we designed because the public benchmarks don't exercise certain failure modes. Each tests one specific aspect of how memory systems behave under adversarial conditions.

### Memory architecture stress

#### E1 — Blackboard stress (60 docs across 3 interleaved streams)

*Original run: 2026-04-25. [results](./benchmarks/e1_blackboard_stress/results/run_20260425_141415.md). Variant rows + multitier added 2026-04-29 ([results](./benchmarks/e1_blackboard_stress/results/run_20260429_181032.md)).*

Testing high-velocity attribute updates on the same entity (Alice's temperature, Prod-01's status, Project Nova's lead).

| system | fidelity | ingest ms | avg query ms | LLM extraction calls |
|---|---|---|---|---|
| **zep_lite** | **3/3** | 91,035 | 242 | 60 |
| **mem0_lite** | **3/3** | 44,094 | 142 | 60 |
| **supermemory_lite** | **3/3** | 52,274 | 300 | 60 |
| **m_flow_lite** | **3/3** | 45,858 | 128 | 60 |
| **prototype** | **3/3** | 90,378 | 1,081 | 60 |
| **multitier** | **3/3** | 39,562 | 865 | 60 |
| **gapaware_prototype** | **3/3** | 237,739 | 350 | 60 |
| **mem0_real** *(default install)* | 2/3 | 119,821 | 549 | 60 |
| **epistemic_prototype** | 0/3 ⚠ | 39,483 | 3,979 | 60 |
| **mem0_real_v3** *(mainline + full nlp)* | 1/3 | 126,159 | 475 | 60 |
| **hybrid_flat** | 1/3 | 8,882 | 459 | 0 |
| **hybrid_recency** | 0/3 | 7,322 | 460 | 0 |

> **Ingest-time note.** Lite systems and base `prototype` cite ingest times from the original 2026-04-25 run (the rows weren't re-run when variants were added on 2026-04-29). `multitier`, both prototype variants, and `mem0_real_v3` cite 2026-04-29 numbers. The fidelity scores (which is what the table is *about*) are unaffected — base prototype hit 3/3 on both runs, lite systems at 3/3 on both. Ingest times differ across the two runs because the 2026-04-29 venv had `fastembed` + `spacy` installed (different concurrent system load); the 2026-04-25 numbers are from a venv without those extras. We preserve the original 2026-04-25 ingest figures as the canonical baseline rather than re-running every system to homogenize the column.

Notable: `mem0_real` (default install — v3 algorithm with semantic-only retrieval) underperforms `mem0_lite` on this test — same architectural family, but the real product abstains on the Alice-temperature query rather than retrieving the latest of 20 observations.

**Engaging the full v3 nlp extras + mainline patches didn't fix this — it regressed.** v3's headline change is "single-pass ADD-only extraction; nothing is overwritten," which should be a perfect match for E1's high-velocity attribute updates (preserve all 20 temperature observations, retrieve the latest). Empirically on Gemma stack, the full-nlp configuration dropped to 1/3 (per-question results from [`benchmarks/e1_blackboard_stress/results/run_20260429_e1_v3_inline.md`](./benchmarks/e1_blackboard_stress/results/run_20260429_e1_v3_inline.md)):
- Alice.temperature: both configurations abstained ("memory does not contain the current temperature"). Storage layer (ADD-only) preserved all observations in both configs; retrieval failed to surface 99.0 in either case.
- Prod-01.status: **default-install retrieved "green" correctly; full-nlp returned "red"** (a superseded value). Engaging multi-signal retrieval flipped this query from a win to a stale-pick loss — the configuration with more retrieval signals did *worse* than the one with semantic-only.
- Nova.lead: both correct ("Iris"), the easier query where less noise accumulated.

Read this as a **stack-dependent regression**: on Gemma 26B, mem0's full multi-signal retrieval (semantic + BM25 + entity) scores produce different rankings than semantic-only does, and the difference doesn't favor the configuration with more signals. The exact failure mechanism (whether the multi-signal sigmoid scoring + post-retrieval threshold pushes specific candidates down or whether BM25 over-weights stale values) is plausible from mem0's documented algorithm but we did not capture diagnostic logs of the per-query score vectors — would need instrumentation to confirm definitively. The empirical pattern is clear though: more retrieval features ≠ better on this stack.

*Reproducer (full-nlp configuration):* `RP_BENCH_INCLUDE_MEM0_REAL_V3=1 uv run python -m benchmarks.e1_blackboard_stress.run` after the install steps in [Reproducing the two configurations](#reproducing-the-two-configurations). The 1/3 row was produced by an inline script (the runner's full system list re-runs every system; the inline script just instantiates `Mem0Real` and runs E1's corpus + queries, since the other systems' E1 numbers from the linked `run_20260425_141415.md` are already canonical).

> **`epistemic_prototype` 0/3 — scoring artifact, not a retrieval failure.** Looking at epistemic's actual answers: Server-status returned `"green" [conviction 1.00, 9 mentions]` at the top of its multi-claim list (the correct latest value, with high confidence), but also surfaced competing values `"yellow" [6 mentions]` and `"red" [5 mentions]`. E1's score function rejects any answer containing a superseded value — that's the *deliberate* test design, since the original goal was to penalize stale-pick failures. Epistemic's design is to *preserve* the multi-claim view (its whole architectural premise: don't collapse competing claims to a single value); it surfaces the latest at the top *and* the historical context underneath, and the substring-style scoring penalizes that. Architectural tension between epistemic's design (preserve all competing claims) and E1's scoring (single-value, no superseded mentions allowed) — not a recall regression. The Alice and Nova queries are real misses (epistemic's hot-index surfaced an older reading instead of the latest); E1's design hits epistemic's weakest path. **The same root architectural issue surfaces in mem0 v3** (which also stores all claims, ADD-only, by design): on Gemma 26B both systems pay a similar cost in different forms — epistemic in output-format scoring artifacts, mem0 v3 in retrieval-ranking failures (returning stale values or abstaining). Strong-generator infrastructure (GPT-class) appears to handle the "preserve all, disambiguate at retrieval" architectural cost better than Gemma 26B does.

#### E1-TTL — Cold-vs-hot retention

*Run: 2026-04-24. [results](./benchmarks/e1_ttl/results/run_20260424_161652.md).*

Every system tested gets 2/2 on cold + hot doc separation.

#### E5 — Noisy extraction (tail-failure)

*Original run: 2026-04-25. [results](./benchmarks/e5_noisy_extraction/results/run_20260425_124409.md). Variant rows added 2026-04-29 ([results](./benchmarks/e5_noisy_extraction/results/run_20260429_184140.md)).*

Last 5 docs of each stream return empty extraction. Every system gets 1/3 *except* `epistemic_prototype` which gets 0/3 — same scoring-artifact pattern as E1 (multi-claim format trips substring scoring even when the latest value is in the response). `gapaware_prototype` ties base prototype at 1/3. **A negative result we leaned into.** Indicates current memory architectures can't recover from extractor failure on the tail; this is an architectural ceiling, not a system-level differentiator.

### Temporal queries

#### E4 — Query-time repair (10 docs, 3 current + 3 temporal queries)

*Original run: 2026-04-25. [results](./benchmarks/e4_query_time_repair/results/run_20260425_123424.md). Variant + multitier rows added 2026-04-29 ([results](./benchmarks/e4_query_time_repair/results/run_20260429_180015.md)). `mem0_real_v3` row added 2026-04-29 via inline script ([results](./benchmarks/_real_products/results_mem0_real_v3_tier2.md#e4--query-time-repair)).*

| system | current | temporal | overall | ingest ms | avg query ms |
|---|---|---|---|---|---|
| **zep_lite** | 3/3 | **3/3** | **6/6** | 19,653 | 240 |
| **multitier** | 3/3 | **3/3** | **6/6** | 15,361 | 649 |
| **gapaware_prototype** | 3/3 | **3/3** | **6/6** | 48,044 | 344 |
| **prototype** | 2/3 | **3/3** | 5/6 | 23,858 | 665 |
| **hybrid** | 3/3 | 2/3 | 5/6 | 3,085 | 919 |
| **epistemic_prototype** | 2/3 | **3/3** | 5/6 | 15,391 | 700 |
| **karpathy_lite** | 3/3 | 0/3 | 3/6 | 16,608 | 562 |
| **mem0_real_v3** *(mainline + full nlp)* | 2/3 | 3/3 | **5/6** | 31,334 | 634 |

Karpathy LLM-wiki is fast on current state but lacks temporal anchoring — confirms the need for `t_ref` annotations in tier-3. `gapaware_prototype` matches base prototype + zep_lite at 6/6 (clean ceiling); `epistemic_prototype` ties base at 5/6 (one current-query miss). `mem0_real_v3` (added 2026-04-29 inline) ties base prototype + epistemic at 5/6 — competitive on this small temporal-repair test.

#### E8 — Differential state reconstruction (60 non-monotonic state changes)

*Base run: 2026-04-28. [results](./benchmarks/e8_differential_state/results/run_20260428_121208.md). Two `mem0_real` v3 configurations added 2026-04-29 via inline runs (both bottom-of-table; see notes below).*

| system | current | current_with_context | historical | overall | ingest ms |
|---|---|---|---|---|---|
| **prototype** | 1/1 | 1/1 | **4/4** | **6/6** | 85,562 |
| **epistemic_prototype** | 1/1 | 1/1 | **4/4** | **6/6** | 86,006 |
| **gapaware_prototype** | 1/1 | 1/1 | **4/4** | **6/6** | 566,963 |
| **zep_rich** | 1/1 | 1/1 | 3/4 | 5/6 | 92,101 |
| **intent_routed_zep** | 1/1 | 1/1 | 3/4 | 5/6 | 103,839 |
| **mem0_lite** | 1/1 | 0/1 | 1/4 | 2/6 | 99,805 |
| **zep_lite** | 1/1 | 0/1 | 1/4 | 2/6 | 104,153 |
| **mem0_real_v3** *(mainline + full nlp)* | 1/1 | 0/1 | 0/4 | 1/6 | 128,620 |
| **hybrid_flat** | 1/1 | 0/1 | 0/4 | 1/6 | 3,647 |
| **mem0_real** *(PyPI 2.0.0 build + full nlp)* | 0/1 | 0/1 | 0/4 | **0/6** | 130,278 |

**Prototype family wins decisively on historical state queries — and v3 doesn't change the picture.** E8 was where v3's headline claim should land hardest: the test exists *because* "preserve all state changes; don't overwrite" is exactly what v3's ADD-only extraction promises. We tested two v3 configurations on Gemma stack (mainline build at SHA `693e7093` + full nlp extras = 1/6; PyPI 2.0.0 wheel + full nlp extras = 0/6 — same algorithm class, 74-line patch delta). Both bottom-of-table; the mainline patches buy mem0 exactly one question (the simple "current value", probably via the `merge_filters` deep-merge fix). Multi-signal retrieval with sigmoid scoring + 0.1 threshold pushes most historical queries into abstention on Gemma 26B — the same failure mode we saw on E1.

The empirical pattern across both v3 configurations and on the failure mode v3 explicitly targets: **mem0's `Memories accumulate; nothing is overwritten` design idea is correct at the storage layer, but its retrieval-layer multi-signal scoring requires a stronger generator than Gemma 26B to surface the right preserved values**. The `prototype` family (which combines append-only storage with intent-routed deterministic retrieval) gets all 4 historical queries on the same stack.

*Reproducer:* `RP_BENCH_INCLUDE_MEM0_REAL_V3=1 uv run python -m benchmarks.e8_differential_state.run` (full-nlp config). The PyPI-build row was produced via inline script after `uv pip uninstall mem0ai && uv pip install mem0ai==2.0.0` (bypassing the `[tool.uv.sources]` pin temporarily).

#### E9 — Cross-thread intent routing (90 interleaved triples)

*Original run: 2026-04-25. [results](./benchmarks/e9_cross_thread_routing/results/run_20260425_002326.md). Variant + prototype/multitier rows added 2026-04-29 ([results](./benchmarks/e9_cross_thread_routing/results/run_20260429_183035.md)). `mem0_real_v3` row added 2026-04-29 via inline script ([results](./benchmarks/_real_products/results_mem0_real_v3_tier2.md#e9--cross-thread-routing)).*

| system | current | current_with_context | historical | overall |
|---|---|---|---|---|
| **zep_rich** | 4/4 | 1/1 | **4/4** | **9/9** |
| **intent_routed_zep** | 4/4 | 1/1 | **4/4** | **9/9** |
| **prototype** | 4/4 | 1/1 | **4/4** | **9/9** |
| **multitier** | 4/4 | 1/1 | **4/4** | **9/9** |
| **gapaware_prototype** | 4/4 | 1/1 | **4/4** | **9/9** |
| **epistemic_prototype** | 1/4 ⚠ | 1/1 | **4/4** | 6/9 |
| **mem0_lite** | 4/4 | 1/1 | 0/4 | 5/9 |
| **zep_lite** | 4/4 | 1/1 | 0/4 | 5/9 |
| **mem0_real_v3** *(mainline + full nlp)* | 2/4 | 1/1 | 1/4 | 4/9 |
| **hybrid_flat** | 2/4 | 0/1 | 1/4 | 3/9 |

Intent routing helps on historical queries; the lite versions lose all 4 historical. `gapaware_prototype` and `multitier` join the prototype family at 9/9. `epistemic_prototype` regresses on `current` queries (1/4) — same scoring-artifact as E1: epistemic's multi-claim output format includes superseded values alongside the correct latest value, and E9's substring scoring rejects answers containing superseded mentions. *historical* queries (where epistemic's "preserve all claims" architecture is supposed to help most) all 4/4 — confirming the regression is at the output-format / scoring layer, not retrieval. **`mem0_real_v3` lands at 4/9 — *below* `mem0_lite` (5/9)**: v3's multi-signal retrieval (BM25 + entity-store engaged) makes things slightly worse on cross-thread routing at Gemma 26B than the simple chunks-with-recency `mem0_lite` baseline. Architectural ceiling for chunk-based mem0 architectures on this test, regardless of v3's retrieval features.

#### E11 — Uncertainty calibration (10 queries, 4 categories)

*Run: 2026-04-28. [results](./benchmarks/e11_uncertainty/results/run_20260428_121535.md).*

All 9 systems tested achieve 10/10 — a sanity check that everyone correctly says "I don't know" when there's no information.

### Cross-entity & open-world

#### E6 — Cross-entity temporal correlation (3 streams of 10 each)

*Original run: 2026-04-25. [results](./benchmarks/e6_cross_entity/results/run_20260425_122357.md). Variant + multitier rows added 2026-04-29 ([results](./benchmarks/e6_cross_entity/results/run_20260429_181633.md)). `mem0_real_v3` row added 2026-04-29 via inline script ([results](./benchmarks/_real_products/results_mem0_real_v3_tier2.md#e6--cross-entity-correlation)).*

| system | cross-entity (3) | controls (2) | overall (5) |
|---|---|---|---|
| **zep_rich** | 2/3 | 2/2 | **4/5** |
| **m_flow_rich** | 2/3 | 2/2 | **4/5** |
| **prototype** | 2/3 | 2/2 | **4/5** |
| **multitier** | 2/3 | 2/2 | **4/5** |
| **epistemic_prototype** | 2/3 | 2/2 | **4/5** |
| **gapaware_prototype** | 2/3 | 2/2 | **4/5** |
| **hybrid_flat** | 1/3 | 2/2 | 3/5 |
| **mem0_lite** | 0/3 | 2/2 | 2/5 |
| **zep_lite** | 0/3 | 2/2 | 2/5 |
| **supermemory_lite** | 0/3 | 2/2 | 2/5 |
| **m_flow_lite** | 0/3 | 1/2 | 1/5 |
| **mem0_real_v3** *(mainline + full nlp)* | 0/3 | 2/2 | 2/5 |

Lite systems pass control queries but fail at correlating events across entities. Rich variants, prototype, multitier, and *both* prototype family variants tie at the 4/5 ceiling — clean parity for the variants on cross-entity correlation. `mem0_real_v3` lands at the lite ceiling (2/5) — v3's full multi-signal retrieval doesn't rescue mem0 from cross-entity correlation failure on Gemma 26B; same architectural ceiling as the chunk-based lite re-implementations.

#### E11b — Open-world status updates (asymmetric resolution)

*Run: 2026-04-28. [results](./benchmarks/e11b_open_world/results/run_20260428_121853.md).*

| system | resolved (4) | unresolved (4) | current (2) | overall (10) |
|---|---|---|---|---|
| **zep_rich** | 4/4 | 4/4 | 2/2 | **10/10** |
| **m_flow_rich** | 4/4 | 4/4 | 2/2 | **10/10** |
| **prototype** | 4/4 | 4/4 | 2/2 | **10/10** |
| **epistemic_prototype** | 4/4 | 4/4 | 2/2 | **10/10** |
| **gapaware_prototype** | 4/4 | 4/4 | 2/2 | **10/10** |
| **m_flow_lite** | 4/4 | 3/4 | 2/2 | 9/10 |
| **mem0_lite** | 4/4 | 2/4 | 2/2 | 8/10 |
| **zep_lite** | 4/4 | 2/4 | 2/2 | 8/10 |
| **supermemory_lite** | 4/4 | 2/4 | 2/2 | 8/10 |
| **intent_routed_zep** | 4/4 | 2/4 | 2/2 | 8/10 |

The unresolved-state column separates rich-schema systems (4/4) from lite systems (2/4). Prototype family hits 10/10.

### Conversational

#### E7 — Conversational memory stress (23 turns, 4 sessions)

*Original run: 2026-04-24. [results](./benchmarks/e7_conversational/results/run_20260424_175340.md). Variant + prototype/multitier rows added 2026-04-29 ([results](./benchmarks/e7_conversational/results/run_20260429_183449.md)). `mem0_real_v3` row added 2026-04-29 via inline script ([results](./benchmarks/_real_products/results_mem0_real_v3_tier2.md#e7--conversational-stress-23-turns)).*

| system | overall (6) | ingest ms |
|---|---|---|
| **zep_lite** | **6/6** | 27,349 |
| **gapaware_prototype** | **6/6** | 84,613 |
| **supermemory_lite** | 5/6 | 24,899 |
| **m_flow_lite** | 5/6 | 20,583 |
| **prototype** | 5/6 | 14,641 |
| **multitier** | 5/6 | 15,578 |
| **mem0_lite** | 4/6 | 25,088 |
| **hybrid_flat** | 4/6 | 4,798 |
| **epistemic_prototype** | 4/6 | 16,270 |
| **mem0_real_v3** *(mainline + full nlp)* | **6/6** | 53,156 |

`gapaware_prototype` and `mem0_real_v3` tie the top score (6/6 with `zep_lite`); both beat base prototype by 1 question. **This is the one E-test where v3's full multi-signal retrieval clearly helps on Gemma stack** — short-window conversational shape plays to mem0's design strengths (chunks + recency + extraction). The gap-detection / consolidation tick in `gapaware_prototype` similarly surfaces preference-evolution and cross-session links that base prototype misses. `epistemic_prototype` ties `mem0_lite` / `hybrid_flat` at 4/6, losing 1 more than base — its multi-claim format costs it on the `forgetting` and `preference_evolution` queries where E7's scoring expects a single canonical answer.

#### E7-long — 73 turns, 8 weeks

*Run: 2026-04-24. [results](./benchmarks/e7_long_conversational/results/run_20260424_220748.md).*

| system | overall (10) | ingest ms |
|---|---|---|
| **zep_lite, mem0_lite, supermemory_lite, m_flow_lite** | **9/10** | 95-110k |
| **hybrid_flat** | 7/10 | 11,662 |

`hybrid_flat` ingests 8-10× faster but trades 2 query points.

#### E7-XL — 124 turns, 16 weeks (12 queries, most spanning 100+ turns)

*Run: 2026-04-25. [results](./benchmarks/e7_xl_conversational/results/run_20260425_132858.md).*

| system | overall (12) | ingest ms |
|---|---|---|
| **hybrid_flat** | **11/12** | **18,808** |
| **zep_rich** | 11/12 | 193,735 |
| **mem0_lite** | 11/12 | 173,721 |
| **zep_lite** | 10/12 | 197,798 |
| **supermemory_lite** | 10/12 | 200,630 |
| **intent_routed_zep** | 10/12 | 193,372 |
| **prototype** | 10/12 | 1,274,193 |
| **m_flow_rich** | 9/12 | 176,130 |
| **m_flow_lite** | 8/12 | 174,595 |

**The most surprising result we have**: at 124-turn / 16-week scale, the simplest baseline (`hybrid_flat` — flat chunks, no LLM extraction) ties for first while ingesting 10× faster than every richer system. A useful negative result about over-engineering memory architectures for the conversational case.

### Scale

#### E10 — Scale-out (100 → 5000 triples)

*Run: 2026-04-25. [results](./benchmarks/e10_scale_out/results/run_20260425_120229.md).*

Fidelity (out of 7):

| system | 100 | 500 | 1000 | 2500 | 5000 |
|---|---|---|---|---|---|
| **prototype** | **7/7** | **7/7** | **7/7** | **7/7** | **7/7** |
| **intent_routed_zep** | **7/7** | **7/7** | **7/7** | **7/7** | **7/7** |
| **zep_rich** | 7/7 | 6/7 | 6/7 | 7/7 | 7/7 |
| **m_flow_rich** | 7/7 | 7/7 | 7/7 | 5/7 | 4/7 |
| **mem0_lite, zep_lite, m_flow_lite** | 6/7 | 4/7 | 4/7 | 4/7 | 4/7 |

Avg query latency (ms):

| system | 100 | 500 | 1000 | 2500 | 5000 |
|---|---|---|---|---|---|
| **mem0_lite** | 283 | 180 | 183 | 189 | 185 |
| **zep_lite** | 169 | 181 | 183 | 188 | 187 |
| **m_flow_lite** | 173 | 197 | 197 | 204 | 231 |
| **m_flow_rich** | 210 | 556 | 1,383 | 6,925 | 25,174 |
| **zep_rich** | 225 | 786 | 3,051 | 12,481 | 46,155 |
| **intent_routed_zep** | 327 | 865 | 2,326 | 12,486 | 46,433 |

Rich systems pay for their accuracy with super-linear query latency. The lite systems stay fast but lose accuracy.

#### E10-XL — Extreme scale (10k, 20k triples)

*Run: 2026-04-25. [results](./benchmarks/e10_xl_extreme_scale/results/run_20260425_134705.md).*

| system | 10,000 | 20,000 | notes |
|---|---|---|---|
| **multitier** | **7/7** | **7/7** | only system that holds at 20k |
| mem0_lite, zep_lite | 5/7 | 4/7 | partial degradation |
| prototype, intent_routed_zep | 4/7 | 4/7 | context-window errors |
| zep_rich | 0/7 | 0/7 | context-window errors blocking all queries |

Skipped 50k — past every backend's limits. **`multitier` is the headline result for this benchmark.**

---

## Methodology

- **Substring scoring**: lower bound. Marks an answer correct iff the expected token sequence appears verbatim in the answer.
- **LLM-judge scoring**: per-paper protocol where applicable. LongMemEval uses [the official paper's per-type prompts](https://arxiv.org/abs/2410.10813); LoCoMo uses the official GPT-4-class judge protocol. We substitute the `google/gemma-4-26B-A4B-it` judge throughout (see [Testing environment](#testing-environment--read-this-first-before-comparing-to-published-numbers) above) — every system is judged identically, but absolute numbers are not comparable to paper-reported runs that used GPT-4-class judges.
- **Ingest ms / total ingest s**: wall-clock time for the system to absorb the test corpus. LLM-extraction calls dominate.
- **Avg query ms**: per-query retrieval+answer latency.

Real-product systems (`*_real`) call their official SDKs configured to point at the same `google/gemma-4-26B-A4B-it` vLLM endpoint where the SDK supports a custom OpenAI-compatible base URL — so e.g. `mem0_real` calls the actual mem0 SDK pipeline, but with our Gemma stack as its underlying LLM. Where a real product cannot be redirected (e.g. parts of `zep_real` rely on Zep's hosted backend), we note that on the relevant row.

## Reproducibility

Every result file in this doc lives at `benchmarks/<name>/results/`. To re-run any benchmark:

```bash
cd research-pipeline
uv sync --extra sim --extra dev
uv run python -m benchmarks.e8_differential_state.run     # any name
```

Real-product wrappers require the corresponding SDKs:

```bash
uv pip install mem0ai zep-cloud supermemory
# m_flow is local clone in ../m_flow
```

## Caveats

1. **Single-judge, single-generator stack** — see [Testing environment](#testing-environment--read-this-first-before-comparing-to-published-numbers) above for the full picture. The ordering between systems on this fixed stack tends to be stable; the absolute % does *not* compare to paper-reported runs using GPT-class infrastructure. Triangulation on LoCoMo: mem0's v3 algorithm self-publishes 91.6% (full nlp config, GPT-class), m_flow's independent third-party reproduction with `gpt-5-mini` got 50.4% (algorithm version under m_flow's test cannot be confirmed; m_flow's own published-reference row in the same table is 67.1% for the v2-era number, suggesting their reproduction was v2), and our `mem0_real` / `mem0_real_v3` on Gemma 26B got 43% / 42% (default install / mainline + full nlp extras respectively) — *near-identical across mem0 configurations on Gemma*. The same-stack v3 features-on/off gap is small (1pp on LoCoMo overall, 2pp on LongMemEval), so v3's algorithm gain is stack-dependent and doesn't compound on a Gemma 26B generator the way mem0 reports it does on GPT-class. When re-running on a different stack expect every row to move, and possibly some ordering shifts on the public benchmarks (the in-house E1–E11b stress tests are designed to expose architectural failure modes that are more model-stable).
2. **Real-product latency includes their full stack** — for `*_real` rows, ingest time depends on the product's hosted backend (round-trips, batch sizes, etc.). Lite/in-house systems run locally.
3. **Stress tests are designed by us** — they reflect what we think matters. The public benchmarks (LoCoMo, LongMemEval) are the unbiased anchors.
4. **`zep_rich` and `intent_routed_zep` use longer prompts** — that's why they hit context-window errors at 10k+ scale. Architectural choice, not a bug.
5. **`mflow_real` is intentionally not in the LongMemEval table** — see the explanation under that benchmark. We kept `m_flow_lite` / `m_flow_rich` (our in-house re-implementations of m_flow's architectural ideas) in the E-series tables since those work cleanly at this suite's scale.

## What this benchmark suite is for

We built `research-pipeline` because we wanted a multi-agent research tool, not a memory paper. But during development we needed to choose a memory architecture, and the existing benchmarks (LoCoMo, LongMemEval) didn't tell us what we needed to know about specific failure modes — non-monotonic state, cross-entity correlation, scale-out, conversational distance.

So we built our own. Then we ran them against the products we'd considered using off-the-shelf. The result is this comparison — useful both for picking a memory architecture for your own agents and for understanding the design tradeoffs (richness vs latency vs scale-out).

If you're building agent memory: clone, run, judge for yourself. PRs adding new test scenarios or fixing implementations of any of the systems are welcome.

---

*`mflow_real` was integrated and run but the result wasn't shippable (see the LongMemEval section for why); the integration is preserved in [`benchmarks/_real_products/mflow_real.py`](./benchmarks/_real_products/mflow_real.py) for future revival. `zep_real` and `supermemory_real` rows are pending. Per-benchmark `Run:` dates above link to the underlying result file when you want to verify.*

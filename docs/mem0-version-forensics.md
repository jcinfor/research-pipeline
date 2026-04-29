# mem0ai install version — forensic verification

*Recorded 2026-04-27. Establishes that every `mem0_real` benchmark this project
ran was against mem0's v3-algorithm code, not v2. Confirmed by bit-identical
hashes between the Windows and Ubuntu installs.*

## Why this matters

`mem0ai==2.0.0` on PyPI ships the **v3 algorithm** (single-pass ADD-only
extraction, BM25 multi-signal retrieval, additive prompts) — not the v2
algorithm that some external comparisons reference. We benchmarked against
this version starting 2026-04-25 across LoCoMo and LongMemEval. The version
fact would change how to read mem0_real's published-vs-our numbers if we
were testing v2 — so we verified.

## Verdict

**Windows and Ubuntu venvs had bit-identical mem0ai installs (same MD5
of `mem0/memory/main.py`). Both are v3-class.**

| field | value |
|---|---|
| Package | `mem0ai==2.0.0` (PyPI wheel) |
| Install method | `uv` (per `INSTALLER` file); no `direct_url.json` (regular PyPI, not editable / not git-source) |
| Install timestamp (Windows) | **2026-04-25 13:49 BST** (dist-info mtime) |
| `main.py` MD5 | `ca00aef8b59f437640da80f58dfc56aa` (matches the "PyPI 2.0.0 wheel" v3-class hash known from Ubuntu) |
| `main.py` size | 136,356 bytes |
| `ADDITIVE_EXTRACTION_PROMPT` | Present in `mem0/configs/prompts.py` AND imported + used in `main.py` at lines 18, 725, 2132 |
| `bm25` markers | Present (`lemmatize_for_bm25`, `get_bm25_params`, `normalize_bm25`) |
| `additive` markers | Present (incl. `generate_additive_extraction_prompt`) |
| `EntityStore` literal | Not present in `main.py` (likely renamed in this build — BM25 + additive markers alone are sufficient v3 evidence) |
| Python import check | `from mem0.configs.prompts import ADDITIVE_EXTRACTION_PROMPT` succeeds; prompt length 33,653 chars |

## Implication for the benchmark numbers

Every `mem0_real` measurement starting 2026-04-25 ~14:00 — including the
n=15 partial, the Tailscale-degraded n=64, both n=30 Phase B intermediates,
and the n=100 final — references **mem0's v3 single-pass ADD-only
algorithm with `ADDITIVE_EXTRACTION_PROMPT`**, not v2. No retroactive
correction needed for any of the numbers in
[agent-memory-benchmarks.md §7.1, §7.2, §7.3](./agent-memory-benchmarks.md)
or [agent-memory-prototype-optimization.md §7-§8](./agent-memory-prototype-optimization.md).

## Method (for future re-verification)

```bash
# 1. Locate dist-info
find .venv -name "mem0ai-*.dist-info" -type d -maxdepth 5

# 2. Provenance from dist-info
cat $DI/INSTALLER          # uv / pip / etc.
cat $DI/direct_url.json    # absent → PyPI; present → editable / git source
head -10 $DI/METADATA      # version

# 3. Active code path markers
grep -n "ADDITIVE_EXTRACTION_PROMPT" .venv/.../mem0/memory/main.py
grep -n "bm25\|additive\|EntityStore" .venv/.../mem0/memory/main.py

# 4. Hash for cross-env identity check
certutil -hashfile <main.py path> MD5     # Windows
md5sum <main.py path>                      # Linux

# 5. Python import check
.venv/.../python -c "from mem0.configs.prompts import ADDITIVE_EXTRACTION_PROMPT; print(len(ADDITIVE_EXTRACTION_PROMPT))"
```

If a future install diverges (different MD5 or missing `ADDITIVE_EXTRACTION_PROMPT`),
revisit the benchmark interpretation before drawing v2-vs-v3 conclusions.

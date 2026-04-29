# POC Findings — 2026-04-20

## Phase 1: probe_llm.py — PASS

The local vLLM endpoint is fully OpenAI-compatible.
- Serves `google/gemma-4-26B-A4B-it` via vLLM (262k context)
- No real API key needed (`sk-noop` accepted)
- Probe round-trip ~300ms

## Phase 2: oasis_one_agent.py — PASS

OASIS drives a single Twitter agent through the custom endpoint end-to-end.

### What worked
- `ModelFactory.create(model_platform=OPENAI_COMPATIBLE_MODEL, url=..., api_key=..., model_type=...)` wires OASIS to the local vLLM endpoint.
- `generate_twitter_agent_graph` built a 1-agent graph from a 1-row CSV (columns: `,user_id,name,username,following_agentid_list,previous_tweets,user_char,description`).
- `ManualAction(CREATE_POST)` succeeded — post written to the `post` table.
- `LLMAction()` succeeded — Gemma returned `do_nothing` through OASIS's tool-call flow. Valid end-to-end path for LLM-driven agents.
- SQLite schema OASIS creates includes: `post, comment, like, follow, mute, trace, user, rec, chat_group, group_members, group_messages, product, report` — matches social-platform expectations.

### Non-fatal warnings we must handle
1. **Recsys embedding model fails to load.** OASIS tries `Twitter/twhin-bert-base` from HuggingFace at step 2. On first run, download takes ~10 min on this link; eventually errors with "Failed to load the model: Twitter/twhin-bert-base" but the simulation continues (recs come back empty). Mitigations:
    - Pre-cache the model before running simulations.
    - Or run with the recsys disabled (need to inspect OASIS for a flag).
    - Or swap in a lighter embedding (nomic-embed-text via local Ollama) — would require a patch/fork.

2. **HuggingFace symlinks on Windows.** Warning that cache is degraded because symlinks need Developer Mode or admin. Set `HF_HUB_DISABLE_SYMLINKS_WARNING=1` to silence. Degraded cache uses more disk; not a correctness issue.

3. **`hf_xet` not installed.** Performance-only. Add `hf_xet` to the `[sim]` extras for faster HuggingFace downloads.

4. **Silent `social.twitter - ERROR - list index out of range` during first `env.reset()`.** Happens before recs cache is populated. Non-fatal; OASIS continues.

### Numbers
- camel-oasis install: 125 packages, ~16s install time after download
- Cold run wall-time: ~10 min (dominated by twhin-bert-base download)
- Warm run wall-time: ~seconds after model cached

## Next integration

- Expose OASIS wiring through `research_pipeline.simulation` module.
- Pre-cache `Twitter/twhin-bert-base` in the app bootstrap, OR patch to skip recsys for small agent pools (<50).
- Feed archetype system prompts into OASIS agent `description` field so the LLM gets proper role context.
- Put `HF_HUB_DISABLE_SYMLINKS_WARNING=1` and `TRANSFORMERS_OFFLINE=0` in the default env.

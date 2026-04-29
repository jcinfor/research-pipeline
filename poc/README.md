# Research Pipeline — POCs

Sequential validation before scaffolding the full app.

## Phase 1: `probe_llm.py`

Confirms the local LLM endpoint is OpenAI-compatible and reachable.

```bash
cd research-pipeline/poc
pip install openai httpx
python probe_llm.py
```

Configurable via env vars:
- `LLM_BASE_URL` (e.g. `http://localhost:9999/v1`)
- `LLM_API_KEY`  (default `sk-noop` — many local servers accept any string)
- `LLM_MODEL`    (default: first model returned by `/models`)

Paste the output back so we can lock in the config and move to phase 2.

## Phase 2: `oasis_one_agent.py` (next — blocked on phase 1 passing)

Drives OASIS with one agent, one Twitter turn, using the verified endpoint.

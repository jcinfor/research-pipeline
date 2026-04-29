"""Minimal probe to find m_flow's current failure mode.

Tries: add(small text) → memorize → query, with the env config from
mflow_real.py. Prints each stage's outcome separately so we can see
exactly where it breaks.
"""
from __future__ import annotations

import asyncio
import faulthandler
import os
import sys
import traceback
import uuid

# Dump Python traceback on segfault
faulthandler.enable(file=sys.stderr)

# Set env vars BEFORE importing m_flow (same as adapter does).
# Override VLLM_BASE_URL / OLLAMA_BASE_URL in your environment if your
# endpoints aren't on localhost.
_VLLM = os.environ.get("VLLM_BASE_URL", "http://localhost:9999/v1")
_OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_ENDPOINT", _VLLM)
os.environ.setdefault("LLM_MODEL", "openai/google/gemma-4-26B-A4B-it")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("OPENAI_API_KEY", "dummy")
os.environ.setdefault("OPENAI_BASE_URL", _VLLM)
os.environ.setdefault("MFLOW_EMBEDDING_PROVIDER", "ollama")
os.environ.setdefault("MFLOW_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
# Use Ollama's newer /api/embed endpoint (returns plural "embeddings"
# which is what m_flow's OllamaEmbeddingEngine parses; the legacy
# /api/embeddings returns singular "embedding" which m_flow can't parse).
os.environ.setdefault("MFLOW_EMBEDDING_ENDPOINT", f"{_OLLAMA}/api/embed")
os.environ.setdefault("MFLOW_EMBEDDING_DIMENSIONS", "1024")
os.environ.setdefault("MFLOW_HUGGINGFACE_TOKENIZER", "Qwen/Qwen3-Embedding-0.6B")
os.environ.setdefault("OLLAMA_API_BASE", _OLLAMA)
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

# Force tool_call mode for instructor: our vLLM endpoint doesn't have
# `--guided-decoding-backend` enabled, so requests with `response_format:
# json_schema` hang for the full client retry timeout. tool_call uses
# vLLM's tool-calling path which works without guided decoding.
os.environ.setdefault("MFLOW_LLM_INSTRUCTOR_MODE", "tool_call")

# On Ubuntu, lancedb (m_flow's default vector store) works — no need for
# the Windows-only chromadb sidecar workaround we used to need.


async def main():
    print("Stage 0: importing m_flow...")
    import m_flow
    print(f"  OK — version probe: dir size {len(dir(m_flow))}")
    print(f"  Has functions: add={hasattr(m_flow, 'add')}, memorize={hasattr(m_flow, 'memorize')}, query={hasattr(m_flow, 'query')}")

    dataset = f"probe_{uuid.uuid4().hex[:8]}"
    print(f"\nStage 1: add(text='Alice lives in Berlin.', dataset_name='{dataset}')")
    try:
        result = await m_flow.add(
            data="Alice lives in Berlin.",
            dataset_name=dataset,
        )
        print(f"  OK — result: {repr(result)[:200]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return

    print(f"\nStage 2: memorize(datasets='{dataset}')")
    try:
        result = await m_flow.memorize(datasets=dataset)
        print(f"  OK — result: {repr(result)[:200]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return

    print(f"\nStage 3: low-level search(query_type=TRIPLET_COMPLETION, use_combined_context=True)")
    # m_flow.query() is broken — its `_convert_to_query_result` expects
    # SearchResult objects but `_format_standard_results` actually returns
    # raw strings/dicts. The `_format_combined_result` path (chosen by
    # use_combined_context=True) does produce a real CombinedSearchResult,
    # so we bypass query() and call the underlying search() directly.
    from m_flow.api.v1.search.search import search as raw_search
    from m_flow.search.types import RecallMode
    try:
        result = await raw_search(
            query_text="Where does Alice live?",
            query_type=RecallMode.TRIPLET_COMPLETION,
            datasets=dataset,
            top_k=5,
            use_combined_context=True,
        )
        print(f"  OK — result type: {type(result).__name__}")
        print(f"  result attrs: {[a for a in dir(result) if not a.startswith('_')][:30]}")
        for attr in ("result", "answer", "response", "text", "summary", "episodes", "context"):
            val = getattr(result, attr, None)
            if val:
                print(f"    .{attr} = {repr(val)[:200]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

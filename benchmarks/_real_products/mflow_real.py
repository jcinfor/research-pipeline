"""Adapter wrapping the real `mflow-ai` package (cloned as a sibling of research-pipeline at science/m_flow).

m-flow has a two-step ingest pipeline (`add` → `memorize`) plus a graph-routed
search. ALL its public APIs are async coroutines, so we drive them from a
single persistent event loop per instance — creating a new loop per call is
unsafe because m_flow caches asyncio.Lock instances bound to the loop they
were first created in (silent "Lock bound to a different event loop" warnings
at scale). The persistent-loop pattern keeps m_flow's locks consistent.

Configuration: vLLM Gemma (chat) + Ollama qwen3-embedding via env vars below.

Retrieval path: we use the canonical `m_flow.search(query_type=EPISODIC)`
pattern from the upstream test suite (`examples/test_comprehensive_episodic.py`)
rather than `m_flow.query()` — `query()`'s upper-level wrapper has an
unconditional bug where `_format_standard_results` returns raw dicts/strings
but `_convert_to_query_result` expects SearchResult objects, raising
`AttributeError: 'str' object has no attribute 'search_result'`. Once we have
the episode list we run our own LLM synthesis (Gemma) instead of relying on
m_flow's TRIPLET_COMPLETION synthesizer, which proved overly cautious on
sparse contexts (returning "the provided context does not contain
information" even when the relevant evidence was present).
"""
from __future__ import annotations

import asyncio
import os
import threading
import uuid
from threading import Lock

from benchmarks.e1_blackboard_stress.corpus import Doc

# Serialize MFlowReal() construction across threads. m_flow has shared
# global state (kuzu DB, lancedb registry, SQLite metadata) that races
# under concurrent first-instantiation. Per-instance datasets isolate the
# steady-state add()/query() calls — only init needs to be serial.
_INIT_LOCK = Lock()


# --- Single shared event loop, owned by a dedicated background thread ---
#
# m_flow caches asyncio.Lock objects at module level (not per-instance) and
# binds them to whichever event loop they were first created in. With a
# fresh loop per MFlowReal instance, instance #2's call hits "Lock bound to
# a different event loop". Even sequential construction has this problem,
# because the second instance still gets a different loop than the cached
# Locks. The fix: every MFlowReal call dispatches to ONE loop running
# permanently in a dedicated thread. All Locks are bound to that loop.
#
# Performance tradeoff: with N benchmark workers all dispatching to the
# same loop, async LLM calls parallelize fine but **sync** kuzu graph
# queries and lancedb vector ops serialize, with cross-worker lock-handoff
# overhead on top. For benchmarks running m_flow concurrently with other
# systems (e.g. Phase C with prototype + multitier + mem0_real), this is
# fine — m_flow effectively gets ~1 worker while the others use the rest.
# For m_flow-only runs, prefer `--max-workers 1`: same effective
# parallelism, no contention overhead. See
# benchmarks/longmemeval/results/run_oracle_20260428_044526.md
# "Operational note" for the empirical finding.
_LOOP_LOCK = Lock()
_SHARED_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_THREAD: threading.Thread | None = None


def _get_shared_loop() -> asyncio.AbstractEventLoop:
    """Lazily start the dedicated event-loop thread."""
    global _SHARED_LOOP, _LOOP_THREAD
    with _LOOP_LOCK:
        if _SHARED_LOOP is not None and not _SHARED_LOOP.is_closed():
            return _SHARED_LOOP
        loop = asyncio.new_event_loop()

        def _run_forever():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        t = threading.Thread(target=_run_forever, name="mflow-loop", daemon=True)
        t.start()
        _SHARED_LOOP = loop
        _LOOP_THREAD = t
        return loop


def _run_on_shared_loop(coro):
    """Submit a coroutine to the shared loop and block until it completes."""
    loop = _get_shared_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    return fut.result()


# Backend defaults — override via VLLM_BASE_URL / OLLAMA_BASE_URL env vars
# before invoking. The local-vLLM and local-Ollama hostnames assume a single
# workstation; for a split LAN setup, export both env vars before running.
_VLLM = os.environ.get("VLLM_BASE_URL", "http://localhost:9999/v1")
_OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# m_flow uses LiteLLM internally. Configure both chat LLM (vLLM Gemma) and
# the embedder (Ollama qwen3-embedding) BEFORE importing m_flow.
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_ENDPOINT", _VLLM)
os.environ.setdefault("LLM_MODEL", "openai/google/gemma-4-26B-A4B-it")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("OPENAI_API_KEY", "dummy")
os.environ.setdefault("OPENAI_BASE_URL", _VLLM)

# Embedding config: m_flow uses MFLOW_EMBEDDING_* env vars (env_prefix="MFLOW_").
# Default would call OpenAI text-embedding-3-large; redirect to Ollama qwen3.
os.environ.setdefault("MFLOW_EMBEDDING_PROVIDER", "ollama")
os.environ.setdefault("MFLOW_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
# Use Ollama's newer /api/embed endpoint (returns plural "embeddings"
# which m_flow's OllamaEmbeddingEngine parses; the legacy /api/embeddings
# returns singular "embedding" which makes m_flow KeyError on 'data').
os.environ.setdefault("MFLOW_EMBEDDING_ENDPOINT", f"{_OLLAMA}/api/embed")
os.environ.setdefault("MFLOW_EMBEDDING_DIMENSIONS", "1024")
# m_flow's OllamaEmbeddingEngine builds an HF tokenizer for prompt truncation.
# Default ("Salesforce/SFR-Embedding-Mistral") is gated; use a public model
# whose tokenizer matches the embedder we're actually using.
os.environ.setdefault("MFLOW_HUGGINGFACE_TOKENIZER", "Qwen/Qwen3-Embedding-0.6B")
# LiteLLM Ollama provider needs OLLAMA_API_BASE
os.environ.setdefault("OLLAMA_API_BASE", _OLLAMA)

# Disable multi-user access control for benchmarking single-user
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

# Force tool_call instructor mode: our vLLM endpoint doesn't have
# `--guided-decoding-backend` enabled, so the default `json_schema_mode`
# hangs each request through its retry timeout. tool_call uses vLLM's
# tool-calling path which works without guided decoding (0.45s vs ≥60s).
os.environ.setdefault("MFLOW_LLM_INSTRUCTOR_MODE", "tool_call")

# Episodic-pipeline knobs the m_flow team enables in their own quality
# tests (examples/test_comprehensive_episodic.py). Without these the
# graph is built without the FacetPoint layer where the literal evidence
# lives, so retrieval has only Episode-level summaries to return — which
# crushes multi-session recall. Setting them brings the build path in
# line with how m_flow's authors run it for benchmark numbers.
os.environ.setdefault("MFLOW_EPISODIC_ENABLED", "true")
os.environ.setdefault("MFLOW_EPISODIC_ENABLE_FACET_POINTS", "true")
os.environ.setdefault("MFLOW_EPISODIC_POINT_REFINER", "true")
os.environ.setdefault("MFLOW_EPISODIC_RETRIEVER_MODE", "bundle")


# Same backend env-override pattern for the answer-synthesis LLM call below.
VLLM_BASE_URL = _VLLM
GEMMA_MODEL = os.environ.get("VLLM_MODEL", "google/gemma-4-26B-A4B-it")


class MFlowReal:
    """Real m-flow wrapped in our Lite-system interface (ingest/query).

    Each instance owns a unique dataset_name (so concurrent benchmark
    workers' graphs don't collide) and a persistent asyncio event loop
    (so m_flow's cached Locks remain valid across calls).

    Calls memorize() lazily on first query() so we don't rebuild the
    graph after every ingest.
    """

    def __init__(self, dataset_name: str | None = None):
        # Lazy import — m_flow's import is heavy (FastAPI app, logging setup).
        # Serialize construction across threads (see _INIT_LOCK above).
        with _INIT_LOCK:
            import m_flow
            self._mflow = m_flow
            # Touch the shared loop early so m_flow's first internal Lock
            # creation (which happens during the first `add` call) binds
            # to the dedicated thread's loop, not whatever loop happens
            # to be running on the caller's thread.
            _get_shared_loop()
            self.dataset_name = dataset_name or f"rp_{uuid.uuid4().hex[:8]}"
            self._memorized = False

    def _run_async(self, coro):
        return _run_on_shared_loop(coro)

    def ingest(self, doc: Doc) -> None:
        """Register doc with m-flow's add() pipeline. Doesn't run the
        graph-construction step yet (memorize is deferred to first query)."""
        try:
            self._run_async(self._mflow.add(
                data=doc.text,
                dataset_name=self.dataset_name,
            ))
            self._memorized = False
        except Exception as e:
            print(f"[mflow_real] add failed on {doc.id}: {str(e)[:140]}")

    def _memorize_if_needed(self) -> None:
        if self._memorized:
            return
        try:
            self._run_async(self._mflow.memorize(datasets=self.dataset_name))
            self._memorized = True
        except Exception as e:
            print(f"[mflow_real] memorize failed: {str(e)[:140]}")

    def query(self, question: str, as_of: str | None = None) -> str:
        # Build the graph if it hasn't been built since the last add().
        self._memorize_if_needed()

        # Use TRIPLET_COMPLETION + use_combined_context=True: this is the
        # path m_flow's own benchmarks use. It runs the full bundle-aware
        # synthesizer (with the Episode/Facet/FacetPoint cone in context)
        # and returns CombinedSearchResult with .result already containing
        # m_flow's own LLM-synthesized natural-language answer.
        #
        # We bypass the public `m_flow.query()` wrapper because its
        # `_convert_to_query_result` expects SearchResult objects but the
        # standard-formatter actually returns raw dicts — `query()` raises
        # AttributeError on the list path. Calling the lower-level search()
        # with use_combined_context=True forces the combined-formatter,
        # which returns a real CombinedSearchResult.
        from m_flow.api.v1.search.search import search as raw_search
        from m_flow.search.types import RecallMode
        try:
            result = self._run_async(raw_search(
                query_text=question,
                query_type=RecallMode.TRIPLET_COMPLETION,
                datasets=self.dataset_name,
                top_k=10,
                use_combined_context=True,
            ))
        except Exception as e:
            return f"(mflow retrieval error: {str(e)[:140]})"

        # CombinedSearchResult.result is m_flow's bundle-synthesized answer.
        answer = getattr(result, "result", None)
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
        if answer:
            return str(answer)[:600]

        # Fallback to context if the synthesizer returned nothing.
        ctx = getattr(result, "context", None)
        if ctx:
            return str(ctx)[:600]
        return "(no answer)"


_TEXT_KEYS = ("search_text", "summary", "edge_text", "description", "name", "text", "content")
_NESTED_KEYS = ("node_1", "node_2", "edge", "node1", "node2")


def _extract_text(item) -> str | None:
    """Pull retrievable text from one m_flow search-result item.

    Items can be strings, dicts (with possibly-nested edge/node payloads),
    or Pydantic objects exposing .payload or .__dict__. Mirrors the access
    pattern in m_flow's own examples/test_retrieval_15events.py.
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        parts: list[str] = []
        for key in _TEXT_KEYS:
            v = item.get(key)
            if v:
                parts.append(str(v))
        for nkey in _NESTED_KEYS:
            nested = item.get(nkey)
            if isinstance(nested, dict):
                for inner in _TEXT_KEYS:
                    v = nested.get(inner)
                    if v:
                        parts.append(str(v))
        return " | ".join(parts) if parts else None
    payload = getattr(item, "payload", None)
    if payload:
        return str(payload)[:1000]
    if hasattr(item, "__dict__"):
        d = item.__dict__
        parts = [str(v) for v in d.values() if v]
        return " | ".join(parts)[:1000] if parts else None
    return None

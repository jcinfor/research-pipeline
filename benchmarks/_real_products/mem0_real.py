"""Adapter wrapping the real `mem0ai` package so it can be benchmarked
alongside our Lite reimplementations.

Closes Gap 1 ("we've been testing reimplementations, not real products").
We can run our existing E1/E8/E11/etc benchmarks through this adapter and
compare real mem0's behavior to our `Mem0Lite`.

Configuration: points mem0 at the same backend the rest of our research
uses — a local vLLM endpoint (OpenAI-compatible) for chat + a local Ollama
endpoint for embeddings. Defaults assume `localhost`; override via
`VLLM_BASE_URL` / `OLLAMA_BASE_URL` env vars if your endpoints are elsewhere.
"""
from __future__ import annotations

import os
from threading import Lock
from typing import Any

# Disable mem0's internal telemetry vector store BEFORE importing mem0.
# mem0 creates a second hard-coded Qdrant client at ~/.mem0/migrations_qdrant
# for migration tracking — that path is a singleton, so concurrent
# `Memory.from_config()` constructions race on the SQLite file lock and one
# raises `RuntimeError: Storage folder ... is already accessed by another
# instance of Qdrant client`. Setting MEM0_TELEMETRY=false skips the entire
# telemetry-store creation path. (Verified on mem0 source 2026-04-26 via
# `mem0/memory/main.py:360 if MEM0_TELEMETRY:`.)
os.environ.setdefault("MEM0_TELEMETRY", "false")

# Belt-and-suspenders: serialize Mem0Real() construction across threads.
# Concurrent ingest()/query() is fine afterwards — only the constructor
# touches mem0's shared internal state.
_INIT_LOCK = Lock()

from benchmarks.e1_blackboard_stress.corpus import Doc


# Backend defaults — override by exporting VLLM_BASE_URL / OLLAMA_BASE_URL
# in the environment before running benchmarks.
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:9999/v1")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
GEMMA_MODEL = os.environ.get("VLLM_MODEL", "google/gemma-4-26B-A4B-it")
QWEN_EMBED_MODEL = "qwen3-embedding:0.6b"
QWEN_EMBED_DIMS = 1024


def _qdrant_path(suffix: str = "") -> str:
    """Cross-platform path for the local Qdrant store.

    A unique suffix per Mem0Real instance avoids SQLite-lock contention
    when multiple instances are constructed concurrently (the file-based
    Qdrant uses SQLite internally and serializes writers to a single .db
    file even across collections)."""
    base = os.path.join(
        os.environ.get("TMPDIR", "/tmp"),
        f"mem0_real_qdrant_{suffix}" if suffix else "mem0_real_qdrant",
    )
    os.makedirs(base, exist_ok=True)
    return base


def build_mem0_config(*, collection: str = "rp_bench", path_suffix: str = "") -> dict[str, Any]:
    """Wire real mem0 to our vLLM + Ollama backends. The OpenAI provider
    accepts an `openai_base_url`, which is how we point it at vLLM."""
    return {
        "llm": {
            "provider": "openai",
            "config": {
                "model": GEMMA_MODEL,
                "openai_base_url": VLLM_BASE_URL,
                "api_key": "dummy",  # vLLM accepts any token
                "max_tokens": 1024,
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": QWEN_EMBED_MODEL,
                "ollama_base_url": OLLAMA_BASE_URL,
                "embedding_dims": QWEN_EMBED_DIMS,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": collection,
                "embedding_model_dims": QWEN_EMBED_DIMS,
                "path": _qdrant_path(path_suffix),
                "on_disk": True,
            },
        },
    }


def mem0_provenance() -> str:
    """One-line description of which mem0 package the runner is actually
    calling — for embedding in benchmark result file headers.

    Returns one of:
      - "mem0ai==<version> (PyPI)"  — installed from PyPI
      - "mem0ai (editable @ <git-sha>)"  — editable install from a git clone
      - "mem0ai (editable, no git)"  — editable install but no SHA detectable
      - "mem0ai (unknown)"  — couldn't probe

    Includes a v3 marker check (ADDITIVE_EXTRACTION_PROMPT) so the report
    header explicitly states whether v3 algorithm code is present.
    """
    import importlib.metadata
    import importlib.util
    import subprocess
    try:
        version = importlib.metadata.version("mem0ai")
    except importlib.metadata.PackageNotFoundError:
        return "mem0ai (not installed)"
    try:
        v3_marker = importlib.util.find_spec("mem0.configs.prompts") is not None
        if v3_marker:
            from mem0.configs import prompts as _p
            v3_marker = hasattr(_p, "ADDITIVE_EXTRACTION_PROMPT")
    except Exception:
        v3_marker = False
    v3_tag = " v3-algo" if v3_marker else " v2-algo"
    try:
        # If mem0 was installed editable, find the package source dir + git SHA
        spec = importlib.util.find_spec("mem0")
        if spec is None or spec.origin is None:
            return f"mem0ai=={version}{v3_tag} (origin unknown)"
        pkg_dir = os.path.dirname(spec.origin)
        # Walk up to find a .git directory
        d = pkg_dir
        for _ in range(6):
            if os.path.isdir(os.path.join(d, ".git")):
                sha = subprocess.run(
                    ["git", "-C", d, "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()
                if sha:
                    return f"mem0ai (editable @ {sha}){v3_tag}"
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return f"mem0ai=={version}{v3_tag} (PyPI)"
    except Exception:
        return f"mem0ai=={version}{v3_tag} (probe failed)"


class Mem0Real:
    """Real mem0 wrapped in our Lite-system interface (ingest/query).

    Maps:
      ingest(doc) → mem0.Memory.add(...)
      query(question) → mem0.Memory.search(...) + LLM-formulated answer

    Quirk: mem0's add() takes either a string (treated as a single user
    message) or a list of message dicts. We use the string form. Each Doc
    becomes one add() call, with metadata recording (id, pub_date).

    Note: mem0 assumes a conversational user_id model. For benchmarking
    we use a single fixed user_id per benchmark run.
    """

    def __init__(self, user_id: str = "rp_bench_user", collection: str | None = None):
        # Serialize construction — mem0 has shared internal state during
        # __init__ (telemetry store + cached config) that races under
        # concurrent instantiation. Once constructed, ingest()/query()
        # are safe in parallel.
        with _INIT_LOCK:
            import uuid
            from mem0 import Memory
            # Each instance gets its own collection AND its own qdrant path
            # so concurrent benchmarks don't bottleneck on Qdrant's SQLite
            # lock for the actual memory store. Always append a uuid to the
            # path_suffix so two callers passing the same `collection` name
            # (e.g. runners using `int(time.time())` for naming, which
            # collides for parallel workers within the same second) still
            # get distinct on-disk Qdrant stores. The collection name itself
            # stays as the caller asked, since it's only used as a logical
            # qdrant collection identifier.
            coll = collection or f"rp_{id(self):x}"
            unique_suffix = f"{coll}_{uuid.uuid4().hex[:8]}"
            cfg = build_mem0_config(collection=coll, path_suffix=unique_suffix)
            self.memory = Memory.from_config(cfg)
            self.user_id = user_id
            try:
                self.memory.reset()
            except Exception:
                pass

    def ingest(self, doc: Doc) -> None:
        # mem0 wants natural-language messages. The benchmark Docs already
        # contain natural-language text describing the observation, so we
        # pass it as a single user message and let mem0's pipeline extract
        # facts via its own internal LLM call.
        try:
            self.memory.add(
                doc.text,
                user_id=self.user_id,
                metadata={"doc_id": doc.id, "pub_date": doc.pub_date},
            )
        except Exception as e:
            print(f"[mem0_real] add failed on {doc.id}: {str(e)[:120]}")

    def query(self, question: str, as_of: str | None = None) -> str:
        # mem0.search returns a list of memory items. We need to synthesize
        # an answer from them, like our other systems do for fairness.
        try:
            # mem0 v2 requires user_id in filters (not as top-level kwarg).
            results = self.memory.search(
                query=question,
                filters={"user_id": self.user_id},
                top_k=10,
            )
        except Exception as e:
            return f"(mem0 search error: {str(e)[:120]})"

        # mem0 v2 returns dict-like results. Format keys vary; handle robustly.
        items = results if isinstance(results, list) else results.get("results", [])
        if not items:
            return "(no memory)"

        # Format memory snippets as a concise context list and ask the
        # configured LLM (the same one mem0 uses) to answer.
        memory_lines: list[str] = []
        for it in items[:10]:
            if isinstance(it, dict):
                text = it.get("memory") or it.get("text") or it.get("data") or ""
                meta = it.get("metadata") or {}
                pub = meta.get("pub_date") or it.get("created_at") or ""
                memory_lines.append(f"- {text}  [{pub}]" if pub else f"- {text}")
            else:
                memory_lines.append(f"- {it}")
        ctx = "\n".join(memory_lines) or "(no usable items)"

        # Use mem0's underlying LLM to produce the answer (keeps backend
        # consistent with how mem0 normally handles a user turn). We bypass
        # mem0's higher-level conversational chain since our benchmarks
        # ask discrete factual questions.
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=VLLM_BASE_URL,
                api_key="dummy",
            )
            resp = client.chat.completions.create(
                model=GEMMA_MODEL,
                messages=[
                    {"role": "system", "content": (
                        "Answer the question using the memory items below. "
                        "If the memory does not contain the answer, say so honestly. "
                        "Be concise — return just the value when possible."
                    )},
                    {"role": "user", "content": (
                        f"MEMORY ITEMS:\n{ctx}\n\nQUESTION: {question}\nAnswer:"
                    )},
                ],
                max_tokens=600, temperature=0.1,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return f"(answer-LLM error: {str(e)[:120]})"

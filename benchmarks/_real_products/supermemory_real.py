"""Adapter wrapping the real Supermemory hosted SaaS (api.supermemory.ai).

Configuration: requires SUPERMEMORY_API_KEY in benchmarks/.env.
Supermemory's hosted service uses its own LLM internally for fact extraction.
We cannot point it at our local Gemma. As with ZepReal, this means
extractor-quality differences confound architectural comparison.

Adapter mapping:
    ingest → client.documents.add(content=text, container_tag=user, task_type='memory')
    query  → client.search.memories(q=question, container_tag=user) + LLM-formulated answer

The README claims #1 on LongMemEval/LoCoMo/ConvoMem — we'll get to verify.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from benchmarks.e1_blackboard_stress.corpus import Doc
from benchmarks._real_products.zep_real import _load_dotenv

# Read benchmarks/.env so SUPERMEMORY_API_KEY is available.
_load_dotenv()


VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:9999/v1")
GEMMA_MODEL = os.environ.get("VLLM_MODEL", "google/gemma-4-26B-A4B-it")


class SupermemoryReal:
    """Real Supermemory wrapped in our Lite-system interface.

    Uses container_tag (one per instance) to isolate benchmark runs.
    Answer synthesis uses our local Gemma — same protocol as mem0_real /
    zep_real for fairness on the answer-generation step.
    """

    def __init__(self, container_tag: str | None = None,
                 warmup_seconds: float = 8.0):
        from supermemory import Supermemory
        api_key = os.environ.get("SUPERMEMORY_API_KEY")
        if not api_key:
            raise RuntimeError(
                "SUPERMEMORY_API_KEY not set. Add it to benchmarks/.env"
            )
        self.client = Supermemory(api_key=api_key)
        self.container_tag = container_tag or f"rp_bench_{uuid.uuid4().hex[:8]}"
        self._warmup_seconds = warmup_seconds
        self._has_pending_writes = False

    def flush(self) -> None:
        """Wait for Supermemory's async ingestion to process recently-added
        documents. Called before the first query following any ingest."""
        if not self._has_pending_writes:
            return
        time.sleep(self._warmup_seconds)
        self._has_pending_writes = False

    def ingest(self, doc: Doc) -> None:
        """Push doc text into Supermemory under our container tag."""
        try:
            self.client.documents.add(
                content=doc.text,
                container_tag=self.container_tag,
                task_type="memory",
                custom_id=doc.id,
                metadata={"pub_date": doc.pub_date},
            )
            self._has_pending_writes = True
        except Exception as e:
            print(f"[supermemory_real] add failed on {doc.id}: {str(e)[:140]}")

    def query(self, question: str, as_of: str | None = None) -> str:
        """Search Supermemory + synthesize answer via local Gemma. Flushes
        async writes before the first query."""
        self.flush()
        try:
            results = self.client.search.memories(
                q=question,
                container_tag=self.container_tag,
                limit=10,
                search_mode="memories",
            )
        except Exception as e:
            return f"(supermemory search error: {str(e)[:140]})"

        # The response shape varies — try common attribute names robustly
        items = (
            getattr(results, "results", None)
            or getattr(results, "memories", None)
            or getattr(results, "data", None)
            or []
        )

        if not items:
            return "(no memories)"

        memory_lines: list[str] = []
        for it in items[:10]:
            # items might be Pydantic models or dicts
            if hasattr(it, "model_dump"):
                d = it.model_dump()
            elif isinstance(it, dict):
                d = it
            else:
                d = {"raw": str(it)}
            content = (
                d.get("content") or d.get("memory") or d.get("text")
                or d.get("summary") or d.get("raw") or ""
            )
            memory_lines.append(f"- {str(content)[:200]}")
        ctx = "\n".join(memory_lines) or "(no usable items)"

        # Synthesize via local Gemma (fairness with mem0_real / zep_real)
        try:
            from openai import OpenAI
            client = OpenAI(base_url=VLLM_BASE_URL, api_key="dummy")
            resp = client.chat.completions.create(
                model=GEMMA_MODEL,
                messages=[
                    {"role": "system", "content": (
                        "Answer the question using the memory items below. "
                        "If the memory doesn't contain the answer, say so honestly. "
                        "Be concise — return just the value when possible."
                    )},
                    {"role": "user", "content": (
                        f"MEMORY ITEMS:\n{ctx}\n\nQUESTION: {question}\nAnswer:"
                    )},
                ],
                max_tokens=200, temperature=0.1,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return f"(answer-LLM error: {str(e)[:120]})"

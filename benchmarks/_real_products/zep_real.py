"""Adapter wrapping the real Zep cloud (hosted SaaS at app.getzep.com).

Configuration: requires ZEP_API_KEY in benchmarks/.env. Zep's cloud uses
its own LLM internally for fact extraction — we cannot point it at our
local Gemma. This means **direct numeric comparison to mem0_real /
prototype is biased by extractor differences**, not just architecture.

API used:
  ingest → thread.add_messages(thread_id, messages=[Message...])
  query  → thread.get_user_context(thread_id) + LLM-formulated answer

The thread-based ingest path is the canonical Zep API for conversational
data and is more synchronous than graph.add (which has a longer async
fact-extraction queue). Speakers' names are passed via Message.name so
Zep treats them as distinct entities.
"""
from __future__ import annotations

import os
import re
import time
import uuid
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=SyntaxWarning, module="zep_cloud")

from benchmarks.e1_blackboard_stress.corpus import Doc


def _load_dotenv() -> None:
    """Read benchmarks/.env and set keys we need into os.environ."""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:9999/v1")
GEMMA_MODEL = os.environ.get("VLLM_MODEL", "google/gemma-4-26B-A4B-it")

# Match LoCoMo turn text format "[Speaker Name] message text" so we can
# extract the speaker and pass it to Zep's Message.name field.
_SPEAKER_PREFIX_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(.*)", re.DOTALL)


class ZepReal:
    """Real Zep cloud, conversational-thread API.

    Ingest path: each Doc becomes one message in a single thread per
    instance. Speaker name (parsed from text prefix) is passed to Zep so
    the entity graph treats each speaker as a distinct node.

    Query path: thread.get_user_context returns Zep-synthesized context;
    we feed that into our local Gemma for the final answer (matching the
    fairness protocol used by mem0_real / supermemory_real).

    Async note: even the thread API is partially async. Use warmup_seconds
    (default 60s) to give Zep time to process before queries.
    """

    def __init__(self, user_id: str | None = None,
                 thread_id: str | None = None,
                 warmup_seconds: float = 60.0,
                 batch_size: int = 30):
        from zep_cloud.client import Zep
        api_key = os.environ.get("ZEP_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ZEP_API_KEY not set. Add it to benchmarks/.env"
            )
        self.client = Zep(api_key=api_key)
        self.user_id = user_id or f"rp_user_{uuid.uuid4().hex[:8]}"
        self.thread_id = thread_id or f"rp_thread_{uuid.uuid4().hex[:8]}"
        self._warmup_seconds = warmup_seconds
        self._batch_size = batch_size
        self._has_pending_writes = False
        self._pending_messages: list = []  # buffer for batch ingest

        try:
            self.client.user.add(
                user_id=self.user_id,
                first_name="rp_bench",
                email=f"{self.user_id}@example.com",
            )
        except Exception as e:
            print(f"[zep_real] user.add note: {str(e)[:80]}")
        try:
            self.client.thread.create(
                thread_id=self.thread_id, user_id=self.user_id,
            )
        except Exception as e:
            print(f"[zep_real] thread.create note: {str(e)[:80]}")

    @staticmethod
    def _parse_speaker(text: str) -> tuple[str | None, str]:
        m = _SPEAKER_PREFIX_RE.match(text)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return None, text

    def _flush_buffer(self) -> None:
        """Send any buffered messages to Zep in a single batch."""
        if not self._pending_messages:
            return
        try:
            self.client.thread.add_messages(
                self.thread_id, messages=self._pending_messages,
            )
            self._has_pending_writes = True
        except Exception as e:
            print(f"[zep_real] add_messages batch failed: {str(e)[:140]}")
        self._pending_messages = []

    def flush(self) -> None:
        """Drain message buffer + wait for async fact extraction."""
        self._flush_buffer()
        if self._has_pending_writes:
            time.sleep(self._warmup_seconds)
            self._has_pending_writes = False

    def ingest(self, doc: Doc) -> None:
        """Buffer this turn as a Zep Message; flushes in batches of
        batch_size. Final flush happens on first query."""
        from zep_cloud.types import Message
        speaker, content = self._parse_speaker(doc.text)
        msg = Message(
            role="user",
            name=speaker or "unknown",
            content=content or doc.text,
        )
        self._pending_messages.append(msg)
        if len(self._pending_messages) >= self._batch_size:
            self._flush_buffer()

    def query(self, question: str, as_of: str | None = None) -> str:
        """Get Zep's synthesized thread context, then synthesize a final
        answer via local Gemma."""
        self.flush()
        try:
            ctx_resp = self.client.thread.get_user_context(self.thread_id)
            ctx_text = getattr(ctx_resp, "context", "") or ""
        except Exception as e:
            return f"(zep get_user_context error: {str(e)[:140]})"

        if not ctx_text.strip():
            ctx_text = "(no context)"

        try:
            from openai import OpenAI
            client = OpenAI(base_url=VLLM_BASE_URL, api_key="dummy")
            resp = client.chat.completions.create(
                model=GEMMA_MODEL,
                messages=[
                    {"role": "system", "content": (
                        "Answer the question using the conversation context "
                        "below. The context summarizes facts and recent "
                        "messages from the conversation. If it doesn't "
                        "contain the answer, say so honestly. Be concise."
                    )},
                    {"role": "user", "content": (
                        f"CONTEXT:\n{ctx_text[:6000]}\n\n"
                        f"QUESTION: {question}\nAnswer:"
                    )},
                ],
                max_tokens=200, temperature=0.1,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return f"(answer-LLM error: {str(e)[:120]})"

"""Tests for post-level dedup in simulation._generate_unique_post."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from research_pipeline.simulation import _generate_unique_post


@dataclass
class _Msg:
    content: str


@dataclass
class _Choice:
    message: _Msg


@dataclass
class _Resp:
    choices: list[_Choice]


class _FakeLLM:
    """First call returns `first`; second call returns `retry`.
    embed() uses a text->axis registry for deterministic orthogonality."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._axes: dict[str, int] = {}

    async def achat(self, role, messages, **kwargs):
        text = self._responses.pop(0) if self._responses else ""
        return _Resp(choices=[_Choice(message=_Msg(content=text))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        vecs = []
        for t in texts:
            key = t.strip().lower()
            if key not in self._axes:
                self._axes[key] = len(self._axes)
            v = [0.0] * 64
            v[self._axes[key]] = 1.0
            vecs.append(v)
        return vecs


def test_first_attempt_passes_when_unique():
    # Register "prior post" -> axis 0 so avoid[0] matches it, and the generated
    # "a wholly novel thought" gets axis 1 (orthogonal to avoid).
    llm = _FakeLLM(responses=["a wholly novel thought"])
    llm.embed("embedding", "prior post")
    avoid = [[1.0] + [0.0] * 63]  # axis 0 == 'prior post'
    content, emb = asyncio.run(
        _generate_unique_post(
            llm, system_msg="sys", user_msg="u", avoid_embeddings=avoid
        )
    )
    assert content == "a wholly novel thought"
    assert emb is not None


def test_duplicate_triggers_retry_then_accepts():
    # "first thought" -> axis 0 (matches avoid) -> retry.
    # "second thought" -> axis 1 (orthogonal) -> accepted.
    llm = _FakeLLM(responses=["first thought", "second thought"])
    llm.embed("embedding", "first thought")   # axis 0
    avoid = [[1.0] + [0.0] * 63]              # axis 0
    content, emb = asyncio.run(
        _generate_unique_post(
            llm, system_msg="sys", user_msg="u",
            avoid_embeddings=avoid, threshold=0.5,
        )
    )
    assert content == "second thought"
    assert emb is not None


def test_both_attempts_duplicate_returns_none():
    llm = _FakeLLM(responses=["same text", "same text"])
    llm.embed("embedding", "same text")  # axis 0
    avoid = [[1.0] + [0.0] * 63]          # axis 0
    content, emb = asyncio.run(
        _generate_unique_post(
            llm, system_msg="sys", user_msg="u",
            avoid_embeddings=avoid, threshold=0.5,
        )
    )
    assert content is None
    assert emb is None


def test_empty_avoid_set_skips_check():
    llm = _FakeLLM(responses=["anything"])
    content, emb = asyncio.run(
        _generate_unique_post(
            llm, system_msg="sys", user_msg="u", avoid_embeddings=[]
        )
    )
    assert content == "anything"
    assert emb is None

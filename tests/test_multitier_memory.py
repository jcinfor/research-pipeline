"""Tests for MultiTierMemory — episode summarization tier on top of PrototypeMemory."""
from __future__ import annotations

import json
from dataclasses import dataclass

from benchmarks.e1_blackboard_stress.systems import (
    MultiTierMemory, PrototypeMemory, _compute_episode_facets,
)


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _ScriptedLLM:
    def __init__(self, responses=None):
        self._q = list(responses) if responses else []
        self.calls = 0

    def chat(self, role, messages, **kwargs):
        self.calls += 1
        text = self._q.pop(0) if self._q else "(default)"
        return _Resp(choices=[_Choice(message=_Msg(content=text))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        return [[1.0] * 32 for _ in texts]


def _add_n_triples(mem, n: int, base_entity: str = "Alice"):
    """Helper: add n triples deterministically."""
    for i in range(n):
        mem.add_triple(
            entity=base_entity, attribute="status", value=f"v{i % 3}",
            valid_from=f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00",
            source_doc=f"doc_{i:06d}",
        )


# -- Episode facet computation --


def test_compute_episode_facets_first_last_transitions():
    triples = [
        {"entity": "Alice", "attribute": "status", "value": "active",
         "valid_from": "2026-01-01T00:00:00", "source_doc": "d1"},
        {"entity": "Alice", "attribute": "status", "value": "active",
         "valid_from": "2026-01-02T00:00:00", "source_doc": "d2"},
        {"entity": "Alice", "attribute": "status", "value": "blocked",
         "valid_from": "2026-01-03T00:00:00", "source_doc": "d3"},
        {"entity": "Alice", "attribute": "status", "value": "active",
         "valid_from": "2026-01-04T00:00:00", "source_doc": "d4"},
    ]
    facets = _compute_episode_facets(triples)
    f = facets[("alice", "status")]
    assert f["first_value"] == "active"
    assert f["first_at"] == "2026-01-01T00:00:00"
    assert f["last_value"] == "active"
    assert f["last_at"] == "2026-01-04T00:00:00"
    # Transitions: active -> blocked -> active = 2
    assert f["transition_count"] == 2
    assert f["value_counts"] == {"active": 3, "blocked": 1}


def test_compute_facets_separates_entities_and_attributes():
    triples = [
        {"entity": "Alice", "attribute": "role", "value": "lead",
         "valid_from": "2026-01-01T00:00:00", "source_doc": "d1"},
        {"entity": "Bob", "attribute": "role", "value": "contributor",
         "valid_from": "2026-01-02T00:00:00", "source_doc": "d2"},
        {"entity": "Alice", "attribute": "status", "value": "active",
         "valid_from": "2026-01-03T00:00:00", "source_doc": "d3"},
    ]
    facets = _compute_episode_facets(triples)
    assert ("alice", "role") in facets
    assert ("bob", "role") in facets
    assert ("alice", "status") in facets
    assert facets[("alice", "role")]["last_value"] == "lead"
    assert facets[("bob", "role")]["last_value"] == "contributor"


# -- Compression triggers --


def test_no_compression_below_episode_size():
    llm = _ScriptedLLM()
    mem = MultiTierMemory(llm, episode_size=10)
    _add_n_triples(mem, 5)
    assert len(mem.episodes) == 0
    assert len(mem.triples) == 5


def test_compression_fires_at_episode_size():
    llm = _ScriptedLLM()
    mem = MultiTierMemory(llm, episode_size=10)
    _add_n_triples(mem, 12)
    assert len(mem.episodes) == 1
    assert mem.episodes[0].triple_count == 10
    # 2 leftover unsummarized
    uncompressed = [t for t in mem.triples if t["source_doc"] not in mem._compressed_ids]
    assert len(uncompressed) == 2


def test_multiple_episodes_form_at_higher_volumes():
    llm = _ScriptedLLM()
    mem = MultiTierMemory(llm, episode_size=10)
    _add_n_triples(mem, 35)
    # 3 full episodes (30 triples) + 5 leftover
    assert len(mem.episodes) == 3
    assert all(ep.triple_count == 10 for ep in mem.episodes)


def test_compression_is_deterministic_no_llm_by_default():
    llm = _ScriptedLLM()
    mem = MultiTierMemory(llm, episode_size=10, use_llm_for_nl_summary=False)
    _add_n_triples(mem, 10)
    # Compression itself made zero LLM calls (programmatic-only)
    assert llm.calls == 0
    assert mem.episodes[0].summary_text == ""


def test_compression_invokes_llm_when_nl_summary_enabled():
    llm = _ScriptedLLM(responses=["Episode summary: 10 observations of Alice."])
    mem = MultiTierMemory(
        llm, episode_size=10, use_llm_for_nl_summary=True,
    )
    _add_n_triples(mem, 10)
    assert llm.calls == 1
    assert "Alice" in mem.episodes[0].summary_text


# -- Historical query routing (small vs large corpus) --


def test_small_corpus_uses_inherited_full_history_path():
    """Below history_summary_threshold, MultiTierMemory must behave exactly
    like PrototypeMemory on historical queries — exposing all triples."""
    llm = _ScriptedLLM(responses=["historical", "the first value was v0"])
    mem = MultiTierMemory(llm, episode_size=10, history_summary_threshold=10)
    _add_n_triples(mem, 5)
    answer = mem.query("What was the initial status?")
    assert "v0" in answer
    # Two LLM calls: intent classifier + answer (full-history path)
    assert llm.calls == 2


def test_large_corpus_uses_episode_summary_path():
    """Above history_summary_threshold, historical queries route to the
    episode summary path (which only sees digests + recent triples)."""
    llm = _ScriptedLLM(responses=[
        "historical",  # intent classifier
        "Per the first episode digest, initial value was v0",  # answer
    ])
    mem = MultiTierMemory(llm, episode_size=10, history_summary_threshold=10)
    _add_n_triples(mem, 25)  # 2 compressed episodes + 5 recent
    answer = mem.query("What was the initial status?")
    assert "v0" in answer


def test_large_corpus_historical_prompt_includes_episode_digest():
    """Confirm the episode summaries appear in the prompt context (not just
    the answer)."""
    captured: dict = {}
    class _CapturingLLM(_ScriptedLLM):
        def chat(self, role, messages, **kwargs):
            for m in messages:
                if m.get("role") == "user":
                    captured["last_user_msg"] = m.get("content", "")
            return super().chat(role, messages, **kwargs)
    llm = _CapturingLLM(responses=["historical", "v0"])
    mem = MultiTierMemory(llm, episode_size=10, history_summary_threshold=10)
    _add_n_triples(mem, 25)
    mem.query("What was the initial status?")
    assert "EPISODE SUMMARIES" in captured["last_user_msg"]
    assert "Episode ep_0000" in captured["last_user_msg"]


# -- Count via episode digests --


def test_count_aggregates_from_episode_digests():
    """Count queries should aggregate from compressed episode digests +
    uncompressed triples, with NO LLM arithmetic."""
    llm = _ScriptedLLM(responses=[
        json.dumps({"value": "v1"}),  # criteria extractor
    ])
    mem = MultiTierMemory(llm, episode_size=10, history_summary_threshold=100)
    _add_n_triples(mem, 25)
    # Of 25 triples with values rotating v0/v1/v2 by index%3:
    # v0: indices 0,3,6,9,12,15,18,21,24 = 9
    # v1: indices 1,4,7,10,13,16,19,22 = 8
    # v2: indices 2,5,8,11,14,17,20,23 = 8
    answer = mem.query("How many times did v1 occur?")
    assert answer == "8"
    # Only 1 LLM call (criteria), classifier was bypassed by keyword pre-routing
    assert llm.calls == 1


def test_count_falls_back_to_full_scan_with_no_episodes():
    """When no episodes have been compressed yet, count still works
    correctly — using the inherited path over uncompressed triples."""
    llm = _ScriptedLLM(responses=[
        json.dumps({"value": "v0"}),
    ])
    mem = MultiTierMemory(llm, episode_size=100, history_summary_threshold=200)
    _add_n_triples(mem, 9)
    # No compression yet (9 < 100)
    assert len(mem.episodes) == 0
    answer = mem.query("How many times was v0 observed?")
    # v0 at indices 0, 3, 6 = 3
    assert answer == "3"


# -- API compatibility: MultiTier is a drop-in for PrototypeMemory --


def test_multitier_is_a_prototype_memory_subclass():
    assert issubclass(MultiTierMemory, PrototypeMemory)


def test_multitier_inherits_hot_index():
    """The hot index (and its non-destructive guarantees) must still work."""
    llm = _ScriptedLLM()
    mem = MultiTierMemory(llm, episode_size=100)
    mem.add_triple(entity="X", attribute="y", value="a",
                   valid_from="2026-01-01T00:00:00")
    mem.add_triple(entity="X", attribute="y", value="b",
                   valid_from="2026-01-02T00:00:00")
    assert mem.hot_index[("x", "y")]["value"] == "b"
    # Append-only log preserves both
    assert len(mem.triples) == 2

"""Mechanical tests for PrototypeMemory.

Verifies the synthesis layer: append-only storage + non-destructive hot index +
intent routing + programmatic count + open-world-aware prompts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from benchmarks.e1_blackboard_stress.corpus import Doc
from benchmarks.e1_blackboard_stress.systems import PrototypeMemory


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _ScriptedLLM:
    def __init__(self, responses: list[str] | None = None):
        self._q = list(responses) if responses else []
        self.calls = 0
        self.last_user_msg: str = ""
        self.last_system_msg: str = ""

    def chat(self, role, messages, **kwargs):
        self.calls += 1
        for m in messages:
            if m.get("role") == "user":
                self.last_user_msg = m.get("content", "")
            elif m.get("role") == "system":
                self.last_system_msg = m.get("content", "")
        text = self._q.pop(0) if self._q else "(default)"
        return _Resp(choices=[_Choice(message=_Msg(content=text))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        return [[1.0] * 32 for _ in texts]


def _make_doc(id_: str, pub_date: str, text: str) -> Doc:
    return Doc(id=id_, pub_date=pub_date, text=text, entities=tuple())


# -- Storage layer --


def test_hot_index_tracks_latest_per_key():
    llm = _ScriptedLLM()
    p = PrototypeMemory(llm)
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")
    p.add_triple(entity="Alice", attribute="status", value="blocked",
                 valid_from="2026-01-02T00:00:00")
    p.add_triple(entity="Alice", attribute="status", value="review",
                 valid_from="2026-01-03T00:00:00")
    # Hot index keeps the latest
    key = ("alice", "status")
    assert p.hot_index[key]["value"] == "review"
    # But the log preserves all three
    assert len(p.triples) == 3


def test_hot_index_does_not_regress_on_older_writes():
    """Even if a write arrives with an older timestamp, hot index must NOT
    overwrite a newer entry (defends against out-of-order ingestion)."""
    llm = _ScriptedLLM()
    p = PrototypeMemory(llm)
    p.add_triple(entity="Alice", attribute="status", value="review",
                 valid_from="2026-01-03T00:00:00")
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")  # older
    # Log keeps both, in arrival order
    assert len(p.triples) == 2
    # Hot index still points at the newer
    assert p.hot_index[("alice", "status")]["value"] == "review"


def test_ingest_extracts_via_llm_and_indexes():
    """Verify the Doc-based ingest path works (extraction + log + index)."""
    llm = _ScriptedLLM(responses=[
        json.dumps({"triples": [
            {"entity": "Alice", "attribute": "status", "value": "active"},
        ]}),
    ])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc("d1", "2026-01-01T00:00:00",
                       "Alice's status is active."))
    assert len(p.triples) == 1
    assert p.hot_index[("alice", "status")]["value"] == "active"


# -- Phase C 3 — cross-session aggregation query path --


def test_aggregate_keyword_routes_to_aggregate_path():
    """Phase C 3 — questions with sum/average/total/altogether keywords
    route to the new aggregate path (skipping the LLM classifier on the
    fast-path)."""
    llm = _ScriptedLLM(responses=[
        # No classifier call (keyword fast-path fires).
        # Aggregate-path LLM answer with the required ANSWER: line.
        "- (user, purchase) = $1200 [Gucci handbag, luxury]\n"
        "- (user, purchase) = $800 [evening gown, luxury]\n"
        "$1200 + $800 = $2000\n"
        "ANSWER: $2,000",
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="user", attribute="purchase", value="$1200",
                 valid_from="2026-01-01T00:00:00", source_doc="d1")
    p.add_triple(entity="user", attribute="purchase", value="$800",
                 valid_from="2026-01-02T00:00:00", source_doc="d2")
    answer = p.query("What was the total amount spent on luxury items?")
    # 1 LLM call (aggregate); classifier skipped.
    assert llm.calls == 1
    # Final-line extraction picked up just the ANSWER value.
    assert answer == "$2,000"
    # The aggregate prompt must have been used.
    assert "list-then-aggregate" in llm.last_system_msg or "Enumerate" in llm.last_system_msg.lower() or "enumerate" in llm.last_system_msg.lower()


def test_aggregate_path_extracts_answer_line():
    """Whatever verbose CoT the LLM produces, the final returned answer
    is just the value after 'ANSWER:'."""
    llm = _ScriptedLLM(responses=[
        "Lots of reasoning here.\n"
        "Step 1: enumerate items\n"
        "Step 2: sum\n"
        "ANSWER: 42",
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="x", attribute="y", value="z",
                 valid_from="2026-01-01T00:00:00")
    answer = p.query("What is the total combined?")
    assert answer == "42"


def test_aggregate_path_falls_back_to_full_text_when_no_answer_line():
    """If the LLM doesn't follow the ANSWER: format, return the full
    response (the strict-format requirement is best-effort)."""
    llm = _ScriptedLLM(responses=[
        "Just $2000 across the items I found.",
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="x", attribute="y", value="z",
                 valid_from="2026-01-01T00:00:00")
    answer = p.query("Total altogether?")
    assert "$2000" in answer


def test_aggregate_path_uses_chunk_fallback_when_empty():
    """If no triples exist when the aggregate path runs, it falls
    through to chunk fallback (Phase B 2.3 Case A consistency)."""
    llm = _ScriptedLLM(responses=[
        # Chunk fallback answer (no triples → cosine ranks raw doc → answer)
        "$2,500",
    ])
    p = PrototypeMemory(llm)
    # No triples added. raw_docs has one relevant doc, no embeddings (test path).
    p.raw_docs.append(_make_doc(
        "d1", "2026-01-01T00:00:00",
        "Combined total spending: $2,500.",
    ))
    p.raw_doc_by_id["d1"] = p.raw_docs[0]
    answer = p.query("What was the total combined spending?")
    assert "$2,500" in answer


# -- Phase C 2 — source-doc text in historical / cross-entity context --


def test_historical_query_includes_source_doc_text():
    """Phase C 2 — when the historical path passes triples to the answer
    LLM, each triple's source-doc text should be inlined so the LLM sees
    qualifying context ('luxury', 'Gucci' etc.) that the bare triple
    decomposition stripped."""
    llm = _ScriptedLLM(responses=[
        # Ingest extraction
        json.dumps({"triples": [
            {"entity": "user", "attribute": "purchase", "value": "$1200"},
        ]}),
        # Intent classifier
        "historical",
        # Answer LLM
        "$1200 on a Gucci handbag",
    ])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc(
        "d1", "2026-01-01T00:00:00",
        "I bought a luxury Gucci handbag for $1200 yesterday.",
    ))
    p.query("What luxury items did I buy?")
    # The answer prompt should contain the source-doc text — that's the
    # whole point of Phase C 2.
    assert "Gucci handbag" in llm.last_user_msg
    assert "$1200" in llm.last_user_msg


def test_format_triples_with_source_dedupes_same_source():
    """If multiple triples share a source_doc, the source text is inlined
    once (the first time) — duplicating long quotes would explode the
    context size for free."""
    llm = _ScriptedLLM()
    p = PrototypeMemory(llm)
    doc = _make_doc("d1", "2026-01-01T00:00:00",
                    "Alice's status changed from active to blocked.")
    p.raw_doc_by_id["d1"] = doc
    p.raw_docs.append(doc)
    triples = [
        {"entity": "Alice", "attribute": "status", "value": "active",
         "valid_from": "2026-01-01T00:00:00", "source_doc": "d1"},
        {"entity": "Alice", "attribute": "status", "value": "blocked",
         "valid_from": "2026-01-01T00:00:01", "source_doc": "d1"},
    ]
    text = p._format_triples_with_source(triples)
    # Both triples appear
    assert "active" in text
    assert "blocked" in text
    # The source doc's text appears exactly once (deduped)
    assert text.count("Alice's status changed from active to blocked.") == 1


def test_format_triples_with_source_skips_when_doc_missing():
    """Triples whose source_doc isn't in raw_doc_by_id (e.g. add_triple
    test scenarios that don't go through ingest) just get the bare line."""
    llm = _ScriptedLLM()
    p = PrototypeMemory(llm)
    triples = [
        {"entity": "Alice", "attribute": "status", "value": "active",
         "valid_from": "2026-01-01T00:00:00", "source_doc": "d_missing"},
    ]
    text = p._format_triples_with_source(triples)
    assert "active" in text
    assert "source (" not in text  # no inlined source quote


# -- Phase C 1 — embedding-backed (cosine) chunk-fallback --


class _EmbedFromKeyword(_ScriptedLLM):
    """Deterministic embedder where doc embeddings encode a single
    keyword's hash bucket (32-dim sparse). Identical-keyword docs collide
    in vector space; different keywords = orthogonal axes. Lets us write
    cosine-retrieval tests without random noise."""

    def __init__(self, doc_to_keyword: dict[str, str], chat_responses=None):
        super().__init__(responses=chat_responses)
        self.doc_to_keyword = doc_to_keyword

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            v = [0.0] * 32
            # Find which keyword this text maps to (or use first word fallback)
            kw = None
            t_lower = t.lower()
            for keyword in self.doc_to_keyword.values():
                if keyword.lower() in t_lower:
                    kw = keyword.lower()
                    break
            if kw is None:
                # Question or unknown text — use first non-stop word
                for w in t_lower.split():
                    if len(w) > 3 and w not in {"what", "when", "where", "which"}:
                        kw = w
                        break
            if kw:
                v[hash(kw) % 32] = 1.0
            out.append(v)
        return out


def test_doc_embeddings_cached_on_ingest():
    """Phase C 1 — every successfully-extracted ingest also caches the
    doc's embedding for later cosine retrieval."""
    llm = _ScriptedLLM(responses=[
        json.dumps({"triples": [
            {"entity": "Alice", "attribute": "status", "value": "active"},
        ]}),
    ])
    p = PrototypeMemory(llm)
    doc = _make_doc("d1", "2026-01-01T00:00:00", "Alice's status is active.")
    p.ingest(doc)
    assert "d1" in p.doc_embeddings
    assert len(p.doc_embeddings["d1"]) == 32  # _ScriptedLLM emits 32-dim


def test_chunk_fallback_uses_cosine_when_embeddings_present():
    """Cosine retrieval should rank the GPS doc above an unrelated doc
    even when keyword overlap is low. This is the LongMemEval Q1 case."""
    llm = _EmbedFromKeyword(
        doc_to_keyword={"d1": "GPS", "d2": "weather", "d3": "service"},
        chat_responses=[
            # ingest extractions (return empty so we land in chunk fallback)
            json.dumps({"triples": []}),
            json.dumps({"triples": []}),
            json.dumps({"triples": []}),
            # Intent classifier
            "current",
            # Chunk-fallback answer LLM
            "GPS issue",
        ],
    )
    p = PrototypeMemory(llm)
    p.ingest(_make_doc("d1", "2026-01-01T00:00:00",
                       "Yeah I had a GPS problem after the dealer visit."))
    p.ingest(_make_doc("d2", "2026-01-02T00:00:00",
                       "The weather was nice today; we went to the coast."))
    p.ingest(_make_doc("d3", "2026-01-03T00:00:00",
                       "Got the car serviced last Tuesday; it was fast."))
    # Verify cosine ranking directly: d1 (GPS) must be first.
    top1 = p._cosine_top_k("What was the GPS issue?", k=1)
    assert top1 is not None
    assert len(top1) == 1
    assert top1[0].id == "d1"
    # Now run the full query → fallback path and verify the answer is GPS-aligned.
    answer = p.query("What was the GPS issue?")
    assert "GPS" in answer
    # And d1's text was in the LLM context with the chunk-fallback prompt.
    assert "raw conversation excerpts" in llm.last_system_msg
    assert "GPS problem" in llm.last_user_msg


def test_chunk_fallback_falls_back_to_jaccard_without_embeddings():
    """If no docs have cached embeddings (e.g. test scenarios where ingest
    is bypassed), chunk-fallback uses Jaccard. Same behavior as Phase B 2.3."""
    llm = _ScriptedLLM(responses=[
        # Classifier
        "current",
        # Chunk fallback answer
        "GPS",
    ])
    p = PrototypeMemory(llm)
    # Bypass ingest — directly populate raw_docs WITHOUT embedding cache.
    p.raw_docs.append(_make_doc(
        "d1", "2026-01-01T00:00:00",
        "I had a GPS issue after the dealer service.",
    ))
    # Add a triple so we don't take Case A early-return; force Case B.
    p.add_triple(entity="Alice", attribute="color", value="blue",
                 valid_from="2026-01-01T00:00:00")
    # No doc_embeddings populated — should fall back to Jaccard.
    assert p.doc_embeddings == {}
    answer = p.query("What was the GPS issue?")
    # Jaccard found "GPS" overlap with the question and surfaced d1.
    assert "GPS" in answer


def test_chunk_fallback_skipped_cleanly_when_neither_path_finds_anything():
    """If question has no keyword overlap AND no doc embeddings exist,
    return 'no record' — don't fabricate."""
    llm = _ScriptedLLM(responses=[
        "current",       # classifier
        "no record",     # structured-path answer (will trigger Case B)
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")
    p.raw_docs.append(_make_doc("d1", "2026-01-01T00:00:00", "irrelevant"))
    # No embeddings, and question is nothing-words.
    assert p.doc_embeddings == {}
    from benchmarks.e1_blackboard_stress.systems import _is_no_record_answer
    answer = p.query("Is it?")
    assert _is_no_record_answer(answer)
    # Only 2 LLM calls: classifier + structured answer. No fallback fired.
    assert llm.calls == 2


# -- Phase B 2.3 — chunk-fallback retrieval --


def test_chunk_fallback_fires_when_no_triples_extracted():
    """Case A: structured retrieval is empty (extraction yielded zero
    triples for this corpus) → fall back to keyword overlap over raw docs.
    Diagnosed on LongMemEval Q1 / Q22 where prototype answered 'no record'
    despite having relevant raw text in the haystack."""
    llm = _ScriptedLLM(responses=[
        # Ingest extraction returns empty triples
        json.dumps({"triples": []}),
        # Intent classifier
        "current",
        # Chunk fallback answer LLM
        "GPS",
    ])
    p = PrototypeMemory(llm)
    # Ingest a doc that DOES contain the GPS info, but extraction returns []
    p.ingest(_make_doc(
        "d1", "2026-01-01T00:00:00",
        "I had a frustrating issue with the GPS system after my car's first service.",
    ))
    # Structured path is empty (no triples). Question keyword-overlaps with the doc.
    answer = p.query("What was the issue I had with my car?")
    assert "GPS" in answer
    # System message of the LAST llm.chat call should be the chunk-fallback prompt
    assert "raw conversation excerpts" in llm.last_system_msg


def test_chunk_fallback_fires_when_structured_answer_says_no_record():
    """Case B: triples are present but none match → structured path
    answers 'no record' → retry via chunk fallback. Critical: the chunk
    fallback ONLY overrides if it produces a non-'no record' answer
    (legitimate abstention should be preserved)."""
    llm = _ScriptedLLM(responses=[
        # Ingest extraction (irrelevant triples)
        json.dumps({"triples": [
            {"entity": "Alice", "attribute": "color", "value": "blue"},
        ]}),
        # Intent classifier: current
        "current",
        # Structured-path LLM answer: no record (queried attribute not in table)
        "no record",
        # Chunk fallback answer LLM (raw doc had the answer)
        "GPS issue",
    ])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc(
        "d1", "2026-01-01T00:00:00",
        "I had a frustrating issue with the GPS system after my car's first service.",
    ))
    answer = p.query("What was the issue with my car?")
    assert "GPS" in answer


def test_chunk_fallback_preserves_legitimate_abstention():
    """If both structured path AND chunk fallback say 'no record', the
    structured 'no record' should be returned — don't override with a
    chunk answer that's also 'no record'."""
    llm = _ScriptedLLM(responses=[
        json.dumps({"triples": [
            {"entity": "Alice", "attribute": "status", "value": "active"},
        ]}),
        # Classifier
        "current",
        # Structured path answer
        "no record",
        # Chunk fallback ALSO says no record (raw doc has nothing relevant)
        "no record",
    ])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc(
        "d1", "2026-01-01T00:00:00",
        "Alice's status changed to active on Monday.",
    ))
    answer = p.query("What time did the meeting start?")
    # Both paths abstained; final answer should be the abstention.
    # _is_no_record_answer should match either "no record" form.
    from benchmarks.e1_blackboard_stress.systems import _is_no_record_answer
    assert _is_no_record_answer(answer)


def test_chunk_fallback_skipped_when_question_has_no_keywords():
    """If the question is all stopwords, don't bother with chunk-fallback
    retrieval — return 'no record' immediately."""
    llm = _ScriptedLLM(responses=[
        # Classifier (no extraction since we'll add a triple manually)
        "current",
        # Structured answer says no record
        "no record",
        # NO chunk-fallback LLM call expected — Jaccard would have nothing to match
    ])
    p = PrototypeMemory(llm)
    # Add a triple so structured path doesn't take Case A
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")
    # Append a raw doc so the fallback has something to scan
    p.raw_docs.append(_make_doc("d1", "2026-01-01T00:00:00", "irrelevant"))
    answer = p.query("Is it?")
    # Should not have called chunk-fallback's LLM (only 2 calls: classifier + structured answer)
    assert llm.calls == 2
    from benchmarks.e1_blackboard_stress.systems import _is_no_record_answer
    assert _is_no_record_answer(answer)


def test_no_record_answer_detector():
    """The _is_no_record_answer helper must distinguish abstention
    answers from legitimate answers that happen to contain the words."""
    from benchmarks.e1_blackboard_stress.systems import _is_no_record_answer
    # True cases — leading with no-record phrases
    assert _is_no_record_answer("(no record)")
    assert _is_no_record_answer("no record")
    assert _is_no_record_answer("No information given.")
    assert _is_no_record_answer("unknown")
    assert _is_no_record_answer("The memory does not contain the answer.")
    assert _is_no_record_answer("The provided memory doesn't contain information.")
    assert _is_no_record_answer("The records do not specify which book.")
    assert _is_no_record_answer("I don't know.")
    assert _is_no_record_answer("")
    # False cases — legitimate answers that mention but don't lead with these phrases
    assert not _is_no_record_answer("The Samsung Galaxy S22.")
    assert not _is_no_record_answer("Luna, Oliver, and Bailey.")
    assert not _is_no_record_answer("On May 3rd, the record was updated.")
    assert not _is_no_record_answer("Yes — there is no record of failure but X happened.")


# -- Phase B 2.2 — multi-value extraction prompt --


def test_ingest_uses_prototype_specific_extract_prompt():
    """PrototypeMemory ingest should use the prototype-specific prompt
    (with multi-value rule + few-shots), NOT the bare ZepLite prompt.
    Verifies the system message contains the multi-value RULE marker."""
    llm = _ScriptedLLM(responses=[json.dumps({"triples": []})])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc("d1", "2026-01-01T00:00:00", "any"))
    # System message must include the multi-value rule the new prompt added.
    assert "RULE" in llm.last_system_msg
    assert "multi-value" in llm.last_system_msg.lower()
    assert "ONE TRIPLE PER VALUE" in llm.last_system_msg


def test_ingest_handles_multi_value_extraction_output():
    """When the LLM correctly emits multiple triples for a list-style
    attribute (per the new prompt's rule), each value lands as its own
    triple in the log AND the hot index. This is the storage-side
    contract that makes the prompt change useful."""
    llm = _ScriptedLLM(responses=[json.dumps({"triples": [
        {"entity": "Melanie", "attribute": "pet", "value": "Luna"},
        {"entity": "Melanie", "attribute": "pet", "value": "Oliver"},
        {"entity": "Melanie", "attribute": "pet", "value": "Bailey"},
    ]})])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc("d1", "2026-01-01T00:00:00",
                       "Melanie has pets Luna, Oliver, and Bailey."))
    assert len(p.triples) == 3
    pet_values = sorted(
        t["value"] for t in p.triples if t["attribute"] == "pet"
    )
    assert pet_values == ["Bailey", "Luna", "Oliver"]
    # Hot index keeps the LATEST triple per (entity, attr) — since all
    # three share the same valid_from, the last one inserted wins (Bailey).
    # That's a separate concern; the LOG carries all three for historical
    # queries, which is what matters for multi-value answer synthesis.
    hot_pet = p.hot_index[("melanie", "pet")]["value"]
    assert hot_pet in ("Luna", "Oliver", "Bailey")


def test_historical_query_surfaces_all_multi_value_triples():
    """When _historical_query passes triples to the answer LLM, all
    multi-value entries for the same (entity, attribute) must appear in
    the context — that's what lets the answer LLM say 'Luna, Oliver,
    and Bailey' instead of just one of them."""
    llm = _ScriptedLLM(responses=[
        "historical",  # intent classifier
        "Luna, Oliver, and Bailey",  # historical-path answer
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="Melanie", attribute="pet", value="Luna",
                 valid_from="2026-01-01T00:00:00")
    p.add_triple(entity="Melanie", attribute="pet", value="Oliver",
                 valid_from="2026-01-01T00:00:01")
    p.add_triple(entity="Melanie", attribute="pet", value="Bailey",
                 valid_from="2026-01-01T00:00:02")
    answer = p.query("What were the names of Melanie's pets?")
    # All three pet values must appear in the LLM's answer-prompt context.
    for value in ("Luna", "Oliver", "Bailey"):
        assert value in llm.last_user_msg, (
            f"{value!r} missing from historical-path context: "
            f"{llm.last_user_msg[:200]!r}"
        )
    assert answer == "Luna, Oliver, and Bailey"


# -- Phase B 2.1 — robust extraction (repair-and-retry + regex salvage) --


def test_ingest_repair_recovers_from_malformed_json():
    """When the first extract output is malformed JSON, the repair-retry
    pass should produce a clean output and we should still ingest the
    triples. Diagnosed from LongMemEval where 600-1000+ extracts/run were
    being silently dropped due to truncated/garbled JSON."""
    llm = _ScriptedLLM(responses=[
        # Pass 1: malformed (unterminated string — common LongMemEval failure)
        '{"triples": [{"entity": "Alice", "attribute": "status", "value": "act',
        # Pass 2: repair returns clean JSON
        json.dumps({"triples": [
            {"entity": "Alice", "attribute": "status", "value": "active"},
        ]}),
    ])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc("d1", "2026-01-01T00:00:00",
                       "Alice's status is active."))
    assert len(p.triples) == 1
    assert p.hot_index[("alice", "status")]["value"] == "active"
    # 2 LLM calls = initial + repair
    assert llm.calls == 2


def test_ingest_regex_salvage_when_repair_also_fails():
    """If both the initial output AND the repair retry are malformed,
    fall back to regex-scraping the original output for triples. Better
    to recover what we can than drop everything."""
    llm = _ScriptedLLM(responses=[
        # Pass 1: malformed but contains a recognisable triple via regex
        ('Here are the facts: {"entity": "Alice", "attribute": "status", '
         '"value": "active"}, and also {"entity": "Bob", '
         '"attribute": "status", "value": "blocked"} — extra trailing junk'),
        # Pass 2: repair retry ALSO comes back malformed
        '{ broken again no closing brace',
    ])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc("d1", "2026-01-01T00:00:00",
                       "Alice and Bob have statuses."))
    # Regex salvage should have extracted both triples from pass-1's text.
    assert len(p.triples) == 2
    statuses = {t["entity"].lower(): t["value"] for t in p.triples}
    assert statuses == {"alice": "active", "bob": "blocked"}


def test_ingest_skips_doc_when_llm_call_fails():
    """If the LLM call itself raises (network/rate-limit), we should
    drop the doc gracefully — there's nothing to repair from."""
    class _ErrLLM(_ScriptedLLM):
        def chat(self, role, messages, **kwargs):
            self.calls += 1
            raise RuntimeError("connection error")
    llm = _ErrLLM()
    p = PrototypeMemory(llm)
    p.ingest(_make_doc("d1", "2026-01-01T00:00:00", "any content"))
    # No triples appended; no crash.
    assert len(p.triples) == 0


def test_ingest_handles_empty_triples_list():
    """LLM correctly emits {"triples": []} for non-factual content. This
    is a valid extraction — don't trigger the repair path."""
    llm = _ScriptedLLM(responses=[json.dumps({"triples": []})])
    p = PrototypeMemory(llm)
    p.ingest(_make_doc("d1", "2026-01-01T00:00:00", "Hi how are you."))
    assert len(p.triples) == 0
    # Only 1 LLM call — no repair retry triggered.
    assert llm.calls == 1


# -- Intent routing --


def test_intent_router_dispatches_current_to_hot_index_only():
    """A 'current' intent query must use the hot index path — verify by
    counting LLM calls (should be: 1 intent classifier + 1 answer = 2)."""
    llm = _ScriptedLLM(responses=[
        "current",   # intent classifier response
        "active",    # answer
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")
    p.add_triple(entity="Alice", attribute="status", value="blocked",
                 valid_from="2026-01-02T00:00:00")
    answer = p.query("What is Alice's current status?")
    assert "active" in answer or "blocked" in answer  # whatever fake returns
    assert llm.calls == 2  # 1 intent + 1 answer
    # The user msg for the answer should mention CURRENT STATE only
    assert "CURRENT STATE" in llm.last_user_msg


def test_intent_router_dispatches_historical_to_full_log():
    llm = _ScriptedLLM(responses=[
        "historical",  # intent classifier response
        "the first value was active",  # answer
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")
    p.add_triple(entity="Alice", attribute="status", value="blocked",
                 valid_from="2026-01-02T00:00:00")
    p.query("What was Alice's first observed status?")
    # Historical path must include the full triple list in context
    assert "TRIPLES" in llm.last_user_msg
    assert "active" in llm.last_user_msg and "blocked" in llm.last_user_msg


def test_keyword_pre_routing_bypasses_classifier_for_count():
    """Questions with unambiguous count signals must bypass the LLM
    classifier — defends against classifier-flake observed on E8 q3."""
    llm = _ScriptedLLM(responses=[
        # ZERO classifier responses needed because keyword pre-routing fires
        json.dumps({"value": "C"}),  # criteria extractor only
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="X", attribute="proj", value="A",
                 valid_from="2026-01-01T00:00:00")
    p.add_triple(entity="X", attribute="proj", value="C",
                 valid_from="2026-01-02T00:00:00")
    p.add_triple(entity="X", attribute="proj", value="C",
                 valid_from="2026-01-03T00:00:00")
    answer = p.query("How many times was X on project C?")
    assert answer == "2"
    # Only 1 LLM call (criteria extractor). Classifier was bypassed.
    assert llm.calls == 1


def test_keyword_pre_routing_bypasses_classifier_for_cross_entity():
    """Questions matching cross-entity keywords ('at the time / moment')
    skip the classifier and go straight to the cross-entity path. Note:
    bare ' when ' was removed 2026-04-26 — too broad, mis-routed
    LongMemEval temporal questions like 'When did X happen?'"""
    llm = _ScriptedLLM(responses=[
        # Single cross-entity LLM answer; no classifier call needed.
        "value at that timestamp",
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="X", attribute="status", value="green",
                 valid_from="2026-01-01T00:00:00")
    p.query("What was X at the time Y was red?")
    assert llm.calls == 1
    assert "TRIPLES" in llm.last_user_msg  # cross-entity path includes full log


def test_when_only_question_falls_through_to_classifier():
    """Regression: 'When did X happen?' must NOT pre-route to cross_entity
    just because it contains ' when '. Diagnosed on LongMemEval Q1 where
    such queries were misrouted, prototype answered 'no record'."""
    llm = _ScriptedLLM(responses=[
        "historical",  # classifier called -> routes correctly
        "answer",      # historical path answer
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="X", attribute="event", value="happened",
                 valid_from="2026-01-01T00:00:00")
    p.query("When did X happen?")
    # 2 calls = classifier + answer; cross_entity bypass did NOT fire.
    assert llm.calls == 2


def test_duration_question_routes_to_historical_not_count():
    """Regression: 'How many days did X take?' must route to historical
    (a duration question), not count (an event-frequency question).
    Diagnosed on LongMemEval temporal-reasoning Q5/Q6 where prototype
    output '3' / '0' (count results) instead of natural temporal phrasing.
    """
    llm = _ScriptedLLM(responses=[
        "30 days",  # historical path answer; classifier bypassed by duration kw
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="trip", attribute="duration", value="30 days",
                 valid_from="2026-01-01T00:00:00")
    p.query("How many days did the trip take?")
    # Just one LLM call (the answer) — duration keyword pre-routes,
    # AND historical path doesn't need the count's criteria-extractor call.
    assert llm.calls == 1
    # Sanity: historical prompt was used (TRIPLES included in context)
    assert "TRIPLES" in llm.last_user_msg


def test_bare_how_many_no_longer_force_routes_to_count():
    """Regression: 'How many people attended?' must NOT auto-route to
    count just because it contains 'how many'. Falls through to the LLM
    classifier (which can route based on full semantics)."""
    llm = _ScriptedLLM(responses=[
        "current",  # classifier sees the question, picks current
        "42",       # current path answer
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="event", attribute="attendees", value="42",
                 valid_from="2026-01-01T00:00:00")
    p.query("How many people attended the event?")
    # 2 calls = classifier + answer. count's criteria-extractor would
    # have made it 3+ calls if pre-routing had fired.
    assert llm.calls == 2


def test_classifier_post_check_overrides_count_when_no_count_keyword():
    """Phase B 2.4 — if the LLM classifier returns 'count' but the
    question contains no count keyword, override to 'historical'.
    Diagnosed on LongMemEval Q30 where prototype output '0' for a
    temporal question that the classifier mis-routed to count."""
    llm = _ScriptedLLM(responses=[
        # Classifier slip: returns "count" even though question is duration-y.
        # Question has no 'how many times' / 'how often' / 'frequency of' etc.
        "count",
        "the trip took 30 days",  # historical-path answer (after override)
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="trip", attribute="duration", value="30 days",
                 valid_from="2026-01-01T00:00:00")
    answer = p.query("What was the duration of the trip?")
    # 2 calls = classifier + answer. count's criteria-extractor would
    # have made it 3+ calls if the override didn't fire.
    assert llm.calls == 2
    # Sanity: historical-path prompt was used.
    assert "TRIPLES" in llm.last_user_msg
    assert "30 days" in answer


def test_classifier_post_check_keeps_count_when_keyword_present():
    """Sanity: if the question DOES contain a count keyword that the
    fast-path didn't catch (e.g. via LLM classifier returning 'count'
    after a synonym match), don't override — let count_query handle it."""
    # We hit the keyword fast-path first for "how many times", so this
    # test can't actually exercise the override-keep branch without a
    # contrived setup. Verify instead that the fast-path still routes
    # correctly with the post-check refactor.
    llm = _ScriptedLLM(responses=[
        json.dumps({"value": "C"}),  # count's criteria extractor
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="X", attribute="proj", value="C",
                 valid_from="2026-01-01T00:00:00")
    p.add_triple(entity="X", attribute="proj", value="C",
                 valid_from="2026-01-02T00:00:00")
    answer = p.query("How many times was X on project C?")
    assert answer == "2"


def test_intent_router_falls_back_to_current_on_classifier_error():
    """If the intent classifier fails, default to current (safe + cheap)."""
    class _BoomLLM(_ScriptedLLM):
        def chat(self, role, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("classifier transient failure")
            return _Resp(choices=[_Choice(message=_Msg(content="active"))])

    llm = _BoomLLM()
    p = PrototypeMemory(llm)
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")
    answer = p.query("What is Alice's current status?")
    assert "active" in answer


# -- Programmatic count handler (E8 q3 lesson) --


def test_count_query_counts_programmatically_no_llm_arithmetic():
    """LLM is NOT trusted to count; we filter triples directly. Test by
    populating known counts and asking 'how many'.

    Note: 'how many' is in _COUNT_KEYWORDS so the classifier is bypassed —
    only ONE LLM call is needed (the criteria extractor)."""
    llm = _ScriptedLLM(responses=[
        json.dumps({"value": "active"}),  # criteria extractor only
    ])
    p = PrototypeMemory(llm)
    # 3 'active' triples among 5 total
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")
    p.add_triple(entity="Alice", attribute="status", value="blocked",
                 valid_from="2026-01-02T00:00:00")
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-03T00:00:00")
    p.add_triple(entity="Bob", attribute="status", value="active",
                 valid_from="2026-01-04T00:00:00")
    p.add_triple(entity="Bob", attribute="status", value="review",
                 valid_from="2026-01-05T00:00:00")

    answer = p.query("How many times was anyone in 'active' status?")
    assert answer == "3"
    # Only 1 LLM call: criteria. Classifier bypassed by keyword pre-routing.
    assert llm.calls == 1


def test_count_query_uses_word_boundary_not_substring():
    """E8 regression: criterion 'C' must match word C in 'project C', NOT
    every value containing the letter 'c' (e.g. 'project A' contains 'c'
    inside 'project'). The original substring filter scored all 60 triples
    as matches; word-boundary regex correctly counts only true Cs."""
    llm = _ScriptedLLM(responses=[
        json.dumps({"value": "C"}),
    ])
    p = PrototypeMemory(llm)
    # Mix of values: 2 with word-C, 3 without
    p.add_triple(entity="X", attribute="proj", value="project A",
                 valid_from="2026-01-01T00:00:00")
    p.add_triple(entity="X", attribute="proj", value="project B",
                 valid_from="2026-01-02T00:00:00")
    p.add_triple(entity="X", attribute="proj", value="project C",
                 valid_from="2026-01-03T00:00:00")
    p.add_triple(entity="X", attribute="proj", value="project A",
                 valid_from="2026-01-04T00:00:00")
    p.add_triple(entity="X", attribute="proj", value="project C",
                 valid_from="2026-01-05T00:00:00")
    answer = p.query("How many times did X have project C?")
    # Word-boundary "C" matches only "project C" (×2), NOT "project A/B"
    # which contain 'c' inside "project".
    assert answer == "2"


def test_count_query_falls_back_when_criteria_empty():
    """If criteria extraction returns empty {}, fall back to historical
    rather than counting all triples (which would be misleading).

    With keyword pre-routing, total calls = 1 (criteria) + 1 (historical
    answer after fallback) = 2. Classifier is bypassed."""
    llm = _ScriptedLLM(responses=[
        json.dumps({}),   # empty criteria
        "I count 0 matching events given no criteria.",  # historical-path answer
    ])
    p = PrototypeMemory(llm)
    p.add_triple(entity="Alice", attribute="status", value="active",
                 valid_from="2026-01-01T00:00:00")
    answer = p.query("How many?")
    # Should hit the historical fallback, not the count handler
    assert llm.calls == 2


# -- Open-world prompt (E7 q6 lesson) --


def test_current_query_prompt_warns_against_fabrication():
    """The current-query system prompt must instruct the LLM to say 'unknown'
    rather than fabricate when an entity/attribute isn't in the table."""
    from benchmarks.e1_blackboard_stress.systems import (
        _PROTOTYPE_CURRENT_QUERY_SYSTEM,
    )
    s = _PROTOTYPE_CURRENT_QUERY_SYSTEM.lower()
    assert "not in the table" in s or "do not fabricate" in s or "do not fabric" in s
    assert "unknown" in s or "no record" in s


def test_historical_query_prompt_distinguishes_no_record():
    from benchmarks.e1_blackboard_stress.systems import (
        _PROTOTYPE_HISTORICAL_QUERY_SYSTEM,
    )
    s = _PROTOTYPE_HISTORICAL_QUERY_SYSTEM.lower()
    assert "no record" in s

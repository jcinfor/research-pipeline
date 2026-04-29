"""Three memory systems under test in the E4 benchmark.

All three use the same LLM adapter (LLMClient) for fairness — the differences
are structural, not model-driven.

    KarpathyLite — per-entity LLM-compiled summary (write-time LLM compile)
    ZepLite       — entity-attribute-value triples with valid_from (write-time
                    LLM extraction + query-time temporal filter)
    Hybrid        — raw chunks with t_ref (cheap write, query-time temporal
                    filter + cosine retrieval). Mirrors our wiki.py logic.

Each system implements:
    ingest(doc: Doc) -> None
    query(question: str, as_of: str | None) -> str
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from research_pipeline.adapter import LLMClient
from research_pipeline.dedup import cosine

from .corpus import Doc


# ---------------------------------------------------------------------------
# KarpathyLite — write-time LLM compile, no temporal awareness
# ---------------------------------------------------------------------------


_KARPATHY_COMPILE_SYSTEM = """You are maintaining a single current summary for
one entity. Given the prior summary and a new document, produce an updated
summary that incorporates the new information. If the new doc supersedes
earlier claims (e.g., a new CEO replaces the old one), the summary should
reflect the latest state — do NOT keep both facts.

Respond with the updated summary as plain text, 2-4 sentences. No preamble.
"""

_KARPATHY_QUERY_SYSTEM = """Answer the question from the entity summaries
provided. Be concise. If the summaries don't contain the answer, say so.
Do not speculate beyond the summaries.
"""


class KarpathyLite:
    def __init__(self, llm: LLMClient, role: str = "agent_bulk"):
        self.llm = llm
        self.role = role
        self.summaries: dict[str, str] = {}

    def ingest(self, doc: Doc) -> None:
        for entity in doc.entities:
            prior = self.summaries.get(entity, "(no prior summary)")
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _KARPATHY_COMPILE_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"ENTITY: {entity}\n"
                            f"PRIOR SUMMARY: {prior}\n"
                            f"NEW DOCUMENT (published {doc.pub_date}):\n{doc.text}\n\n"
                            f"Produce the updated summary."
                        ),
                    },
                ],
                max_tokens=400,
                temperature=0.1,
            )
            self.summaries[entity] = (resp.choices[0].message.content or "").strip()

    def query(self, question: str, as_of: str | None = None) -> str:
        # as_of is IGNORED by pure Karpathy — no temporal reasoning
        if not self.summaries:
            return "(no summaries)"
        ctx = "\n\n".join(
            f"### {k}\n{v}" for k, v in self.summaries.items()
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _KARPATHY_QUERY_SYSTEM},
                {
                    "role": "user",
                    "content": f"ENTITY SUMMARIES:\n{ctx}\n\nQUESTION: {question}\n\nAnswer:",
                },
            ],
            max_tokens=200,
            temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# ZepLite — write-time LLM extraction of triples with valid_from
# ---------------------------------------------------------------------------


_ZEP_EXTRACT_SYSTEM = """You extract entity-attribute-value triples from
research documents. For each fact the document states about an entity,
output a triple {"entity": ..., "attribute": ..., "value": ...}.

Rules:
- Focus on factual claims about named entities (people, projects, experiments)
- The "attribute" should be a short noun phrase (e.g., "CEO", "status", "lead")
- The "value" should be the specific answer (e.g., "Alice Chen", "failed")
- Return ONLY a JSON object: {"triples": [{"entity": "...", "attribute": "...", "value": "..."}, ...]}
"""

_ZEP_QUERY_SYSTEM = """Answer the question using the time-stamped triples below.
Each triple is (entity, attribute, value) with a 'valid_from' date indicating
when that value started being true. Pick the most recent triple matching the
question. Be concise. If no triple matches, say so.
"""


class ZepLite:
    def __init__(self, llm: LLMClient, role: str = "agent_bulk"):
        self.llm = llm
        self.role = role
        self.triples: list[dict[str, Any]] = []

    def ingest(self, doc: Doc) -> None:
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _ZEP_EXTRACT_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"DOCUMENT (published {doc.pub_date}):\n{doc.text}\n\n"
                            "Extract triples."
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=512,
                temperature=0,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            print(f"[zep_lite] extract failed on {doc.id}: {e}")
            return

        for t in data.get("triples", []):
            if not isinstance(t, dict):
                continue
            entity = str(t.get("entity", "")).strip()
            attribute = str(t.get("attribute", "")).strip()
            value = str(t.get("value", "")).strip()
            if not (entity and attribute and value):
                continue
            self.triples.append({
                "entity": entity,
                "attribute": attribute,
                "value": value,
                "valid_from": doc.pub_date,
                "source_doc": doc.id,
            })

    def query(self, question: str, as_of: str | None = None) -> str:
        cutoff = as_of or "9999-12-31"
        relevant = [t for t in self.triples if t["valid_from"] <= cutoff]
        # Keep only the latest triple per (entity, attribute)
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for t in relevant:
            key = (t["entity"].lower(), t["attribute"].lower())
            if key not in latest or t["valid_from"] > latest[key]["valid_from"]:
                latest[key] = t
        if not latest:
            return "(no matching triples)"
        ctx_lines = [
            f"- ({t['entity']}, {t['attribute']}) = {t['value']}  [valid_from {t['valid_from']}]"
            for t in sorted(
                latest.values(), key=lambda x: x["valid_from"], reverse=True,
            )
        ]
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _ZEP_QUERY_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"TRIPLES (as of {cutoff}):\n"
                        + "\n".join(ctx_lines)
                        + f"\n\nQUESTION: {question}\n\nAnswer:"
                    ),
                },
            ],
            max_tokens=200,
            temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Hybrid — raw chunks + t_ref, cosine retrieval with temporal filter
# ---------------------------------------------------------------------------


_HYBRID_QUERY_SYSTEM = """Answer the question using the retrieved passages.
Each passage is tagged with its publication date. Prefer the most recent
passage that directly answers the question. Be concise.
"""


@dataclass
class _Chunk:
    doc_id: str
    text: str
    t_ref: str
    embedding: list[float] = field(default_factory=list)


class Hybrid:
    def __init__(self, llm: LLMClient, role: str = "agent_bulk"):
        self.llm = llm
        self.role = role
        self.chunks: list[_Chunk] = []

    def ingest(self, doc: Doc) -> None:
        # No LLM call at write — just embed the doc
        try:
            emb = self.llm.embed("embedding", doc.text)[0]
        except Exception as e:
            print(f"[hybrid] embed failed on {doc.id}: {e}")
            emb = []
        self.chunks.append(_Chunk(
            doc_id=doc.id,
            text=doc.text,
            t_ref=doc.pub_date,
            embedding=list(emb),
        ))

    def query(self, question: str, as_of: str | None = None, top_k: int = 5) -> str:
        cutoff = as_of or "9999-12-31"
        candidates = [c for c in self.chunks if c.t_ref <= cutoff and c.embedding]
        if not candidates:
            return "(no chunks available)"
        try:
            q_emb = self.llm.embed("embedding", question)[0]
        except Exception as e:
            print(f"[hybrid] query embed failed: {e}")
            return "(embed failed)"
        ranked = sorted(
            candidates,
            key=lambda c: -cosine(q_emb, c.embedding),
        )[:top_k]
        ctx = "\n\n".join(
            f"(doc {c.doc_id}, published {c.t_ref}):\n{c.text}"
            for c in ranked
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _HYBRID_QUERY_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"PASSAGES (most relevant first):\n{ctx}\n\n"
                        f"QUESTION: {question}\n"
                        f"Answer as of {cutoff}:"
                    ),
                },
            ],
            max_tokens=200,
            temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()

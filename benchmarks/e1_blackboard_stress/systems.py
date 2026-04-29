"""Five memory systems under test in the E1 Blackboard Stress Test.

    HybridFlat       — raw chunks with t_ref, cosine top-k. No write-time LLM.
                       (Our current architecture. Predicted weakness: top-k
                       may miss the latest chunk when many near-identical
                       chunks compete.)
    HybridRecency    — hybrid variant: candidates sorted by t_ref DESC first,
                       then cosine reranked within the top-M most recent.
                       Tests whether adding a recency prior fixes hybrid's
                       predicted weakness without adding write-time LLM cost.
    ZepLite          — entity-attribute-value triples with valid_from.
                       Write-time LLM extraction. Deterministic latest lookup.
    Mem0Lite         — extract + consolidate into an entity-attribute map.
                       Write-time LLM extraction; each new value OVERWRITES
                       the prior for (entity, attribute).
    SupermemoryLite  — extract + consolidate + chunk fallback ("hybrid
                       search: RAG + memory in one query"). Stores BOTH a
                       consolidated profile AND embedded chunks; query
                       prefers profile hits and falls back to chunk search
                       when the profile misses. If `default_ttl_sec` is set,
                       profile facts whose updated_at is older than TTL (as
                       measured against the latest observed doc timestamp)
                       are EXPIRED out of the profile at query time; the
                       chunk fallback may still surface the expired fact.
    MFlowLite        — M-Flow-inspired 4-level cone (Episode > Facet >
                       FacetPoint > Entity). Each doc becomes one Episode;
                       each extracted fact becomes a FacetPoint linked to
                       an Entity node and an attribute-Facet. Query
                       retrieval navigates the hierarchy: locate matching
                       entities, enumerate their attribute-facets, return
                       the latest FacetPoint. For single-entity queries
                       this is equivalent to Mem0/Zep; the cone's value
                       prop (cross-Entity graph paths) is NOT tested by
                       the E1 workload — see E6.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from research_pipeline.adapter import LLMClient
from research_pipeline.dedup import cosine

from .corpus import Doc


# ---------------------------------------------------------------------------
# Hybrid — flat (cosine-only) and recency-reranked variants
# ---------------------------------------------------------------------------


_HYBRID_QUERY_SYSTEM = """Answer the question using the retrieved passages.
Each passage is tagged with its publication timestamp. Prefer the MOST RECENT
passage that directly answers the question — later updates override earlier
ones. Be concise. Respond with just the value, no preamble.
"""


@dataclass
class _Chunk:
    doc_id: str
    text: str
    t_ref: str
    embedding: list[float] = field(default_factory=list)


class HybridFlat:
    def __init__(self, llm: LLMClient, role: str = "agent_bulk", top_k: int = 5):
        self.llm = llm
        self.role = role
        self.top_k = top_k
        self.chunks: list[_Chunk] = []

    def ingest(self, doc: Doc) -> None:
        try:
            emb = self.llm.embed("embedding", doc.text)[0]
        except Exception as e:
            print(f"[hybrid_flat] embed failed on {doc.id}: {e}")
            emb = []
        self.chunks.append(_Chunk(
            doc_id=doc.id, text=doc.text, t_ref=doc.pub_date, embedding=list(emb),
        ))

    def query(self, question: str, as_of: str | None = None) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        cands = [c for c in self.chunks if c.t_ref <= cutoff and c.embedding]
        if not cands:
            return "(no chunks)"
        try:
            q_emb = self.llm.embed("embedding", question)[0]
        except Exception as e:
            return f"(embed failed: {e})"
        ranked = sorted(cands, key=lambda c: -cosine(q_emb, c.embedding))[:self.top_k]
        ctx = "\n\n".join(
            f"(doc {c.doc_id}, published {c.t_ref}):\n{c.text}" for c in ranked
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _HYBRID_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"PASSAGES (top-{self.top_k} by cosine):\n{ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=100, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


class HybridRecency:
    """Hybrid variant: take most recent M chunks, then cosine-rerank within."""
    def __init__(
        self, llm: LLMClient, role: str = "agent_bulk",
        recency_window: int = 20, top_k: int = 5,
    ):
        self.llm = llm
        self.role = role
        self.recency_window = recency_window
        self.top_k = top_k
        self.chunks: list[_Chunk] = []

    def ingest(self, doc: Doc) -> None:
        try:
            emb = self.llm.embed("embedding", doc.text)[0]
        except Exception as e:
            print(f"[hybrid_recency] embed failed on {doc.id}: {e}")
            emb = []
        self.chunks.append(_Chunk(
            doc_id=doc.id, text=doc.text, t_ref=doc.pub_date, embedding=list(emb),
        ))

    def query(self, question: str, as_of: str | None = None) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        cands = [c for c in self.chunks if c.t_ref <= cutoff and c.embedding]
        if not cands:
            return "(no chunks)"
        # Recency window first: most recent M
        recent = sorted(cands, key=lambda c: c.t_ref, reverse=True)[:self.recency_window]
        try:
            q_emb = self.llm.embed("embedding", question)[0]
        except Exception as e:
            return f"(embed failed: {e})"
        ranked = sorted(recent, key=lambda c: -cosine(q_emb, c.embedding))[:self.top_k]
        ctx = "\n\n".join(
            f"(doc {c.doc_id}, published {c.t_ref}):\n{c.text}" for c in ranked
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _HYBRID_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"PASSAGES (recency-filtered, top-{self.top_k} by cosine "
                    f"within last {self.recency_window}):\n{ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=100, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# ZepLite — triples with valid_from
# ---------------------------------------------------------------------------


_ZEP_EXTRACT_SYSTEM = """Extract entity-attribute-value triples from the
document. For each factual claim, output {"entity": ..., "attribute": ..., "value": ...}.
Return ONLY JSON: {"triples": [...]}.
"""


# Phase B 2.2 — prototype-specific extraction prompt with multi-value rule
# and few-shot anchors. Targets the "single triple with multi-value
# concatenated" failure mode diagnosed on LoCoMo (e.g. "Luna, Oliver, and
# Bailey" collapsing to one triple, or to {"value": "unknown"}). Few-shot
# examples are kept minimal to bound prompt-token cost (~150 tokens).
#
# Critical: this is a SEPARATE constant from `_ZEP_EXTRACT_SYSTEM` so
# ZepLite's benchmark baseline stays unchanged — its E1-E11 results need
# to remain comparable.
_PROTOTYPE_EXTRACT_SYSTEM = """Extract entity-attribute-value triples. For each factual claim, output {"entity": ..., "attribute": ..., "value": ...}.

RULE — multi-value attributes (pets, art mediums, hobbies, books, events, instruments, foods, places visited, favorite movies, etc.): emit ONE TRIPLE PER VALUE. Use singular attribute names ("pet" not "pets"). Include descriptive qualifiers in the value (e.g. "white Adidas sneakers", not just "Adidas sneakers", when source said "white").

Examples:

Input: "Melanie has pets Luna, Oliver, and Bailey."
Output: {"triples":[{"entity":"Melanie","attribute":"pet","value":"Luna"},{"entity":"Melanie","attribute":"pet","value":"Oliver"},{"entity":"Melanie","attribute":"pet","value":"Bailey"}]}

Input: "Alice bought white Adidas sneakers yesterday."
Output: {"triples":[{"entity":"Alice","attribute":"purchase","value":"white Adidas sneakers"}]}

Input: "Hi, how are you?"
Output: {"triples":[]}

Input: "Bob's status changed from active to blocked."
Output: {"triples":[{"entity":"Bob","attribute":"status","value":"blocked"}]}

Return ONLY valid JSON: {"triples": [...]}.
"""


# Regex to salvage triples from malformed JSON output. Used by
# PrototypeMemory's robust-extract path (Phase B 2.1) when both the
# initial parse AND the repair-retry fail. Lower-quality than a clean
# parse but recovers something on partial-output drops.
_TRIPLE_SALVAGE_RE = re.compile(
    r'"entity"\s*:\s*"([^"]+)"\s*,\s*'
    r'"attribute"\s*:\s*"([^"]+)"\s*,\s*'
    r'"value"\s*:\s*"([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)


def _salvage_triples_from_text(text: str) -> list[dict[str, str]]:
    """Regex-scrape (entity, attribute, value) triples from a string that
    failed strict JSON parsing. Tolerates trailing junk, missing braces,
    truncation mid-output. Order of fields must be entity → attribute → value.
    """
    if not text:
        return []
    out: list[dict[str, str]] = []
    for m in _TRIPLE_SALVAGE_RE.finditer(text):
        e = m.group(1).strip()
        a = m.group(2).strip()
        v = m.group(3).strip()
        if e and a and v:
            out.append({"entity": e, "attribute": a, "value": v})
    return out


def _try_parse_triples(text: str) -> list[dict[str, Any]] | None:
    """Attempt strict JSON parse and return the `triples` list.
    Returns None if the JSON didn't parse — caller can decide how to
    fall back. Returns [] if JSON parsed but had no `triples` key
    (the LLM correctly emitted an empty extraction)."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    out = data.get("triples")
    if not isinstance(out, list):
        return []
    return out

_ZEP_QUERY_SYSTEM = """Answer using the time-stamped triples below. Pick the
most recent matching triple. Respond with just the value, no preamble.
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
                    {"role": "user", "content": (
                        f"DOCUMENT (published {doc.pub_date}):\n{doc.text}\n\n"
                        "Extract triples."
                    )},
                ],
                response_format={"type": "json_object"},
                max_tokens=256, temperature=0,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            print(f"[zep_lite] extract failed on {doc.id}: {e}")
            return
        for t in data.get("triples", []):
            if not isinstance(t, dict):
                continue
            e = str(t.get("entity", "")).strip()
            a = str(t.get("attribute", "")).strip()
            v = str(t.get("value", "")).strip()
            if not (e and a and v):
                continue
            self.triples.append({
                "entity": e, "attribute": a, "value": v,
                "valid_from": doc.pub_date, "source_doc": doc.id,
            })

    def query(self, question: str, as_of: str | None = None) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        rel = [t for t in self.triples if t["valid_from"] <= cutoff]
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for t in rel:
            key = (t["entity"].lower(), t["attribute"].lower())
            if key not in latest or t["valid_from"] > latest[key]["valid_from"]:
                latest[key] = t
        if not latest:
            return "(no triples)"
        ctx = "\n".join(
            f"- ({t['entity']}, {t['attribute']}) = {t['value']}  [valid_from {t['valid_from']}]"
            for t in sorted(latest.values(), key=lambda x: x["valid_from"], reverse=True)
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _ZEP_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"TRIPLES:\n{ctx}\n\nQUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=100, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Mem0Lite — extract + consolidate (overwrite on new value)
# ---------------------------------------------------------------------------


_MEM0_EXTRACT_SYSTEM = """Extract entity-attribute-value facts from the
document. For each factual claim about a named entity, output
{"entity": ..., "attribute": ..., "value": ...}. Return ONLY JSON:
{"facts": [...]}. If the doc states a new value for an existing attribute,
still emit the fact — consolidation happens at the memory layer.
"""

_MEM0_QUERY_SYSTEM = """Answer from the consolidated memory below. Each
(entity, attribute) has exactly one current value. Respond with just the
value, no preamble.
"""


class Mem0Lite:
    """Mem0-inspired: extract facts, consolidate by overwriting prior value."""
    def __init__(self, llm: LLMClient, role: str = "agent_bulk"):
        self.llm = llm
        self.role = role
        # memory[entity_lower][attribute_lower] = {"value": ..., "updated_at": ..., "entity": orig, "attribute": orig}
        self.memory: dict[str, dict[str, dict[str, Any]]] = {}

    def ingest(self, doc: Doc) -> None:
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _MEM0_EXTRACT_SYSTEM},
                    {"role": "user", "content": (
                        f"DOCUMENT (observed {doc.pub_date}):\n{doc.text}\n\n"
                        "Extract facts."
                    )},
                ],
                response_format={"type": "json_object"},
                max_tokens=256, temperature=0,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            print(f"[mem0_lite] extract failed on {doc.id}: {e}")
            return
        for f in data.get("facts", []):
            if not isinstance(f, dict):
                continue
            e = str(f.get("entity", "")).strip()
            a = str(f.get("attribute", "")).strip()
            v = str(f.get("value", "")).strip()
            if not (e and a and v):
                continue
            ek, ak = e.lower(), a.lower()
            prior = self.memory.setdefault(ek, {}).get(ak)
            # Consolidate: only overwrite if this update is NEWER.
            # (Mem0's published design uses timestamp-aware consolidation.)
            if prior is None or doc.pub_date >= prior["updated_at"]:
                self.memory[ek][ak] = {
                    "value": v, "entity": e, "attribute": a,
                    "updated_at": doc.pub_date, "source_doc": doc.id,
                }

    def query(self, question: str, as_of: str | None = None) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        rows: list[dict[str, Any]] = []
        for ek, attrs in self.memory.items():
            for ak, fact in attrs.items():
                if fact["updated_at"] <= cutoff:
                    rows.append(fact)
        if not rows:
            return "(no memory)"
        ctx = "\n".join(
            f"- ({r['entity']}, {r['attribute']}) = {r['value']}  [updated {r['updated_at']}]"
            for r in sorted(rows, key=lambda x: x["updated_at"], reverse=True)
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _MEM0_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"MEMORY:\n{ctx}\n\nQUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=600, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# SupermemoryLite — consolidated profile + chunk fallback ("hybrid search")
# ---------------------------------------------------------------------------


_SUPERMEM_EXTRACT_SYSTEM = """Extract entity-attribute-value facts from the
document. For each factual claim about a named entity, output
{"entity": ..., "attribute": ..., "value": ...}. Return ONLY JSON:
{"facts": [...]}.
"""

_SUPERMEM_QUERY_SYSTEM = """Answer using the candidate evidence below. PROFILE
holds consolidated structured facts with their last-update timestamps.
PASSAGES holds raw excerpts with publication timestamps. Use the MOST RECENT
evidence across BOTH sources: if a PASSAGE's publication timestamp is newer
than the matching PROFILE entry's update timestamp, prefer the PASSAGE's
value. If PROFILE is empty for the queried attribute, use PASSAGES.
Respond with just the value, no preamble.
"""


class SupermemoryLite:
    """Supermemory-inspired: consolidated profile + raw chunks, queried together.

    Write cost = 1 LLM extract + 1 embed per doc (strict superset of
    Mem0Lite's write cost, matching the real supermemory architecture's
    'RAG + memory in one query').

    TTL metadata is recorded per fact but not actively expired in E1 —
    forgetting is tested by a future E1-TTL variant.
    """

    def __init__(
        self, llm: LLMClient, role: str = "agent_bulk",
        chunk_top_k: int = 5, default_ttl_sec: int | None = None,
    ):
        self.llm = llm
        self.role = role
        self.chunk_top_k = chunk_top_k
        self.default_ttl_sec = default_ttl_sec
        self.memory: dict[str, dict[str, dict[str, Any]]] = {}
        self.chunks: list[_Chunk] = []

    def ingest(self, doc: Doc) -> None:
        try:
            emb = self.llm.embed("embedding", doc.text)[0]
        except Exception as e:
            print(f"[supermemory_lite] embed failed on {doc.id}: {e}")
            emb = []
        self.chunks.append(_Chunk(
            doc_id=doc.id, text=doc.text, t_ref=doc.pub_date, embedding=list(emb),
        ))
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _SUPERMEM_EXTRACT_SYSTEM},
                    {"role": "user", "content": (
                        f"DOCUMENT (observed {doc.pub_date}):\n{doc.text}\n\n"
                        "Extract facts."
                    )},
                ],
                response_format={"type": "json_object"},
                max_tokens=256, temperature=0,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            print(f"[supermemory_lite] extract failed on {doc.id}: {e}")
            return
        for f in data.get("facts", []):
            if not isinstance(f, dict):
                continue
            e = str(f.get("entity", "")).strip()
            a = str(f.get("attribute", "")).strip()
            v = str(f.get("value", "")).strip()
            if not (e and a and v):
                continue
            ek, ak = e.lower(), a.lower()
            prior = self.memory.setdefault(ek, {}).get(ak)
            if prior is None or doc.pub_date >= prior["updated_at"]:
                self.memory[ek][ak] = {
                    "value": v, "entity": e, "attribute": a,
                    "updated_at": doc.pub_date, "source_doc": doc.id,
                    "ttl_sec": self.default_ttl_sec,
                }

    def query(self, question: str, as_of: str | None = None) -> str:
        from datetime import datetime as _dt
        cutoff = as_of or "9999-12-31T23:59:59"
        # Determine "now" for TTL from the latest observed doc (either profile
        # or chunk). This is deterministic — tests stay reproducible.
        now_iso = cutoff
        if self.default_ttl_sec is not None:
            now_iso = max(
                (f["updated_at"] for attrs in self.memory.values() for f in attrs.values()),
                default=cutoff,
            )
            chunk_max = max((c.t_ref for c in self.chunks), default="")
            if chunk_max > now_iso:
                now_iso = chunk_max
            if as_of and as_of < now_iso:
                now_iso = as_of
        profile_rows: list[dict[str, Any]] = []
        for ek, attrs in self.memory.items():
            for ak, fact in attrs.items():
                if fact["updated_at"] > cutoff:
                    continue
                ttl = fact.get("ttl_sec")
                if ttl is not None:
                    age = (_dt.fromisoformat(now_iso) - _dt.fromisoformat(fact["updated_at"])).total_seconds()
                    if age > ttl:
                        continue
                profile_rows.append(fact)
        profile_ctx = "\n".join(
            f"- ({r['entity']}, {r['attribute']}) = {r['value']}  [updated {r['updated_at']}]"
            for r in sorted(profile_rows, key=lambda x: x["updated_at"], reverse=True)
        ) or "(empty)"

        chunk_cands = [c for c in self.chunks if c.t_ref <= cutoff and c.embedding]
        chunk_ctx = "(none)"
        if chunk_cands:
            try:
                q_emb = self.llm.embed("embedding", question)[0]
                ranked = sorted(
                    chunk_cands, key=lambda c: -cosine(q_emb, c.embedding),
                )[:self.chunk_top_k]
                chunk_ctx = "\n\n".join(
                    f"(doc {c.doc_id}, published {c.t_ref}):\n{c.text}"
                    for c in ranked
                )
            except Exception as e:
                chunk_ctx = f"(embed failed: {e})"

        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _SUPERMEM_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"PROFILE:\n{profile_ctx}\n\n"
                    f"PASSAGES (top-{self.chunk_top_k} by cosine):\n{chunk_ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=100, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# MFlowLite — 4-level cone (Entity > Facet > FacetPoint, with Episode tags)
# ---------------------------------------------------------------------------


_MFLOW_EXTRACT_SYSTEM = """Extract entity-attribute-value facts from the
document. For each factual claim about a named entity, output
{"entity": ..., "attribute": ..., "value": ...}. Return ONLY JSON:
{"facts": [...]}.
"""

_MFLOW_QUERY_SYSTEM = """Answer using the cone below. Each Entity has
attribute-Facets; each Facet shows its LATEST FacetPoint value with the
total count of historical FacetPoints for that attribute. Respond with
just the value, no preamble.
"""


class MFlowLite:
    """M-Flow-inspired cone: Entity > Facet (attribute) > FacetPoint (value+timestamp).

    Each ingested doc becomes one Episode; each extracted fact becomes one
    FacetPoint linked to an Entity node and an attribute-Facet. Retrieval
    navigates the cone: locate matching entities, enumerate attribute-Facets,
    return the latest FacetPoint.

    NOTE: On E1-style single-entity queries this reduces to a more verbose
    ZepLite. The cone's cross-Entity path scoring is the differentiator —
    see E6 (cross-entity queries) for a workload that actually stresses it.
    """

    def __init__(self, llm: LLMClient, role: str = "agent_bulk"):
        self.llm = llm
        self.role = role
        # cone[entity_key][facet_key] = [facetpoint dicts]
        self.cone: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self.episodes: list[dict[str, Any]] = []

    def ingest(self, doc: Doc) -> None:
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _MFLOW_EXTRACT_SYSTEM},
                    {"role": "user", "content": (
                        f"DOCUMENT (observed {doc.pub_date}):\n{doc.text}\n\n"
                        "Extract facts."
                    )},
                ],
                response_format={"type": "json_object"},
                max_tokens=256, temperature=0,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            print(f"[m_flow_lite] extract failed on {doc.id}: {e}")
            return
        episode_id = f"ep_{doc.id}"
        fps: list[dict[str, Any]] = []
        for f in data.get("facts", []):
            if not isinstance(f, dict):
                continue
            e = str(f.get("entity", "")).strip()
            a = str(f.get("attribute", "")).strip()
            v = str(f.get("value", "")).strip()
            if not (e and a and v):
                continue
            ek, ak = e.lower(), a.lower()
            fp = {
                "value": v, "entity": e, "attribute": a,
                "pub_date": doc.pub_date, "doc_id": doc.id,
                "episode_id": episode_id,
            }
            self.cone.setdefault(ek, {}).setdefault(ak, []).append(fp)
            fps.append(fp)
        if fps:
            self.episodes.append({
                "id": episode_id, "source_doc": doc.id,
                "pub_date": doc.pub_date, "facetpoints": fps,
            })

    def query(self, question: str, as_of: str | None = None) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        sections: list[str] = []
        for ek, facets in sorted(self.cone.items()):
            ent_lines: list[str] = []
            entity_display = ""
            for ak, fps in sorted(facets.items()):
                valid = [fp for fp in fps if fp["pub_date"] <= cutoff]
                if not valid:
                    continue
                latest = max(valid, key=lambda x: x["pub_date"])
                entity_display = latest["entity"]
                ent_lines.append(
                    f"  - Facet '{ak}': latest FacetPoint = {latest['value']} "
                    f"(at {latest['pub_date']}, {len(valid)} total)"
                )
            if ent_lines:
                sections.append(f"Entity: {entity_display}\n" + "\n".join(ent_lines))
        if not sections:
            return "(empty cone)"
        ctx = "\n\n".join(sections)
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _MFLOW_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"CONE (Entity > Facet > latest FacetPoint):\n{ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=100, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Rich-query variants for cross-entity temporal reasoning (E6)
#
# ZepLite / MFlowLite STORE full history but their query() methods collapse
# to latest-per-key at retrieval. That kills cross-entity temporal joins.
# These Rich variants expose the full history to the LLM at query time.
# ---------------------------------------------------------------------------


_ZEP_RICH_QUERY_SYSTEM = """Answer using the time-stamped triples below.
Each triple has a 'valid_from' timestamp. Triples are sorted chronologically.
For temporal or cross-entity queries ("what was X when Y was Z?"), reason
across multiple triples. Respond concisely with just the answer value.
"""


class ZepRich(ZepLite):
    """Zep variant that exposes ALL triples (not just latest-per-key) at
    query time, enabling cross-entity temporal reasoning.

    Same ingest cost as ZepLite; higher query-time context size.
    """
    def query(self, question: str, as_of: str | None = None) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        rel = [t for t in self.triples if t["valid_from"] <= cutoff]
        if not rel:
            return "(no triples)"
        ctx_lines = [
            f"- ({t['entity']}, {t['attribute']}) = {t['value']}  [valid_from {t['valid_from']}]"
            for t in sorted(rel, key=lambda x: x["valid_from"])
        ]
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _ZEP_RICH_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"TRIPLES ({len(rel)} total, chronological):\n"
                    + "\n".join(ctx_lines)
                    + f"\n\nQUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=200, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


_MFLOW_RICH_QUERY_SYSTEM = """Answer using the cone below. Each Entity has
attribute-Facets; each Facet lists ALL FacetPoints with timestamps.
For cross-entity or temporal queries, align timestamps across entities.
Respond concisely with just the answer value.
"""


_INTENT_CLASSIFIER_SYSTEM = """Classify the user's memory query into ONE of these
intent categories:
  current  — asks for the latest/current value of a single attribute
             (e.g., "What is Alice's current role?", "Who leads X?")
  historical — asks about past values, changes, or patterns over time
             (e.g., "How many times has X happened?", "What was it before?",
             "Between T1 and T2, what did X do?", "When did X first happen?")
  current_with_context — needs current value AND nearby history
             (e.g., "What is X currently and how did it change recently?")

Respond with ONLY the category name, no explanation.
"""


class IntentRoutedZep(ZepLite):
    """Preserves full history (ZepLite's storage) + routes queries by intent.

    The routing innovation: query-time, a fast LLM call classifies the query
    as {current, historical, current_with_context}. Each intent uses a
    different retrieval strategy over the SAME underlying triple store:
      - current:              latest-per-(entity,attribute) — ZepLite behavior
      - historical:           full-history exposure — ZepRich behavior
      - current_with_context: latest + last K timestamps per attribute

    Hypothesis (from project 8 decision.md): append-only storage is primary;
    this router sits on top and picks the right query surface per intent.
    Tests whether routing recovers from ZepRich's "too much context" failure
    on current-state queries (seen at E7-XL q9).
    """

    def _classify_intent(self, question: str) -> str:
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _INTENT_CLASSIFIER_SYSTEM},
                    {"role": "user", "content": f"Query: {question}\nCategory:"},
                ],
                max_tokens=20, temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
            if "historical" in raw:
                return "historical"
            if "with_context" in raw or "with context" in raw:
                return "current_with_context"
            return "current"
        except Exception:
            return "current"

    def _rich_query(self, question: str, as_of: str | None = None) -> str:
        """ZepRich-style full-history exposure."""
        cutoff = as_of or "9999-12-31T23:59:59"
        rel = [t for t in self.triples if t["valid_from"] <= cutoff]
        if not rel:
            return "(no triples)"
        ctx_lines = [
            f"- ({t['entity']}, {t['attribute']}) = {t['value']}  [valid_from {t['valid_from']}]"
            for t in sorted(rel, key=lambda x: x["valid_from"])
        ]
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": (
                    "Answer from the chronological triples below. For temporal "
                    "queries, reason across the full history. Be concise."
                )},
                {"role": "user", "content": (
                    f"TRIPLES ({len(rel)} total, chronological):\n"
                    + "\n".join(ctx_lines)
                    + f"\n\nQUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=200, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()

    def _current_with_context_query(
        self, question: str, as_of: str | None = None, k_recent: int = 5,
    ) -> str:
        """Latest-per-(entity,attribute) + the last K triples for context."""
        cutoff = as_of or "9999-12-31T23:59:59"
        rel = [t for t in self.triples if t["valid_from"] <= cutoff]
        if not rel:
            return "(no triples)"
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for t in rel:
            key = (t["entity"].lower(), t["attribute"].lower())
            if key not in latest or t["valid_from"] > latest[key]["valid_from"]:
                latest[key] = t
        recent = sorted(rel, key=lambda x: x["valid_from"], reverse=True)[:k_recent]
        ctx_lines = ["CURRENT STATE (latest per entity+attribute):"]
        ctx_lines += [
            f"- ({t['entity']}, {t['attribute']}) = {t['value']}  [as of {t['valid_from']}]"
            for t in sorted(latest.values(), key=lambda x: x["valid_from"], reverse=True)
        ]
        ctx_lines.append(f"\nRECENT HISTORY (last {k_recent}):")
        ctx_lines += [
            f"- ({t['entity']}, {t['attribute']}) = {t['value']}  [valid_from {t['valid_from']}]"
            for t in recent
        ]
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": (
                    "Answer using current state + recent history. Prefer the "
                    "current value unless the question explicitly asks about "
                    "recent change. Be concise."
                )},
                {"role": "user", "content": (
                    "\n".join(ctx_lines) + f"\n\nQUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=600, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()

    def query(self, question: str, as_of: str | None = None) -> str:
        intent = self._classify_intent(question)
        if intent == "historical":
            return self._rich_query(question, as_of)
        if intent == "current_with_context":
            return self._current_with_context_query(question, as_of)
        return super().query(question, as_of)


class MFlowRich(MFlowLite):
    """M-Flow variant that exposes all FacetPoints (not just latest) at
    query time. Enables cross-entity graph-path-style reasoning via LLM.
    """
    def query(self, question: str, as_of: str | None = None) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        sections: list[str] = []
        for ek, facets in sorted(self.cone.items()):
            ent_lines: list[str] = []
            entity_display = ek
            for ak, fps in sorted(facets.items()):
                valid = [fp for fp in fps if fp["pub_date"] <= cutoff]
                if not valid:
                    continue
                entity_display = valid[0]["entity"]
                fp_lines = [
                    f"      * {fp['value']} @ {fp['pub_date']}"
                    for fp in sorted(valid, key=lambda x: x["pub_date"])
                ]
                ent_lines.append(
                    f"  - Facet '{ak}' ({len(valid)} FacetPoints):\n"
                    + "\n".join(fp_lines)
                )
            if ent_lines:
                sections.append(f"Entity: {entity_display}\n" + "\n".join(ent_lines))
        if not sections:
            return "(empty cone)"
        ctx = "\n\n".join(sections)
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _MFLOW_RICH_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"CONE (full FacetPoint history):\n{ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=200, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# PrototypeMemory — synthesis of E1-E11 learnings
#
# Architecture:
#   - Append-only triple log (E6/E8/E9/E10: substrate primacy)
#   - Hot index for O(1) current-value lookup (E10: avoid full-scan latency)
#   - Intent classifier dispatches to the right query path (E10: 1000× speedup)
#   - Programmatic count for aggregation queries (E8 q3 lesson: LLM arithmetic
#     fails — said 16 instead of 19 on a count of 60 items)
#   - Open-world-aware prompts (E7 q6 lesson: distinguish "no record" from
#     "no event")
#   - Flat triple exposure, NOT hierarchical (E10 lesson: m_flow_rich's cone
#     hierarchy degraded fastest at scale — flat triple lists win)
# ---------------------------------------------------------------------------


_PROTOTYPE_INTENT_CLASSIFIER = """Classify the user's memory query into ONE of these
intent categories:
  current      — asks for the latest/current value of one attribute
                 ("What is X's current Y?", "Who currently leads Z?")
  historical   — asks about past values, transitions, initial state, OR
                 a duration / "when did X happen" / temporal lookup
                 ("What was X's first Y?", "Who was X before Y?",
                  "Has X ever been Z?", "When did X happen?",
                  "How many days did X take?", "How long ago was X?")
  count        — asks for a numeric count or FREQUENCY OF EVENTS
                 ("How many TIMES did X happen?", "How often was Y?")
                 NOTE: NOT for "how many days/weeks/months/years" —
                 those are durations, classify as historical.
  aggregate    — asks for sum / average / total / "across all" of values
                 across multiple mentions ("How much total did I spend?",
                 "What's the average X across all Y?", "altogether",
                 "combined total", "across the sessions")
  cross_entity — asks about correlations between two entities at a moment
                 ("What was X when Y was Z?")
  current_with_context — asks for current value plus brief recent context
                 ("What is X currently and what was it before?")

Respond with ONLY the category name, lowercase, no explanation.
"""


_PROTOTYPE_CURRENT_QUERY_SYSTEM = """Answer using the structured CURRENT STATE
table below. Each row is a single (entity, attribute) → latest value with
when it was last updated. If the queried entity or attribute is not in the
table, say so honestly — do NOT fabricate a value. For 'has X ever been Y?'
or 'is X resolved?' style queries, only answer 'yes' if the table or context
shows a positive record; otherwise answer 'no record / unknown'. Be concise:
return just the value or 'unknown'.
"""


_PROTOTYPE_HISTORICAL_QUERY_SYSTEM = """Answer from the time-stamped triples
below. For temporal queries (initial / first / before / after), reason
across the full chronology. If a queried (entity, attribute) has no triples,
say 'no record' rather than fabricating. Be concise.
"""


_PROTOTYPE_CROSS_ENTITY_QUERY_SYSTEM = """Answer using the time-stamped triples
below. For cross-entity queries ('what was X when Y was Z?'): first identify
the timestamp of the Y=Z event, then look up X's triple at that timestamp.
If exact-match is unavailable, take X's most recent triple AT or BEFORE the
target timestamp. If you cannot locate the anchoring event in the data,
answer 'no record'. Be concise.
"""


# Phase C 3 — aggregation prompt for multi-session sum/average/total/count
# questions ("how much total did I spend on luxury?", "average age across
# mentions?"). Uses chain-of-thought style enumerate-then-aggregate so the
# LLM doesn't silently miscount across many triples. Source-doc text is
# inlined per Phase C 2 so qualifying context ("luxury", "Gucci") is visible.
_PROTOTYPE_AGGREGATE_QUERY_SYSTEM = """Answer aggregation questions (sum,
total, average, count of items, "across all" / "altogether") using the
triples and source-doc text below.

REQUIRED FORMAT — list-then-aggregate:
1. First, enumerate every triple that is relevant to the question. One per
   line, format: "- (entity, attribute) = value [from source: brief reason]".
2. Then on a new line, perform the aggregation. Show the arithmetic
   explicitly when summing/averaging numbers.
3. End with a single concise final answer line: "ANSWER: <result>".

If no triples are relevant, answer "no record" — do NOT fabricate.
Use only the qualifying context from the inlined source quotes; do NOT
infer extra items not present in the data.
"""


# Phase B 2.3 — chunk-fallback retrieval prompt. Used only when structured
# retrieval is empty OR when the structured-path answer says "no record"
# (the relevant facts weren't extracted into triples). The LLM answers
# from raw conversation excerpts; if the excerpts truly don't contain the
# answer, it should still abstain — important for not regressing on
# legitimate-abstention cases.
_PROTOTYPE_CHUNK_FALLBACK_SYSTEM = """Answer the question using ONLY the
raw conversation excerpts below. Each excerpt is timestamped with its
publication date.

If the excerpts directly contain the answer, give it concisely (just the
value, no preamble).
If the excerpts don't contain the answer, say 'no record' rather than
fabricating.
Do NOT use background knowledge — only the supplied excerpts.
"""


# Heuristic: tokens to ignore when computing keyword overlap between
# question and raw doc text. Trimmed to the most common English words
# plus question words; not a full stoplist.
_CHUNK_FALLBACK_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "did", "does",
    "for", "from", "had", "has", "have", "how", "i", "in", "is", "it",
    "of", "on", "or", "say", "the", "to", "was", "were", "what", "when",
    "where", "which", "who", "why", "will", "with", "you", "your", "we",
    "they", "this", "that", "these", "those", "my", "me", "our", "ours",
    "us", "if", "then", "than", "but", "not", "no",
})

# Pattern that detects an answer indicating "no record / unknown" so the
# query method can decide to retry via the chunk-fallback path. Conservative
# — only matches answers that LEAD with the no-record phrase (avoids
# false positives on legitimate answers that happen to contain the words).
_NO_RECORD_LEAD_RE = re.compile(
    r"^\s*(?:\(\s*)?(no record|no information|unknown|"
    r"the (?:provided\s+)?memory (?:does not|doesn'?t) contain|"
    r"the (?:provided\s+)?(?:records|information) (?:do not|don'?t|does not|doesn'?t) "
    r"(?:contain|specify|mention)|"
    r"i (?:do not|don'?t) (?:know|have))",
    re.IGNORECASE,
)


def _is_no_record_answer(answer: str) -> bool:
    """True if the answer text reads as 'I don't know / no record'.
    Used by Phase B 2.3 to decide whether to retry via chunk-fallback."""
    if not answer or not answer.strip():
        return True
    return _NO_RECORD_LEAD_RE.match(answer.strip()) is not None


def _question_keywords(question: str) -> set[str]:
    """Tokens for keyword-overlap scoring. Lowercase, alpha-numeric, and
    drops common English stop-words + question words."""
    return {
        t for t in re.findall(r"\b\w+\b", question.lower())
        if t not in _CHUNK_FALLBACK_STOPWORDS and len(t) > 1
    }


def _doc_keywords(doc_text: str) -> set[str]:
    """Same tokenization as `_question_keywords` but over a doc body."""
    return {
        t for t in re.findall(r"\b\w+\b", doc_text.lower())
        if t not in _CHUNK_FALLBACK_STOPWORDS and len(t) > 1
    }


class PrototypeMemory:
    """Synthesis of E1-E11 learnings.

    Storage: append-only triple log + materialized hot index (latest-per-key).
    Same data lives in both — index is non-destructive.

    Query: intent classifier dispatches to:
      current → hot index O(1) lookup, latest-per-key context only
      historical → filtered scan, full chronological context
      count → programmatic aggregation, NO LLM arithmetic
      cross_entity → full-history with timestamp-alignment instructions
      current_with_context → hot index + last K triples for the queried key

    Hardened prompts: closed-world for current ("if not in table, say so"),
    open-world for historical ("no record" vs "no, never happened").
    """

    def __init__(self, llm: LLMClient, role: str = "agent_bulk"):
        self.llm = llm
        self.role = role
        # Append-only log
        self.triples: list[dict[str, Any]] = []
        # Hot index — materialized view, rebuilt on each ingest. Non-destructive.
        # hot_index[(entity_lower, attr_lower)] = latest triple dict
        self.hot_index: dict[tuple[str, str], dict[str, Any]] = {}
        # Phase B 2.3 — keep raw doc text for chunk-fallback retrieval. Used
        # only when structured retrieval comes up empty OR when the answer
        # LLM says "no record" despite having triples (because the relevant
        # facts weren't extracted into triples).
        self.raw_docs: list[Doc] = []
        # Phase C 1 — per-doc embedding cache for cosine-similarity chunk
        # retrieval. Computed once on ingest, keyed by doc.id. Falls back
        # to Jaccard only for docs whose embedding failed (or all docs if
        # no doc has an embedding). Higher recall on noisy haystacks where
        # keyword-overlap drowns the relevant doc out.
        self.doc_embeddings: dict[str, list[float]] = {}
        # Phase C 2 — O(1) lookup from doc.id → Doc (mirrors raw_docs).
        # Used by historical / cross_entity query paths to surface the
        # verbatim source-doc text alongside each triple in the answer-LLM
        # context. Targets multi-session questions where the structured
        # triple loses qualifying context (e.g. "$1200 Gucci handbag" →
        # triple value is "$1200" but the "luxury" qualifier lives in the
        # surrounding sentence).
        self.raw_doc_by_id: dict[str, Doc] = {}

    # ---- Write path ----

    def _maintain_hot_index(self, t: dict[str, Any]) -> None:
        key = (t["entity"].lower(), t["attribute"].lower())
        prior = self.hot_index.get(key)
        if prior is None or t["valid_from"] >= prior["valid_from"]:
            self.hot_index[key] = t

    def ingest(self, doc: Doc) -> None:
        """Extract triples from `doc` and append to the log.

        Phase B 2.1 — three-pass robust extraction:
          1. Strict JSON parse on the LLM's first output.
          2. On JSON-decode failure, repair-and-retry with a stricter prompt.
          3. If retry also fails, regex-salvage triples from the original
             malformed text. Better to recover what we can than drop everything.

        Raised the per-call max_tokens from 256 → 600 so multi-entity
        haystacks don't truncate mid-output (the leading cause of the
        "Unterminated string" failures observed on LongMemEval).
        """
        # Phase B 2.3 — keep the raw doc regardless of extraction outcome.
        # Even if extraction fails, the chunk-fallback path can still find
        # the relevant text from this doc later via keyword overlap.
        self.raw_docs.append(doc)
        # Phase C 2 — also key it by id for fast lookup from triples.
        self.raw_doc_by_id[doc.id] = doc

        # Phase C 1 — cache the doc's embedding for cosine chunk-retrieval.
        # Best-effort: an embedder failure for a single doc shouldn't block
        # ingest; that doc just won't be cosine-retrievable and will fall
        # through to the Jaccard path at query time.
        try:
            vec = self.llm.embed("embedding", doc.text)[0]
            self.doc_embeddings[doc.id] = vec
        except Exception as e:
            print(f"[prototype] embed failed on {doc.id}: {e}")

        # Pass 1: initial extract with strict JSON.
        raw_text = self._call_extract(doc)
        if raw_text is None:
            # LLM-call-level failure (network, rate limit). Don't try to repair —
            # we have nothing to repair from. Move on.
            return
        triples = _try_parse_triples(raw_text)
        if triples is None:
            # JSON parse failed — go to repair pass.
            triples = self._repair_extract(doc, raw_text)
        for raw in triples:
            if not isinstance(raw, dict):
                continue
            e = str(raw.get("entity", "")).strip()
            a = str(raw.get("attribute", "")).strip()
            v = str(raw.get("value", "")).strip()
            if not (e and a and v):
                continue
            t = {
                "entity": e, "attribute": a, "value": v,
                "valid_from": doc.pub_date, "source_doc": doc.id,
            }
            self.triples.append(t)
            self._maintain_hot_index(t)

    def _call_extract(self, doc: Doc) -> str | None:
        """Run the initial extract call. Returns the raw model text on
        success, None on LLM-level failure (where there's nothing to
        repair from). Uses the prototype-specific multi-value-aware
        extraction prompt from Phase B 2.2."""
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _PROTOTYPE_EXTRACT_SYSTEM},
                    {"role": "user", "content": (
                        f"DOCUMENT (published {doc.pub_date}):\n{doc.text}\n\n"
                        "Extract triples."
                    )},
                ],
                response_format={"type": "json_object"},
                max_tokens=600, temperature=0,
            )
            return resp.choices[0].message.content or "{}"
        except Exception as e:
            print(f"[prototype] extract LLM call failed on {doc.id}: {e}")
            return None

    def _repair_extract(self, doc: Doc, prior_output: str) -> list[dict[str, Any]]:
        """Pass 2 + 3 of robust extraction.

        Pass 2: re-prompt the LLM with the prior malformed output and a
        stricter instruction to return clean JSON only. If that parses,
        return its triples.
        Pass 3: regex-salvage triples from the ORIGINAL prior_output
        (more conservative than salvaging from the retry, which may have
        drifted further). Lower-quality but better than dropping all.
        """
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _PROTOTYPE_EXTRACT_SYSTEM},
                    {"role": "user", "content": (
                        f"DOCUMENT (published {doc.pub_date}):\n{doc.text}\n\n"
                        "Extract triples."
                    )},
                    {"role": "assistant", "content": prior_output[:1500]},
                    {"role": "user", "content": (
                        "The previous output was malformed JSON. Re-emit ONLY "
                        'valid JSON in the form {"triples":[{"entity":"...",'
                        '"attribute":"...","value":"..."}, ...]}. No preamble, '
                        "no commentary, no trailing text."
                    )},
                ],
                response_format={"type": "json_object"},
                max_tokens=600, temperature=0,
            )
            retry_text = resp.choices[0].message.content or "{}"
        except Exception:
            # Retry call itself failed — go straight to regex salvage.
            return _salvage_triples_from_text(prior_output)
        retry_triples = _try_parse_triples(retry_text)
        if retry_triples is not None:
            return retry_triples
        # Pass 3 — regex-salvage from the ORIGINAL output.
        return _salvage_triples_from_text(prior_output)

    def add_triple(
        self, *, entity: str, attribute: str, value: str,
        valid_from: str, source_doc: str = "",
    ) -> None:
        """Direct write API — useful for tests and scale benchmarks that
        skip the extraction step."""
        t = {
            "entity": entity, "attribute": attribute, "value": value,
            "valid_from": valid_from, "source_doc": source_doc,
        }
        self.triples.append(t)
        self._maintain_hot_index(t)

    # ---- Phase B 2.3 — chunk-fallback retrieval ----

    def _cosine_top_k(self, question: str, k: int = 3) -> list[Doc] | None:
        """Phase C 1 — cosine similarity over qwen3-embedding for
        chunk-fallback retrieval. Higher recall than Jaccard on noisy
        haystacks where the relevant doc shares few keywords with the
        question. Returns None if no docs have cached embeddings (caller
        falls back to Jaccard) or if the question embedding fails.
        """
        if not self.doc_embeddings:
            return None
        try:
            q_vec = self.llm.embed("embedding", question)[0]
        except Exception:
            return None
        scored: list[tuple[float, Doc]] = []
        for doc in self.raw_docs:
            vec = self.doc_embeddings.get(doc.id)
            if vec is None:
                continue
            score = cosine(q_vec, vec)
            scored.append((score, doc))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:k]]

    def _jaccard_top_k(self, question: str, k: int = 3) -> list[Doc] | None:
        """Keyword-overlap top-k. Used as fallback when cosine is
        unavailable (no embeddings cached, embedder failed, or test
        scenarios). Returns None if no doc has any keyword overlap (so
        caller knows to abstain rather than feed noise to the LLM)."""
        qkw = _question_keywords(question)
        if not qkw:
            return None
        scored: list[tuple[float, Doc]] = []
        for doc in self.raw_docs:
            dkw = _doc_keywords(doc.text)
            if not dkw:
                continue
            overlap = len(qkw & dkw)
            if overlap == 0:
                continue
            # Jaccard with +1 smoothing so very-short docs don't blow up.
            score = overlap / (1 + len(qkw | dkw))
            scored.append((score, doc))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:k]]

    def _chunk_fallback(self, question: str, k: int = 3) -> str:
        """Top-k of raw docs by relevance → answer LLM. Fires when the
        structured path is empty or when its answer reads as 'no record'.
        Phase C 1 prefers cosine via qwen3-embedding (higher recall on
        noisy haystacks); falls back to Jaccard keyword-overlap when no
        embeddings are cached. Returns 'no record' if both retrieval
        modes find nothing relevant — don't feed irrelevant noise to
        the LLM."""
        if not self.raw_docs:
            return "(no record)"
        # Phase C 1 — try cosine first.
        top = self._cosine_top_k(question, k)
        if not top:
            # No embeddings cached / question embed failed — Jaccard fallback.
            top = self._jaccard_top_k(question, k)
        if not top:
            return "(no record)"
        ctx = "\n\n---\n\n".join(
            f"[published {d.pub_date}] {d.text}" for d in top
        )
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _PROTOTYPE_CHUNK_FALLBACK_SYSTEM},
                    {"role": "user", "content": (
                        f"EXCERPTS:\n{ctx}\n\nQUESTION: {question}\nAnswer:"
                    )},
                ],
                max_tokens=300, temperature=0.1,
            )
            return (resp.choices[0].message.content or "(no record)").strip()
        except Exception:
            return "(no record)"

    # ---- Intent classification ----

    # Keyword shortcuts that bypass the LLM classifier when the signal is
    # unambiguous. Prevents classifier-flake on questions like "how many
    # times was X" which should reliably route to the count handler.
    #
    # NOTE: bare "how many" was REMOVED 2026-04-26 after LongMemEval
    # diagnosed misroutes on temporal-reasoning questions like "How many
    # days did X take?" — those are *duration* questions (historical),
    # not *event-count* questions. Keep only the specific-frequency phrases.
    _COUNT_KEYWORDS: tuple[str, ...] = (
        "how many times", "how often", "count of", "number of times",
        "frequency of", "how frequently",
    )
    # Duration keywords route to historical, NOT count. These questions
    # ("how many days...", "how long...") need chronology, not event-count.
    _DURATION_KEYWORDS: tuple[str, ...] = (
        "how many days", "how many weeks", "how many months",
        "how many years", "how many hours", "how many minutes",
        "how long", "how long ago",
    )
    _CROSS_ENTITY_KEYWORDS: tuple[str, ...] = (
        " at the time ", " at the moment ",
    )
    # Phase C 3 — aggregation keywords route to the new aggregate path.
    # These are sum / average / total style multi-session questions:
    # "how much total did I spend?", "what's the average X across all Y?",
    # "altogether", "combined". Detected before count to avoid the
    # frequency keywords ("how many times") shadowing them.
    _AGGREGATE_KEYWORDS: tuple[str, ...] = (
        "total amount", "in total", "altogether", "combined",
        "across all", "across multiple", "across the sessions",
        "average ", "the sum of", "summed across", "grand total",
    )

    def _classify_intent(self, question: str) -> str:
        lower_q = " " + question.lower() + " "
        # Fast-path: duration questions route to HISTORICAL, not count.
        # Must be checked BEFORE count keywords since "how many days" is
        # both a duration AND a substring of (now-removed) "how many".
        for kw in self._DURATION_KEYWORDS:
            if kw in lower_q:
                return "historical"
        # Phase C 3 — aggregate (sum / average / total / across-all) route.
        # Checked before count so frequency-keyword overlap doesn't shadow
        # genuine aggregation questions ("total combined" etc).
        for kw in self._AGGREGATE_KEYWORDS:
            if kw in lower_q:
                return "aggregate"
        # Fast-path: unambiguous count signals bypass the LLM classifier.
        # The LLM was sometimes mis-routing these to 'historical'.
        for kw in self._COUNT_KEYWORDS:
            if kw in lower_q:
                return "count"
        # Fast-path: cross-entity correlation phrases
        for kw in self._CROSS_ENTITY_KEYWORDS:
            if kw in lower_q:
                return "cross_entity"

        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _PROTOTYPE_INTENT_CLASSIFIER},
                    {"role": "user", "content": f"Query: {question}\nCategory:"},
                ],
                max_tokens=20, temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
        except Exception:
            return "current"
        # Map fuzzy responses
        if "aggregate" in raw:
            return "aggregate"
        if "count" in raw:
            # Phase B 2.4 — post-classification sanity check. The LLM
            # occasionally classifies temporal-reasoning questions as
            # 'count' when no count keyword is present (LongMemEval Q30
            # output "0" for a duration question). Override to historical
            # if the question contains none of the explicit count-frequency
            # phrases — those are already handled by the keyword fast-path
            # above, so a count classification this far down is suspicious.
            if not any(kw in lower_q for kw in self._COUNT_KEYWORDS):
                return "historical"
            return "count"
        if "cross_entity" in raw or "cross entity" in raw or "cross-entity" in raw:
            return "cross_entity"
        if "historical" in raw:
            return "historical"
        if "with_context" in raw or "with context" in raw:
            return "current_with_context"
        return "current"

    # ---- Read paths ----

    def _current_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        # Hot index gives us all latest-per-(entity, attribute) in O(1)
        rows = [
            r for r in self.hot_index.values()
            if r["valid_from"] <= cutoff
        ]
        if not rows:
            # Phase B 2.3 Case A — no triples to reason from. Try chunks.
            return self._chunk_fallback(question)
        ctx = "\n".join(
            f"- ({r['entity']}, {r['attribute']}) = {r['value']}  "
            f"[updated {r['valid_from']}]"
            for r in sorted(rows, key=lambda x: x["valid_from"], reverse=True)
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _PROTOTYPE_CURRENT_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"CURRENT STATE:\n{ctx}\n\nQUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=600, temperature=0.1,
        )
        answer = (resp.choices[0].message.content or "").strip()
        return self._maybe_chunk_fallback(question, answer)

    def _historical_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        rel = [t for t in self.triples if t["valid_from"] <= cutoff]
        if not rel:
            # Phase B 2.3 Case A
            return self._chunk_fallback(question)
        # Phase C 2 — pair each triple with its source-doc text so the
        # answer LLM sees verbatim qualifying context (e.g. "luxury",
        # "white", "Gucci") that gets stripped during triple decomposition.
        ctx = self._format_triples_with_source(
            sorted(rel, key=lambda x: x["valid_from"])
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _PROTOTYPE_HISTORICAL_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"TRIPLES ({len(rel)} total, chronological):\n{ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=600, temperature=0.1,
        )
        answer = (resp.choices[0].message.content or "").strip()
        return self._maybe_chunk_fallback(question, answer)

    def _cross_entity_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        rel = [t for t in self.triples if t["valid_from"] <= cutoff]
        if not rel:
            # Phase B 2.3 Case A
            return self._chunk_fallback(question)
        # Phase C 2 — pair each triple with source-doc text (same as historical).
        ctx = self._format_triples_with_source(
            sorted(rel, key=lambda x: x["valid_from"])
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _PROTOTYPE_CROSS_ENTITY_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"TRIPLES ({len(rel)} total, chronological):\n{ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=600, temperature=0.1,
        )
        answer = (resp.choices[0].message.content or "").strip()
        return self._maybe_chunk_fallback(question, answer)

    def _format_triples_with_source(
        self, triples: list[dict[str, Any]], max_source_chars: int = 200,
    ) -> str:
        """Phase C 2 — format triples with their source-doc text inlined.

        Multi-session aggregation questions need the answer LLM to see
        verbatim qualifying context ("luxury", "Gucci", "white" etc.)
        that gets stripped when (entity, attribute, value) decomposition
        splits a sentence into pieces. Including the source-doc text
        beneath each triple gives the LLM both the structured signal
        (for matching) AND the natural-language context (for nuance).

        max_source_chars caps the per-triple source quote so a single
        long doc doesn't dominate the context. Triples that share a
        source_doc see the same quoted excerpt — duplicated text is
        cheap and ergonomic.
        """
        seen_sources: set[str] = set()
        lines: list[str] = []
        for t in triples:
            line = (
                f"- ({t['entity']}, {t['attribute']}) = {t['value']}  "
                f"[valid_from {t['valid_from']}]"
            )
            src_id = t.get("source_doc")
            doc = self.raw_doc_by_id.get(src_id) if src_id else None
            if doc and src_id not in seen_sources:
                # Inline a short verbatim excerpt from the source doc.
                excerpt = (doc.text or "").strip()[:max_source_chars]
                if excerpt:
                    line += f'\n    source ({src_id}): "{excerpt}"'
                    seen_sources.add(src_id)
            lines.append(line)
        return "\n".join(lines)

    def _count_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        """Programmatic count — bypass LLM arithmetic.

        Heuristic: extract candidate (entity, attribute, value) signature
        from the question via a fast LLM call, then count matching triples.
        Falls back to historical_query if extraction is ambiguous.
        """
        # Use a focused prompt to pull the search criteria
        criteria_prompt = (
            "From this question, extract the search criteria as JSON with optional "
            "fields: entity, attribute, value. Only include fields the question "
            "specifies; omit unspecified fields. Return ONLY JSON.\n"
            f"Question: {question}"
        )
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": (
                        "Extract search criteria as JSON. Be conservative: only "
                        "include fields the question explicitly mentions."
                    )},
                    {"role": "user", "content": criteria_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=80, temperature=0,
            )
            crit = json.loads(resp.choices[0].message.content or "{}")
        except Exception:
            crit = {}

        import re
        cutoff = as_of or "9999-12-31T23:59:59"
        e_filter = crit.get("entity")
        a_filter = crit.get("attribute")
        v_filter = crit.get("value")

        if not (e_filter or a_filter or v_filter):
            # Couldn't pin down criteria — fall back to historical
            return self._historical_query(question, as_of=as_of)

        # Word-boundary matching: criterion "C" must match the WORD "C"
        # (in "project C") not just any "c" character (e.g. inside "project").
        # This avoided a real bug seen on E8: substring matching counted all
        # 60 triples because "c" appeared inside "project".
        def _matches(text: str, criterion: str | None) -> bool:
            if not criterion:
                return True
            pattern = re.compile(
                rf"\b{re.escape(criterion)}\b", re.IGNORECASE,
            )
            return pattern.search(text or "") is not None

        n = 0
        for t in self.triples:
            if t["valid_from"] > cutoff:
                continue
            if not _matches(t["entity"], e_filter):
                continue
            if not _matches(t["attribute"], a_filter):
                continue
            if not _matches(t["value"], v_filter):
                continue
            n += 1
        return str(n)

    def _current_with_context_query(
        self, question: str, as_of: str | None = None, k_recent: int = 5,
    ) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        latest_rows = [
            r for r in self.hot_index.values()
            if r["valid_from"] <= cutoff
        ]
        if not latest_rows:
            # Phase B 2.3 Case A
            return self._chunk_fallback(question)
        recent = sorted(
            (t for t in self.triples if t["valid_from"] <= cutoff),
            key=lambda x: x["valid_from"], reverse=True,
        )[:k_recent]
        ctx_lines = ["CURRENT STATE (latest per entity+attribute):"]
        ctx_lines += [
            f"- ({r['entity']}, {r['attribute']}) = {r['value']}  [as of {r['valid_from']}]"
            for r in sorted(latest_rows, key=lambda x: x["valid_from"], reverse=True)
        ]
        ctx_lines.append(f"\nRECENT HISTORY (last {k_recent} observations):")
        ctx_lines += [
            f"- ({t['entity']}, {t['attribute']}) = {t['value']}  [valid_from {t['valid_from']}]"
            for t in recent
        ]
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": (
                    "Answer using current state + recent history. Prefer the "
                    "current value unless the question explicitly asks about "
                    "a recent change. If queried entity/attribute not present, "
                    "say 'no record'. Be concise."
                )},
                {"role": "user", "content": (
                    "\n".join(ctx_lines) + f"\n\nQUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=600, temperature=0.1,
        )
        answer = (resp.choices[0].message.content or "").strip()
        return self._maybe_chunk_fallback(question, answer)

    def _maybe_chunk_fallback(self, question: str, structured_answer: str) -> str:
        """Phase B 2.3 Case B — if the structured-path answer reads as
        'no record' but raw docs may contain the answer, retry via the
        chunk-fallback path. If chunks ALSO say 'no record', keep the
        structured answer (legitimate abstention should be preserved).
        """
        if not _is_no_record_answer(structured_answer):
            return structured_answer
        chunk_answer = self._chunk_fallback(question)
        if _is_no_record_answer(chunk_answer):
            return structured_answer
        return chunk_answer

    def _aggregate_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        """Phase C 3 — multi-session aggregation (sum / average / total
        / across-all). Uses the same triple retrieval as historical, plus
        Phase C 2's source-doc context, plus a chain-of-thought prompt
        that forces the LLM to enumerate before aggregating.

        Returns the LAST line after 'ANSWER:' if the LLM follows the
        format, otherwise the full enumerate-then-aggregate response.
        Aggressive parse-and-extract is left for a follow-up; this is a
        prompt-engineering pass."""
        cutoff = as_of or "9999-12-31T23:59:59"
        rel = [t for t in self.triples if t["valid_from"] <= cutoff]
        if not rel:
            # Phase B 2.3 Case A
            return self._chunk_fallback(question)
        ctx = self._format_triples_with_source(
            sorted(rel, key=lambda x: x["valid_from"])
        )
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _PROTOTYPE_AGGREGATE_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"TRIPLES ({len(rel)} total, chronological):\n{ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            # Bigger token budget — enumerate + aggregate is verbose.
            max_tokens=900, temperature=0.1,
        )
        full = (resp.choices[0].message.content or "").strip()
        # Extract just the final answer line if the LLM followed the format.
        for line in reversed(full.splitlines()):
            stripped = line.strip()
            if stripped.upper().startswith("ANSWER:"):
                final = stripped[len("ANSWER:"):].strip()
                # Phase B 2.3 Case B applies here too — if final is "no record",
                # try chunk fallback.
                return self._maybe_chunk_fallback(question, final)
        # LLM didn't emit ANSWER: line — return the full output and let the
        # judge decide. Still apply Case B (no-record retry).
        return self._maybe_chunk_fallback(question, full)

    def query(self, question: str, as_of: str | None = None) -> str:
        intent = self._classify_intent(question)
        if intent == "count":
            return self._count_query(question, as_of=as_of)
        if intent == "aggregate":
            return self._aggregate_query(question, as_of=as_of)
        if intent == "historical":
            return self._historical_query(question, as_of=as_of)
        if intent == "cross_entity":
            return self._cross_entity_query(question, as_of=as_of)
        if intent == "current_with_context":
            return self._current_with_context_query(question, as_of=as_of)
        return self._current_query(question, as_of=as_of)


# ---------------------------------------------------------------------------
# MultiTierMemory — adds episode summarization tier on top of PrototypeMemory
#
# Motivation: E10-XL empirically proved that "expose all chronological history"
# fails at 10k+ triples (HTTP 400 context overflow). At 5000 triples zep_rich
# took 5+ minutes per query; at 10000+ it crashes immediately.
#
# Architecture (the 5th necessary component):
#   - Triples accumulate in the append-only log (inherited).
#   - Hot index for current queries (inherited).
#   - When triples reach `episode_size`, compress oldest batch into an
#     EpisodeSummary: per-(entity, attribute) digest + optional NL summary.
#   - Historical queries at scale use episode summaries + recent triples +
#     hot index instead of raw all-triples exposure. Drops context from
#     500K tokens to ~5-50K.
#   - Count queries can aggregate from episode digests (programmatic, fast).
# ---------------------------------------------------------------------------


@dataclass
class EpisodeSummary:
    """A digest of a contiguous range of triples.

    Programmatic digest (facets dict) is computed deterministically from
    the triples — no LLM needed. Optional NL summary is LLM-generated and
    can be omitted for benchmarks / tests.
    """
    episode_id: str
    start_date: str
    end_date: str
    triple_count: int
    entities: tuple[str, ...]
    # facets[(entity_lower, attribute_lower)] = {
    #   "first_value", "first_at", "last_value", "last_at",
    #   "value_counts": {value: int}, "transition_count"
    # }
    facets: dict[tuple[str, str], dict[str, Any]]
    summary_text: str = ""  # optional LLM-generated NL summary


def _compute_episode_facets(
    triples: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    """Programmatic per-(entity, attribute) digest. No LLM."""
    facets: dict[tuple[str, str], dict[str, Any]] = {}
    sorted_t = sorted(triples, key=lambda t: t["valid_from"])
    for t in sorted_t:
        key = (t["entity"].lower(), t["attribute"].lower())
        d = facets.setdefault(key, {
            "entity": t["entity"], "attribute": t["attribute"],
            "first_value": t["value"], "first_at": t["valid_from"],
            "last_value": t["value"], "last_at": t["valid_from"],
            "value_counts": {}, "transition_count": 0,
            "prior_value": t["value"],
        })
        # Update last_value
        if t["valid_from"] >= d["last_at"]:
            if t["value"] != d["prior_value"]:
                d["transition_count"] += 1
                d["prior_value"] = t["value"]
            d["last_value"] = t["value"]
            d["last_at"] = t["valid_from"]
        d["value_counts"][t["value"]] = d["value_counts"].get(t["value"], 0) + 1
    # Strip the helper field
    for d in facets.values():
        d.pop("prior_value", None)
    return facets


_MULTITIER_HISTORICAL_SYSTEM = """Answer the historical question below using
EPISODE SUMMARIES (compressed digests of older history) plus RECENT TRIPLES
(uncompressed last batch). Each Episode summary lists per-(entity, attribute)
first/last values and transition counts within that time window.

For "first observed" queries, use the FIRST episode that contains the entity.
For point-in-time queries, find the episode whose time range covers the target
and report the relevant facet's value.
For aggregation queries, sum the per-episode counts.
If no episode or recent triple covers the queried fact, say "no record".
Be concise.
"""


class MultiTierMemory(PrototypeMemory):
    """PrototypeMemory + episode summarization tier.

    Triples roll up into episodes once `episode_size` accumulates. Historical
    queries at scale use episode digests instead of full triple exposure,
    avoiding the context overflow that crashed zep_rich at 10k+ triples (E10-XL).

    For benchmarks, compression is programmatic-only (no LLM) by default.
    Set `use_llm_for_nl_summary=True` to additionally generate natural-language
    summaries via the configured LLM at compression time.
    """

    def __init__(
        self, llm: LLMClient, role: str = "agent_bulk",
        episode_size: int = 1000,
        use_llm_for_nl_summary: bool = False,
        # Threshold above which historical queries route to summary-based path
        # rather than full-triple exposure. Default: episode_size.
        history_summary_threshold: int | None = None,
    ):
        super().__init__(llm, role)
        self.episode_size = episode_size
        self.use_llm_for_nl_summary = use_llm_for_nl_summary
        self.history_summary_threshold = (
            history_summary_threshold if history_summary_threshold is not None
            else episode_size
        )
        self.episodes: list[EpisodeSummary] = []
        # Track which triples have been compressed (by source_doc id).
        self._compressed_ids: set[str] = set()

    def _maybe_compress(self) -> None:
        """If unsummarized triples have crossed `episode_size`, compress the
        oldest `episode_size` of them into a new Episode."""
        unsummarized = [
            t for t in self.triples
            if t["source_doc"] not in self._compressed_ids
        ]
        # Sort by valid_from to compress oldest first
        unsummarized.sort(key=lambda t: t["valid_from"])
        while len(unsummarized) >= self.episode_size:
            batch = unsummarized[:self.episode_size]
            unsummarized = unsummarized[self.episode_size:]
            self._compress_batch(batch)

    def _compress_batch(self, batch: list[dict[str, Any]]) -> None:
        if not batch:
            return
        facets = _compute_episode_facets(batch)
        entities = tuple(sorted({t["entity"] for t in batch}))
        ep_id = f"ep_{len(self.episodes):04d}"
        nl_summary = ""
        if self.use_llm_for_nl_summary:
            try:
                resp = self.llm.chat(
                    self.role,
                    messages=[
                        {"role": "system", "content": (
                            "You produce concise 2-3 sentence summaries of "
                            "research-pipeline observation cohorts. Stick to "
                            "what the data shows."
                        )},
                        {"role": "user", "content": (
                            f"Cohort summary inputs (programmatic digest):\n"
                            f"  entities: {entities}\n"
                            f"  date range: {batch[0]['valid_from']} → "
                            f"{batch[-1]['valid_from']}\n"
                            f"  facet count: {len(facets)}\n"
                            "Write a 2-3 sentence NL summary."
                        )},
                    ],
                    max_tokens=200, temperature=0.1,
                )
                nl_summary = (resp.choices[0].message.content or "").strip()
            except Exception as e:
                print(f"[multitier] NL summary failed for {ep_id}: {e}")
        ep = EpisodeSummary(
            episode_id=ep_id,
            start_date=batch[0]["valid_from"],
            end_date=batch[-1]["valid_from"],
            triple_count=len(batch),
            entities=entities,
            facets=facets,
            summary_text=nl_summary,
        )
        self.episodes.append(ep)
        for t in batch:
            self._compressed_ids.add(t["source_doc"])

    # Override write paths to trigger compression
    def add_triple(
        self, *, entity: str, attribute: str, value: str,
        valid_from: str, source_doc: str = "",
    ) -> None:
        super().add_triple(
            entity=entity, attribute=attribute, value=value,
            valid_from=valid_from, source_doc=source_doc,
        )
        self._maybe_compress()

    def ingest(self, doc: Doc) -> None:
        super().ingest(doc)
        self._maybe_compress()

    # ---- Read paths ----

    def _format_episodes_for_prompt(self) -> str:
        """Compact LLM-context-friendly view of all episode summaries."""
        if not self.episodes:
            return "(no compressed episodes yet)"
        lines: list[str] = []
        for ep in self.episodes:
            lines.append(
                f"Episode {ep.episode_id} [{ep.start_date} → {ep.end_date}, "
                f"{ep.triple_count} obs, entities={list(ep.entities)}]:"
            )
            for _, f in sorted(ep.facets.items()):
                vc = f.get("value_counts", {})
                vc_str = ", ".join(f"{v}×{c}" for v, c in vc.items())
                lines.append(
                    f"  ({f['entity']}, {f['attribute']}): "
                    f"first={f['first_value']}@{f['first_at']}, "
                    f"last={f['last_value']}@{f['last_at']}, "
                    f"transitions={f['transition_count']}, counts={{{vc_str}}}"
                )
            if ep.summary_text:
                lines.append(f"  NL: {ep.summary_text}")
        return "\n".join(lines)

    def _historical_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        # Small-corpus path: use the inherited full-history exposure.
        if len(self.triples) <= self.history_summary_threshold:
            return super()._historical_query(question, as_of=as_of)
        # Large-corpus path: episode summaries + recent uncompressed triples.
        cutoff = as_of or "9999-12-31T23:59:59"
        recent = [
            t for t in self.triples
            if t["source_doc"] not in self._compressed_ids
            and t["valid_from"] <= cutoff
        ]
        recent.sort(key=lambda x: x["valid_from"])
        recent_ctx = "\n".join(
            f"- ({t['entity']}, {t['attribute']}) = {t['value']}  "
            f"[valid_from {t['valid_from']}]"
            for t in recent
        ) or "(none)"
        episodes_ctx = self._format_episodes_for_prompt()
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _MULTITIER_HISTORICAL_SYSTEM},
                {"role": "user", "content": (
                    f"EPISODE SUMMARIES:\n{episodes_ctx}\n\n"
                    f"RECENT TRIPLES (uncompressed, {len(recent)}):\n{recent_ctx}\n\n"
                    f"QUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=600, temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()

    def _count_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        """If we have compressed episodes, count from per-episode digests
        plus uncompressed triples — much faster than scanning all triples
        and avoids the LLM altogether after criteria extraction."""
        # Reuse the parent's criteria extractor logic. We need to call it but
        # then short-circuit the loop.
        import json
        try:
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": (
                        "Extract search criteria as JSON. Be conservative: only "
                        "include fields the question explicitly mentions."
                    )},
                    {"role": "user", "content": (
                        "From this question, extract the search criteria as JSON "
                        "with optional fields: entity, attribute, value. Only "
                        "include fields the question specifies; omit "
                        "unspecified fields. Return ONLY JSON.\n"
                        f"Question: {question}"
                    )},
                ],
                response_format={"type": "json_object"},
                max_tokens=80, temperature=0,
            )
            crit = json.loads(resp.choices[0].message.content or "{}")
        except Exception:
            crit = {}

        e_filter = crit.get("entity")
        a_filter = crit.get("attribute")
        v_filter = crit.get("value")
        if not (e_filter or a_filter or v_filter):
            return self._historical_query(question, as_of=as_of)

        import re
        def _matches(text: str, criterion: str | None) -> bool:
            if not criterion:
                return True
            return bool(re.search(
                rf"\b{re.escape(criterion)}\b", text or "", re.IGNORECASE,
            ))

        # Aggregate from episode digests
        n = 0
        for ep in self.episodes:
            for f in ep.facets.values():
                if not _matches(f["entity"], e_filter):
                    continue
                if not _matches(f["attribute"], a_filter):
                    continue
                # Sum value_counts for matching values
                for v, c in f["value_counts"].items():
                    if _matches(v, v_filter):
                        n += c
        # Add uncompressed triples
        cutoff = as_of or "9999-12-31T23:59:59"
        for t in self.triples:
            if t["source_doc"] in self._compressed_ids:
                continue
            if t["valid_from"] > cutoff:
                continue
            if not _matches(t["entity"], e_filter):
                continue
            if not _matches(t["attribute"], a_filter):
                continue
            if not _matches(t["value"], v_filter):
                continue
            n += 1
        return str(n)


# =============================================================================
# INNOVATION VARIANTS — see docs/agent-memory-prototype-innovations.md
# =============================================================================
# These two classes intentionally depart from the "passive store + query-time
# retrieval" template every existing memory system shares (mem0, zep,
# supermemory, m_flow, our own PrototypeMemory/MultiTierMemory). They do NOT
# patch PrototypeMemory's storage — they redefine what storage represents.


@dataclass
class EpistemicClaim:
    """A claim with its lineage and conviction trajectory.

    Lives parallel to the parent's append-only triple log. Where the parent's
    hot_index keeps a SINGLE latest value per (entity, attribute), this keeps
    the FULL value space — every value ever observed — each as its own claim
    with conviction that grows on reinforcement.
    """
    entity: str
    attribute: str
    value: str
    sources: list[str]            # source_doc ids supporting this value
    seen_count: int               # times this exact (e, a, v) has been ingested
    conviction: float             # 0.0–1.0
    first_seen_at: str
    last_seen_at: str
    history: list[dict[str, str]]  # [{action, source, valid_from}, ...]


_EPISTEMIC_QUERY_SYSTEM = """Answer the question using the CLAIMS below.

Each claim has a conviction (0.0–1.0) and a mention count. Format per key:
  (entity, attribute):
    ▸ "value-A" [conviction X.XX, N mention(s)]
      competing: "value-B" [conviction Y.YY, M mention(s)]   (if any)

Rules:
- If a single claim per key (no "competing"), answer with its value.
- If multiple competing claims and convictions DIFFER by >= 0.2, answer with
  the highest-conviction value.
- If competing claims are within 0.2 of each other, surface BOTH with brief
  attribution.
- If the question explicitly asks for contested or older values, use the
  history accordingly.
- If no claim covers the question, say "no record" honestly.

Be concise — return just the value when possible.
"""


class EpistemicPrototype(PrototypeMemory):
    """Memory whose storage primitive is a conviction trajectory, not a value.

    Diverges from PrototypeMemory at exactly one point: the hot index. Where
    the parent's hot_index maps (entity, attribute) → latest_triple, this
    class maintains a parallel `claims` map of (entity, attribute) → list of
    EpistemicClaim, each carrying conviction, source list, and history.

    On reinforcement (same e/a/v re-ingested), conviction climbs. On a new
    value for the same (e, a), the existing claims are kept as competing —
    nothing is overwritten. Retrieval surfaces the multi-claim picture to
    the LLM rather than picking a winner upstream.
    """

    def __init__(self, llm: LLMClient, role: str = "agent_bulk"):
        super().__init__(llm, role)
        # claims[(entity_lower, attr_lower)] = list[EpistemicClaim]
        self.claims: dict[tuple[str, str], list[EpistemicClaim]] = {}

    def _maintain_hot_index(self, t: dict[str, Any]) -> None:
        # Keep the parent's hot index intact so historical/count/cross-entity
        # paths continue to work — those don't benefit from epistemic shape.
        super()._maintain_hot_index(t)
        # Update the parallel claim store.
        key = (t["entity"].lower(), t["attribute"].lower())
        bucket = self.claims.setdefault(key, [])
        for c in bucket:
            if c.value.lower() == t["value"].lower():
                c.seen_count += 1
                c.conviction = min(1.0, c.conviction + 0.1)
                c.sources.append(t["source_doc"])
                if t["valid_from"] > c.last_seen_at:
                    c.last_seen_at = t["valid_from"]
                c.history.append({
                    "action": "reinforced",
                    "source": t["source_doc"],
                    "valid_from": t["valid_from"],
                })
                return
        bucket.append(EpistemicClaim(
            entity=t["entity"], attribute=t["attribute"], value=t["value"],
            sources=[t["source_doc"]],
            seen_count=1,
            conviction=0.5,
            first_seen_at=t["valid_from"],
            last_seen_at=t["valid_from"],
            history=[{
                "action": "introduced",
                "source": t["source_doc"],
                "valid_from": t["valid_from"],
            }],
        ))

    def _current_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        """Override: surface the conviction-rich multi-claim picture."""
        cutoff = as_of or "9999-12-31T23:59:59"
        rel: list[tuple[tuple[str, str], list[EpistemicClaim]]] = []
        for key, bucket in self.claims.items():
            in_window = [c for c in bucket if c.first_seen_at <= cutoff]
            if in_window:
                rel.append((key, in_window))
        if not rel:
            return self._chunk_fallback(question)

        # Keyword-narrow to relevant keys (cheap; mirrors parent's relevance
        # heuristic). If narrowing eliminates everything, fall back to all so
        # the answer-LLM still has context.
        kw = _question_keywords(question)
        narrowed: list[tuple[tuple[str, str], list[EpistemicClaim]]] = []
        for key, bucket in rel:
            tokens = set((key[0] + " " + key[1]).split())
            if tokens & kw:
                narrowed.append((key, bucket))
        if not narrowed:
            narrowed = rel

        lines: list[str] = []
        for key, bucket in narrowed[:30]:  # cap context
            sorted_claims = sorted(bucket, key=lambda c: -c.conviction)
            top = sorted_claims[0]
            lines.append(f"({top.entity}, {top.attribute}):")
            for i, c in enumerate(sorted_claims):
                marker = "▸" if i == 0 else "  competing:"
                lines.append(
                    f"  {marker} \"{c.value}\" "
                    f"[conviction {c.conviction:.2f}, {c.seen_count} mention(s)]"
                )
        ctx = "\n".join(lines) or "(no relevant claims)"

        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _EPISTEMIC_QUERY_SYSTEM},
                {"role": "user", "content": (
                    f"CLAIMS:\n{ctx}\n\nQUESTION: {question}\nAnswer:"
                )},
            ],
            max_tokens=600, temperature=0.1,
        )
        answer = (resp.choices[0].message.content or "").strip()
        return self._maybe_chunk_fallback(question, answer)


@dataclass
class Gap:
    """An identified unknown — a question the memory cannot currently answer."""
    question: str             # natural-language form
    related_entity: str       # entity the gap is about
    related_attribute: str    # missing attribute
    introduced_at: str        # source_doc that triggered the detection
    resolved_by: str | None = None  # source_doc that filled the gap
    resolved_value: str | None = None


_GAP_DETECT_SYSTEM = """You inspect a document to identify SPECIFIC unknowns it
raises — facts that the document MENTIONS or IMPLIES but does NOT specify.

Examples:
- "User bought a Honda Civic" → unknowns: year, model trim, mileage, color
- "Team had a meeting yesterday" → unknowns: attendees, decisions, duration
- "User got a new laptop" → unknowns: brand, model, price, when

Do NOT list facts the document already states explicitly. Only list
genuinely-missing details a follow-up question would naturally ask.

Return STRICT JSON: {"gaps": [{"question": "...", "entity": "...",
"attribute": "..."}]}. Return 0–5 gaps. If the doc raises no clear
unknowns, return {"gaps": []}.
"""


_GAP_AWARE_QUERY_SYSTEM = """Answer the question using the CURRENT STATE
triples below. If the question targets a fact listed under KNOWN UNKNOWNS,
honestly say "no record" rather than guessing — the system has explicitly
flagged this as something it tracked but never observed.

For other questions, answer concisely from the triples. If no triple
covers the question and it is not a known unknown, say "no record".
"""


class GapAwarePrototype(PrototypeMemory):
    """Memory that tracks what it doesn't know.

    After each ingest, an LLM identifies 0–5 unknowns raised by the doc
    (mentioned-but-unspecified details) and stores them as Gap entries. On
    every subsequent ingest, gaps are checked: if a new triple matches an
    open gap's (entity, attribute), the gap is marked resolved.

    On query, the LLM sees both the matched triples AND any gaps relevant
    to the question's keywords. Abstention becomes principled — the system
    says "no record of X" because X was explicitly tracked as a known
    unknown, not because retrieval came up empty.

    A consolidation tick runs every K ingests (programmatic, no LLM):
    surface contradictions (same key, conflicting values) and write them
    as derived records.
    """

    def __init__(
        self, llm: LLMClient, role: str = "agent_bulk",
        consolidate_every: int = 5,
        gap_detect_every: int = 1,
    ):
        super().__init__(llm, role)
        self.gaps: list[Gap] = []
        self._consolidate_every = consolidate_every
        self._gap_detect_every = gap_detect_every
        self._ingest_count = 0
        self.consolidations: list[dict[str, Any]] = []

    def ingest(self, doc: Doc) -> None:
        super().ingest(doc)
        self._check_gap_resolutions()
        self._ingest_count += 1
        if self._ingest_count % self._gap_detect_every == 0:
            self._detect_gaps(doc)
        if self._ingest_count % self._consolidate_every == 0:
            self._consolidate()

    def _check_gap_resolutions(self) -> None:
        for gap in self.gaps:
            if gap.resolved_by is not None:
                continue
            key = (gap.related_entity.lower(), gap.related_attribute.lower())
            t = self.hot_index.get(key)
            if t is not None:
                gap.resolved_by = t["source_doc"]
                gap.resolved_value = t["value"]

    def _detect_gaps(self, doc: Doc) -> None:
        self.detect_gaps_from_text(
            doc.text, source_id=doc.id, pub_date=doc.pub_date,
        )

    def detect_gaps_from_text(
        self, text: str, source_id: str = "", pub_date: str = "",
    ) -> int:
        """Public entry point: run gap detection on arbitrary text and append
        detected unknowns to self.gaps. Returns count of gaps added.

        Used by benchmark populate paths that bypass ingest() (e.g. E11/E11b
        which work from a triple-only corpus). This way gap-aware's
        gap-detection LLM call can still fire even though the substrate was
        populated via add_triple directly.
        """
        try:
            user_msg = (
                f"DOCUMENT (published {pub_date}):\n{text}\n\n"
                if pub_date
                else f"DOCUMENT:\n{text}\n\n"
            )
            user_msg += "List the unknowns this document raises, as JSON."
            resp = self.llm.chat(
                self.role,
                messages=[
                    {"role": "system", "content": _GAP_DETECT_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                max_tokens=400, temperature=0,
            )
            raw = resp.choices[0].message.content or "{}"
            import json
            data = json.loads(raw)
            added = 0
            for g in (data.get("gaps") or [])[:5]:
                if not isinstance(g, dict):
                    continue
                q = str(g.get("question", "")).strip()
                e = str(g.get("entity", "")).strip()
                a = str(g.get("attribute", "")).strip()
                if not (q and e and a):
                    continue
                self.gaps.append(Gap(
                    question=q, related_entity=e, related_attribute=a,
                    introduced_at=source_id,
                ))
                added += 1
            return added
        except Exception as e:
            print(f"[gap-aware] gap detection failed on {source_id}: {e}")
            return 0

    def _consolidate(self) -> None:
        """Surface contradictions: same (entity, attribute) with different
        values across the triple log. Programmatic, no LLM."""
        seen: dict[tuple[str, str], set[str]] = {}
        for t in self.triples:
            key = (t["entity"].lower(), t["attribute"].lower())
            seen.setdefault(key, set()).add(t["value"])
        for key, values in seen.items():
            if len(values) <= 1:
                continue
            already = any(
                c.get("kind") == "contradiction" and c.get("key") == key
                for c in self.consolidations
            )
            if already:
                continue
            self.consolidations.append({
                "kind": "contradiction",
                "key": key,
                "values": sorted(values),
                "noted_at_ingest_count": self._ingest_count,
            })

    def _format_open_gaps_for_query(self, question: str) -> str:
        kw = _question_keywords(question)
        relevant: list[Gap] = []
        for g in self.gaps:
            if g.resolved_by is not None:
                continue
            tokens = set(
                (g.related_entity.lower() + " " + g.related_attribute.lower())
                .split()
            )
            if tokens & kw:
                relevant.append(g)
        if not relevant:
            return ""
        lines = [
            "KNOWN UNKNOWNS (the system tracks these as missing — do NOT guess):"
        ]
        for g in relevant[:5]:
            lines.append(
                f"  - {g.question} "
                f"(about {g.related_entity}/{g.related_attribute}, "
                f"introduced from {g.introduced_at})"
            )
        return "\n".join(lines)

    def _current_query(
        self, question: str, as_of: str | None = None,
    ) -> str:
        cutoff = as_of or "9999-12-31T23:59:59"
        rows = [
            r for r in self.hot_index.values()
            if r["valid_from"] <= cutoff
        ]
        if not rows:
            return self._chunk_fallback(question)
        ctx = "\n".join(
            f"- ({r['entity']}, {r['attribute']}) = {r['value']}  "
            f"[updated {r['valid_from']}]"
            for r in sorted(rows, key=lambda x: x["valid_from"], reverse=True)
        )
        gaps_block = self._format_open_gaps_for_query(question)
        user_msg = f"CURRENT STATE:\n{ctx}\n\n"
        if gaps_block:
            user_msg += gaps_block + "\n\n"
        user_msg += f"QUESTION: {question}\nAnswer:"
        resp = self.llm.chat(
            self.role,
            messages=[
                {"role": "system", "content": _GAP_AWARE_QUERY_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=600, temperature=0.1,
        )
        answer = (resp.choices[0].message.content or "").strip()
        return self._maybe_chunk_fallback(question, answer)

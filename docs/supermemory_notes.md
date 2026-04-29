# Supermemory — Memory API for AI Agents

Source: https://github.com/supermemoryai/supermemory (MIT)

## Core claim

"The Memory API for the AI era." Hosted service + SDKs (npm/pip). Claims #1 on LongMemEval, LoCoMo, ConvoMem benchmarks (per project page). Also offers MCP server + plugins (Claude, Cursor, VS Code) + framework wrappers (Vercel AI, LangChain).

## Architecture — inferred from README

Storage substrate not explicitly documented. The system describes itself as "a single memory structure and ontology," suggesting a unified backing store (likely hybrid vector + structured metadata).

## Temporal handling — the differentiating axis

Supermemory advertises four distinct temporal behaviors:
1. **Automatic fact extraction** from conversations (similar to Mem0/Zep)
2. **User profile maintenance** (similar to Mem0's extract-consolidate pattern)
3. **Contradiction handling** — "'I moved to SF' supersedes 'I live in NYC'" → updates rather than duplicates. Overwrite semantics.
4. **Forgetting** — "forgets expired information." Explicit TTL/decay. This is distinct from:
   - **Mem0**: overwrites (no history retained)
   - **Zep**: accumulates with `valid_from` (history retained but marked stale by newer triples)
   - **Karpathy**: overwrites via LLM compile
   - **Our hybrid**: keeps all chunks forever (no forgetting)

The forgetting capability is the novel axis no other system in our comparison explicitly foregrounds.

## Retrieval

**Hybrid Search** — "RAG + Memory in a single query" — combines document chunk retrieval with structured profile lookup in one API call. Reported ~50ms for user profiles. This is architecturally what our `hybrid` tries to achieve via chunks-with-t_ref, except supermemory pairs it with a consolidated-profile structure alongside (closer to mem0 + chunks).

## Ingest

Multimodal:
- PDFs (via extraction pipeline)
- Images (OCR)
- Video (transcription)
- Code (AST-aware chunking)
- Text, conversations, URLs, HTML

## APIs

```javascript
client.add("text or URL or file")
client.profile()                       // user profile + optional search
client.search.memories("query")        // hybrid search
client.documents.uploadFile(...)
```

## Deployment

Both hosted service (https://app.supermemory.ai) and open-source library. MIT license permits commercial reuse.

## Target workloads

AI agents, personalization, knowledge management — for both consumer and developer audiences.

## Where it fits in our comparison

- **vs Mem0**: same consolidate-on-update semantics + adds explicit TTL + adds chunk fallback. Strict superset of mem0's pattern.
- **vs Zep**: gives up full temporal history (`valid_from` chain) in exchange for simpler retrieval + forgetting.
- **vs M-Flow**: no four-level cone hierarchy; memory is flat profile + chunks, not graph paths.
- **vs our Hybrid**: adds a consolidated profile layer on top of the chunk store. Our hybrid has chunks-only. The profile layer is what gives it stress-test resilience (E1 hypothesis: consolidation beats chunk-only retrieval for attribute churn).

## Open questions for comparison

- TTL mechanism: time-based, confidence-based, or importance-based? Unclear from README.
- Ingest LLM cost per doc: one extract + one embed? Or more?
- How the "hybrid search" arbitrates between profile hits and chunk hits when both have candidate answers.
- Whether "forgetting" is destructive (chunks deleted) or soft (marked expired, still retrievable with flags).

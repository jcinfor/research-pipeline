# M-Flow — Bio-Inspired Cognitive Memory Engine

Source: https://github.com/FlowElement-ai/m_flow (Apache-2.0)

## Core claim

"RAG matches chunks. GraphRAG structures context. M-flow scores evidence paths."

M-flow treats knowledge retrieval as **path-cost optimization** in a structured graph, not similarity matching. Queries anchor at matching granularity, then propagate evidence through the graph.

## Architecture — four-level inverted-cone graph

- **Episode** — bounded semantic events (incidents, decisions, workflows)
- **Facet** — one dimensional slice of an Episode (topical cross-section)
- **FacetPoint** — atomic assertions or precise facts
- **Entity** — named things (people, tools, metrics) linked across Episodes

Granularity-aligned retrieval: a precise query anchors on a FacetPoint, a broader one enters through Facets or Episode summaries.

## Temporal handling

- Episodic memory with time-bounded event clustering
- Session-level coreference resolution before indexing (pronouns resolved → preserves temporal context across multi-turn conversations)
- LongMemEval temporal benchmark: reports 93% accuracy

## How it differs

**vs RAG:** vector similarity → graph propagation paths. Returns Episode bundles with supporting chains, not ranked chunks.
**vs classic KGs:** edges carry semantic meaning (`edge_text`); the graph is an active scoring engine, not just storage.

## Benchmarks reported by project

- LoCoMo-10: 81.8% accuracy
- LongMemEval: 89% (vs competitors 50-79% in their reporting)

## APIs (from README)

Write:
```python
await m_flow.add("text or document")
await m_flow.memorize()  # graph construction + embedding
```

Read:
```python
results = await m_flow.query("question", query_type=EPISODIC)
```

CLI: `mflow add`, `mflow memorize`, `mflow search`, `mflow -ui`.

## Components

- Extraction pipeline (50+ file formats, coreference resolution)
- Knowledge graph builder (cone hierarchy with typed, weighted edges)
- Vector + graph adapters (LanceDB, Neo4j, PostgreSQL/pgvector, ChromaDB, KùzuDB, Pinecone)
- Episodic retrieval (graph-routed bundle search; primary mode)
- Procedural memory (extracts reusable abstract patterns)
- MCP server (exposes memory as MCP tools)
- Optional face-recognition integration (real-time partitioning by biometric identity)

## Use cases claimed

- Agentic AI: persistent memory for long-running agents
- Multi-person: face-aware identity partitioning
- Knowledge-intensive QA over ingested documents
- Conversational systems: temporal coherence via coreference resolution

## What we don't yet know (open questions for comparison)

- Write-time LLM cost per document (m_flow's "memorize" step does coreference + graph construction — how many LLM calls?)
- Latency breakdown for episodic retrieval vs pure vector KNN
- Behavior under explicit contradictions (the E4 scenario: earlier doc says Alice is CEO, later doc says Bob; does m_flow's episodic bundle return both, the latest, or let the caller resolve?)
- Operational complexity (graph DB + vector DB vs our single-store approach)
- Whether coreference pre-indexing assumes clean conversational input (may not fit noisy research corpora)
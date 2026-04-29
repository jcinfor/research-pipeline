# Zep: A Temporal Knowledge Graph for AI Agent Memory

*Sample paper for `rp demo`. Adapted from public Zep documentation and the temporal-knowledge-graph paper. Educational content; not the official Zep paper.*

## Abstract

Zep is a memory system for AI agents built on a temporal knowledge graph (TKG). Where flat-store systems like mem0 retain memories as natural-language statements and retrieve via vector similarity, Zep extracts entities and relationships into a graph and tracks bi-temporal validity (when a fact is true vs when it was recorded). The Zep team's published benchmarks claim strong performance on temporal-reasoning subsets of LoCoMo and LongMemEval.

## Architecture

The core of Zep is a Neo4j-backed graph (Graphiti) populated by an LLM-driven entity-resolution and relation-extraction pipeline. When a conversational turn arrives, Zep:

1. Extracts entities and relationships into the graph.
2. Annotates each fact with a `t_ref` (when the fact is asserted to be true) and a `t_recorded` (when ingestion happened).
3. Maintains a bi-temporal model so queries can ask "what did we know at date X?" or "what is the current state of Y?".

At query time, Zep walks the graph from query-relevant entities, scoring candidate facts by graph-path proximity and temporal precedence.

## Strengths

- **Temporal precision.** Bi-temporal annotation lets agents ask "as of January 1st, what was the user's role?" — a query that flat-store systems struggle with.
- **Cross-entity reasoning.** Graph traversal naturally surfaces connections ("the contract X mentions person Y who works at company Z").
- **Audit trail.** The TKG retains the trajectory of belief changes; nothing is silently overwritten.

## Weaknesses

- **High operational complexity.** Neo4j (or alternative graph store), a separate vector store for embeddings, and several LLM extraction passes per turn.
- **Context window pressure at scale.** When the relevant graph subgraph grows large, "expose all triples" approaches hit context limits — Zep's richer modes degrade or fail at 10k+ triples per project.
- **LLM extraction quality matters.** If entity resolution misclassifies an entity, downstream queries can't recover.

## Implementation note

The underlying [zep-graphiti](https://github.com/getzep/zep) server is open-source (Apache-2.0); the hosted Zep Cloud service is paid. The `research-pipeline` benchmarks include both an in-house `zep_lite` (kind-typed entries, time-anchored, simpler than the real product) and a `zep_real` wrapper around the cloud SDK.

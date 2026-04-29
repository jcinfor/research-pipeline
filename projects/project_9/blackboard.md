# Project 9 blackboard


## evidence (17)

- **[turn 0, system]** # Mem0: A Memory Layer for Personalized AI

*Sample paper for `rp demo`. Adapted from public mem0 documentation. Educational content; not the official mem0 paper.*
  *refs:* source=01_mem0_overview.md
- **[turn 0, system]** ## Abstract

Mem0 is an open-source memory layer for AI agents that extracts structured facts from conversations and stores them in a recency-weighted vector store. It targets long-running assistant scenarios where the user's stated preferences, decisions, and contextual details should persist across sessions. Published mem0 benchmarks on LoCoMo (ACL 2024) report 31% LLM-judge accuracy, making it the leading real-product memory system on that benchmark as of 2024.
  *refs:* source=01_mem0_overview.md, 2024
- **[turn 0, system]** ## Architecture

The mem0 pipeline ingests conversational turns and runs an LLM-driven extraction step to produce natural-language "memories" — short statements like *"User prefers concise responses"* or *"User reported a GPS issue with their Honda Civic on March 22, 2026"*. Each memory is embedded with a sentence-transformer and stored in a vector database (Qdrant by default). At query time, mem0 retrieves the top-K most similar memories via cosine similarity and passes them to the calling agent.

The mem0 design intentionally sacrifices structured-fact precision (entity-attribute-value triples) for natural-language flexibility. A memory like *"the user's car had a GPS issue in March"* is harder to query programmatically than the triple `(user, car_gps_status, broken@2026-03)` but is easier for an LLM to reason about in context.

## Strengths

- **Cross-session continuity.** Memories persist across conversations indexed by `user_id`. An agent can ask about facts from yesterday's session.
- **Natural-language fidelity.** Qualifying details (`"luxury Gucci handbag"` vs just `"handbag"`) are preserved verbatim.
- **Low operational complexity.** A vector DB plus an LLM is the entire stack.
  *refs:* source=01_mem0_overview.md, 2026
- **[turn 0, system]** ## Weaknesses

- **Multi-hop temporal reasoning is unreliable.** When questions require correlating two memories ("which event came first, the GPS issue or the service?"), retrieval may pull both but the answer LLM has to do the date arithmetic, which is error-prone.
- **State updates can lose history.** mem0's default policy on contradictory memories tends toward overwrite ("user now prefers verbose responses" replaces the earlier "user prefers concise responses"), losing the trajectory.
- **Aggregation is hard.** Questions like "how many times did the user mention their car?" require scanning all memories and counting via LLM, which doesn't always work.

## Implementation note

Mem0 is Apache-2.0 licensed. Real `mem0_real` integrations in `research-pipeline` benchmarks call the `mem0ai` Python SDK against the same vLLM/Ollama backend used by all other systems, with `MEM0_TELEMETRY=false` and an init-lock to serialize concurrent constructions.
  *refs:* source=01_mem0_overview.md
- **[turn 0, system]** # Zep: A Temporal Knowledge Graph for AI Agent Memory

*Sample paper for `rp demo`. Adapted from public Zep documentation and the temporal-knowledge-graph paper. Educational content; not the official Zep paper.*
  *refs:* source=02_zep_overview.md
- **[turn 0, system]** ## Abstract

Zep is a memory system for AI agents built on a temporal knowledge graph (TKG). Where flat-store systems like mem0 retain memories as natural-language statements and retrieve via vector similarity, Zep extracts entities and relationships into a graph and tracks bi-temporal validity (when a fact is true vs when it was recorded). The Zep team's published benchmarks claim strong performance on temporal-reasoning subsets of LoCoMo and LongMemEval.
  *refs:* source=02_zep_overview.md
- **[turn 0, system]** ## Architecture

The core of Zep is a Neo4j-backed graph (Graphiti) populated by an LLM-driven entity-resolution and relation-extraction pipeline. When a conversational turn arrives, Zep:

1. Extracts entities and relationships into the graph.
2. Annotates each fact with a `t_ref` (when the fact is asserted to be true) and a `t_recorded` (when ingestion happened).
3. Maintains a bi-temporal model so queries can ask "what did we know at date X?" or "what is the current state of Y?".

At query time, Zep walks the graph from query-relevant entities, scoring candidate facts by graph-path proximity and temporal precedence.
  *refs:* source=02_zep_overview.md
- **[turn 0, system]** ## Strengths

- **Temporal precision.** Bi-temporal annotation lets agents ask "as of January 1st, what was the user's role?" — a query that flat-store systems struggle with.
- **Cross-entity reasoning.** Graph traversal naturally surfaces connections ("the contract X mentions person Y who works at company Z").
- **Audit trail.** The TKG retains the trajectory of belief changes; nothing is silently overwritten.
  *refs:* source=02_zep_overview.md
- **[turn 0, system]** ## Weaknesses

- **High operational complexity.** Neo4j (or alternative graph store), a separate vector store for embeddings, and several LLM extraction passes per turn.
- **Context window pressure at scale.** When the relevant graph subgraph grows large, "expose all triples" approaches hit context limits — Zep's richer modes degrade or fail at 10k+ triples per project.
- **LLM extraction quality matters.** If entity resolution misclassifies an entity, downstream queries can't recover.

## Implementation note

The underlying [zep-graphiti](https://github.com/getzep/zep) server is open-source (Apache-2.0); the hosted Zep Cloud service is paid. The `research-pipeline` benchmarks include both an in-house `zep_lite` (kind-typed entries, time-anchored, simpler than the real product) and a `zep_real` wrapper around the cloud SDK.
  *refs:* source=02_zep_overview.md
- **[turn 0, system]** # A three-tier memory model for multi-agent research pipelines

*Sample paper for `rp demo`. Educational content describing the architecture this repo ships.*
  *refs:* source=03_three_tier_memory.md
- **[turn 0, system]** ## Abstract

Multi-agent research workflows have a temporal structure that flat-store memory systems handle awkwardly: agents work within a single project (short-lived, dense), the project produces lasting outputs (claims, hypotheses, experiments), and outputs accumulate across projects into a long-term knowledge base. We propose a three-tier memory model — **working / project / wiki** — that maps cleanly onto this structure and avoids the "one substrate fits all workloads" failure mode of mem0 and Zep.

## Tier 1 — Working memory

Per-turn, in-prompt only. Regenerated each turn by selecting the top-K relevant evidence, hypotheses-in-play, recent posts, and last-turn KPI feedback. No storage; the prompt is the unit of working memory. Bounded to ~2k tokens so each turn stays cheap.
  *refs:* source=03_three_tier_memory.md
- **[turn 0, system]** ## Tier 2 — Project blackboard

Per-project, kind-typed durable store. Every agent post becomes an `evidence` / `hypothesis` / `critique` / `experiment` / `result` / `draft` / `review` entry on the blackboard. Cosine-deduplicated on write (echo-clustered when similarity ≥ 0.85). Hypotheses carry a state machine: `proposed → supported / refuted / verified`.

The kind-typing is the key architectural choice. mem0's flat memories don't distinguish between "user reported a fact" and "user's hypothesis is that X causes Y" — both are just memory entries. The blackboard's `kind` column lets retrieval ask narrower questions ("what critiques target hypothesis #3?") that flat stores can't answer without LLM scaffolding.
  *refs:* source=03_three_tier_memory.md
- **[turn 0, system]** ## Tier 3 — User wiki

Cross-project long-term memory. Promoted from T2 on healthy runs (rubric ≥ floor). Karpathy LLM-Wiki structure (markdown-first, append-only, human-readable) plus a single capability stolen from Zep: a `t_ref` time-anchor column for "as-of" filters. No graph DB, no full bi-temporal model. The wiki compounds across projects on the same user, seeding new projects with relevant prior knowledge.
  *refs:* source=03_three_tier_memory.md
- **[turn 0, system]** ## Why three tiers

The temptation is to use one substrate at all timescales. Doing so forces tradeoffs that hurt every workload:

- A flat store optimized for quick recall (mem0) loses the structured-fact precision needed for cross-entity reasoning.
- A graph optimized for cross-entity reasoning (Zep) carries operational and latency cost that's wasteful for simple lookup.
- A document-pattern wiki optimized for compounding knowledge (Karpathy) lacks the per-turn working-memory pattern agents need.

Three tiers let each layer specialize. T1 is fast and ephemeral; T2 is structured and project-scoped; T3 is durable and queryable across time.
  *refs:* source=03_three_tier_memory.md
- **[turn 0, system]** ## Open questions

- Does this architecture transfer to non-research workloads (customer support, code agents)?
- At what wiki-size does the cosine-search retrieval start to underperform a graph approach?
- Is the kind taxonomy (evidence/hypothesis/critique/...) overfit to research workflows, or general?

These questions are exactly what `research-pipeline`'s agents would discuss. Run `rp project run <id>` and watch them.
  *refs:* source=03_three_tier_memory.md
- **[turn 0, agent 39]** Stop treating agent memory as a single vector bucket. Mem0’s recency-weighted flat-store [src #758] fails the temporal complexity of research. Use the three-tier model [src #767]: it separates dense project work from lasting claims, preventing semantic drift.
  *refs:* —
- **[turn 1, agent 39]** Stop equating "retrieval" with "reasoning." Mem0 [src #758] is a recency-weighted flat-store, while Zep [src #762] uses temporal knowledge graphs. Both risk failure in research workflows where temporal density varies [src #767]. Refutes [hyp #773].
  *refs:* —

## hypothesis (2)

- **[turn 0, agent 40]** The consensus is that structured graphs (Zep) or multi-tier hierarchies ([src #767]) are superior for research. Counter-hypothesis: For complex multi-agent synthesis, a high-entropy flat-store (Mem0) will outperform structured systems by preventing "semantic ossification."
  *refs:* —
- **[turn 1, agent 40]** I challenge [hyp #773]. Mem0's "high-entropy" flat-store [src #758] won't prevent ossification; it will cause catastrophic interference in multi-agent loops. Research requires the structural constraints of the three-tier model [src #767] to prevent semantic drift. Neutral.
  *refs:* —

## critique (2)

- **[turn 0, agent 41]** The blindspot is treating memory architecture as a retrieval problem rather than a state-consistency problem. You assume Mem0 [src #758] and Zep [src #761] are viable competitors, but their flat or graph structures may fail the temporal density required for research [src #767].
  *refs:* —
- **[turn 1, agent 41]** The claim that Mem0's high-entropy flat-store prevents "semantic ossification" [hyp #773] is an unproven assumption. Without a mechanism to resolve conflicting claims, Mem0's recency-weighting [src #758] likely induces "semantic drift" rather than synthesis.
  *refs:* —

## draft (1)

- **[turn 2, system]** ## Executive summary

This report evaluates three distinct agent-memory architectures for multi-agent research pipelines: Mem0 (a recency-weighted flat-store), Zep (a temporal knowledge graph), and a proposed three-tier model (working/project/wiki). The analysis focuses on the capacity of these systems to handle the temporal and structural complexities of research workflows, such as distinguishing between evidence, hypotheses, and critiques. Current findings suggest that while Mem0 offers high performance on standard benchmarks like LoCoMo, its flat-store nature may lack the structural constraints necessary to prevent semantic drift or interference in multi-agent loops.

## Evidence surfaced

*   **Mem0 Architecture:** An open-source memory layer that extracts structured facts from conversations and stores them in a recency-weighted vector store [source=01_mem0_overview.md]. It targets long-running assistant scenarios by persisting user preferences and decisions [source=01_mem0_overview.md]. On the LoCoMo (ACL 2024) benchmark, it reported 31% LLM-judge accuracy [source=01_mem0_overview.md].
*   **Zep Architecture:** A memory system built on a temporal knowledge graph (TKG) [source=02_zep_overview.md]. Unlike flat-store systems that use natural-language statements and vector similarity, Zep extracts entities and relationships into a graph and tracks bi-temporal validity (when a fact is true vs. when it was recorded) [source=02_zep_overview.md].
*   **Three-Tier Memory Model:** A specialized architecture for multi-agent research pipelines consisting of:
    *   **Tier 1 (Working Memory):** In-prompt, per-turn memory bounded to ~2k tokens, regenerated each turn via top-K relevant evidence and hypotheses [source=03_three_tier_memory.md].
    *   **Tier 2 (Project Blackboard):** A per-project, kind-typed durable store where agent posts are categorized (e.g., `evidence`, `hypothesis`, `critique`) [source=03_three_tier_memory.md]. It utilizes cosine-deduplication on write (echo-clustering at similarity ≥ 0.85) and a state machine for hypotheses [source=03_three_tier_memory.md].
    *   **Tier 3 (Wiki):** A long-term knowledge base for accumulating outputs across projects [source=03_three_tier_memory.md].

## Hypotheses advanced

**UNDER_TEST**
*   **#773:** Structured graphs (Zep) or multi-tier hierarchies are superior for research compared to flat-store models [inferred].

**PROPOSED**
*   **#776:** Mem0's "high-entropy" flat-store will not prevent ossification but will instead cause catastrophic interference in multi-agent loops, as research requires the structural constraints of the three-tier model to prevent semantic drift [agent_40].

## Critiques & open questions

**Critiques**
*   **#777:** The critic (agent_41) notes that the claim that Mem0's high-entropy flat-store prevents "semantic ossification" is an unproven assumption. Without a mechanism to resolve conflicting claims, Mem0's recency-weighting likely induces "semantic drift" rather than synthesis [inferred].

**Open Questions**
*   Does the three-tier architecture transfer effectively to non-research workloads such as customer support or code agents? [source=03_three_tier_memory.md]
*   At what specific wiki-size does cosine-search retrieval performance begin to underperform a graph-based approach? [source=03_three_tier_memory.md]
*   Is the "kind" taxonomy (evidence/hypothesis/critique/etc.) overfit to research workflows or is it generalizable? [source=03_three_tier_memory.md]

## Recommended next steps

1.  **Architecture Selection:** For a multi-agent research pipeline, the **three-tier memory model** is recommended due to its ability to use "kind-typing" (e.g., distinguishing a hypothesis from a fact), which allows for narrower, more effective retrieval than flat stores [source=03_three_tier_memory.md].
2.  **Primary Research Objective:** Investigate the strongest open question: the threshold at which cosine-search retrieval in a large-scale "wiki" tier begins to underperform the graph-based retrieval utilized by Zep [source=03_three_tier_memory.md].
  *refs:* —

## review (1)

- **[turn 2, system]** {"scores": {"coverage": 5, "evidence_density": 4, "rigor": 4, "clarity": 5, "actionability": 5}, "assessment": "The report provides a highly structured and clear comparison of memory architectures, successfully linking technical specifications to the specific needs of a research pipeline. It excels in identifying a concrete research gap regarding the scalability of vector search versus graph retrieval.", "revisions": ["Quantify the 'high-entropy' vs 'semantic ossification' debate by defining specific metrics for semantic drift or interference.", "Provide a brief comparative table of the three architectures across key dimensions (latency, complexity, retrieval type) to enhance quick digestibility.", "Elaborate on the 'kind-typing' mechanism to explain how it specifically mitigates the 'catastrophic interference' mentioned in hypothesis #776."]}
  *refs:* —

# Project 10 blackboard


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
- **[turn 0, agent 42]** Forget flat-stores; Mem0’s recency-weighting [src #781] fails the temporal complexity of research. Use the three-tier model [src #790]: it separates dense project tasks from lasting hypotheses. The big question: how do we automate the hierarchy transition?
  *refs:* —
- **[turn 1, agent 42]** The team is missing the structural mismatch. Mem0’s recency-weighting [src #781] and Zep’s TKG [src #785] are retrieval-centric, but research requires a distinction between transient task density and persistent outputs [src #790]. I refute [hyp #796]; simplicity fails temporal de
  *refs:* —

## hypothesis (2)

- **[turn 0, agent 43]** The consensus favors complex graphs or multi-tier hierarchies for research, but the most effective architecture may be the simplest. Hypothesis: Mem0’s flat-store [src #781] will outperform Zep’s TKG [src #785] and three-tier models [src #790] in multi-agent reasoning because hig
  *refs:* —
- **[turn 1, agent 43]** I refute [hyp #796]. While Mem0's recency-weighting [src #781] reduces retrieval noise, research requires relational depth. I propose: Zep’s TKG [src #785] will outperform the three-tier model [src #790] in *cross-project synthesis* due to entity-linkage density. Falsifiable if t
  *refs:* —

## critique (2)

- **[turn 0, agent 44]** The flaw is assuming "architectural superiority" can be judged on memory retrieval alone. You are ignoring the "Write-to-Read" bottleneck: Mem0/Zep focus on retrieval, but a research pipeline's failure point is the cognitive overhead of agents maintaining graph/wiki consistency [
  *refs:* —
- **[turn 1, agent 44]** [hyp #796] is unsupported. Claiming Mem0's flat-store [src #781] will outperform complex models ignores the structural mismatch: research is hierarchical, not just a stream of recency-weighted facts [src #790]. Simplicity is a liability if it lacks semantic depth.
  *refs:* —

## draft (1)

- **[turn 2, system]** ## Executive summary

This report evaluates three distinct agent-memory architectures for multi-agent research pipelines: the Mem0 flat-store, the Zep temporal knowledge graph (TKG), and a proposed three-tier memory model (working/project/wiki). The investigation focuses on whether a single-substrate approach can meet the structural demands of research workflows, which involve hierarchical data including evidence, hypotheses, and critiques. 

**Recommendation:** For a multi-agent research pipeline, the **three-tier memory model** is recommended. Unlike the flat-store approach of Mem0 or the entity-centric graph of Zep, the three-tier model's kind-typed "Project Blackboard" (Tier 2) specifically addresses the hierarchical and stateful nature of research (e.g., distinguishing between an `evidence` entry and a `hypothesis` entry), which is critical for preventing semantic dilution in complex workflows.

## Evidence surfaced

The following architectural profiles were identified:

*   **Mem0 (Flat-store):** An open-source memory layer that extracts structured facts from conversations and stores them in a recency-weighted vector store [source=01_mem0_overview.md, 2024]. It is designed for long-running assistant scenarios to persist user preferences and contextual details [source=01_mem0_overview.md]. It achieved 31% LLM-judge accuracy on LoCoMo benchmarks [source=01_mem0_overview.md].
*   **Zep (Temporal Knowledge Graph):** A system built on a temporal knowledge graph (TKG) that extracts entities and relationships into a graph structure [source=02_zep_overview.md]. Unlike flat-store systems that use natural-language statements and vector similarity, Zep tracks bi-temporal validity (when a fact is true vs. when it was recorded) [source=02_zep_overview.md].
*   **Three-Tier Memory Model:** A specialized architecture for multi-agent research pipelines designed to map onto the temporal structure of research [source=03_three_tier_memory.md].
    *   **Tier 1 (Working Memory):** In-prompt, per-turn memory bounded to ~2k tokens, consisting of top-K relevant evidence, hypotheses-in-play, and recent feedback [source=03_three_tier_memory.md].
    *   **Tier 2 (Project Blackboard):** A per-project, kind-typed durable store where entries are categorized (e.g., `evidence`, `hypothesis`, `critique`, `experiment`) [source=03_three_tier_memory.md]. It utilizes cosine-deduplication on write [source=03_three_tier_memory.md].
    *   **Tier 3 (Wiki):** A long-term knowledge base for accumulated outputs across projects [source=03_three_tier_memory.md].

## Hypotheses advanced

The debate regarding optimal architecture has centered on the trade-off between retrieval simplicity and relational depth.

*   **RESOLVED:**
    *   **#796 (REFUTED):** The initial hypothesis that the most effective architecture for research might be a simple, recency-weighted flat-store like Mem0 has been refuted. Critics argue that research is inherently hierarchical rather than a stream of recency-weighted facts, making simplicity a liability [source=03_three_tier_memory.md].
*   **UNDER_TEST:**
    *   **#799:** While the flat-store approach is rejected, a conflict remains regarding the superior complex architecture. The hypogen agent (agent_43) proposes that Zep’s TKG [source=02_zep_overview.md] will outperform the three-tier model [source=03_three_tier_memory.md] in *cross-project synthesis* due to higher entity-linkage density. This remains unverified.

## Critiques & open questions

**Critiques:**
*   **#800:** The critic agent (agent_44) argues that #796 is unsupported. The agent contends that claiming Mem0's flat-store [source=01_mem0_overview.md] will outperform complex models ignores a structural mismatch: research is hierarchical rather than a stream of recency-weighted facts [source=03_three_tier_memory.md]. Simplicity is viewed as a liability if it lacks semantic depth [INFERRED].

**Open Questions:**
*   **The Primary Open Question:** At what wiki-size does cosine-search retrieval begin to underperform a graph-based approach? [source=03_three_tier_memory.md]
*   Does the three-tier architecture transfer to non-research workloads such as customer support or code agents? [source=03_three_tier_memory.md]
*   Is the specific kind taxonomy (evidence/hypothesis/critique/...) overfit to research workflows or is it generalizable? [source=03_three_tier_memory.md]

## Recommended next steps

1.  **Comparative Benchmarking:** Conduct a direct comparison between the Zep TKG and the three-tier model specifically measuring "cross-project synthesis" capabilities to test the validity of hypothesis #799.
2.  **Scalability Testing:** Perform retrieval accuracy tests on the Tier 3 (Wiki) component to identify the specific scale at which cosine-search retrieval degrades compared to graph-based retrieval.
3.  **Taxonomy Validation:** Test the three-tier "kind-typing" system (evidence/hypothesis/critique) on a non-research dataset (e.g., customer support logs) to determine if the architecture is generalizable.
  *refs:* —

## review (1)

- **[turn 2, system]** {"scores": {"coverage": 5, "evidence_density": 4, "rigor": 4, "clarity": 5, "actionability": 5}, "assessment": "The report is highly structured and provides a clear, logical progression from architectural comparison to specific, testable hypotheses. It excels at distinguishing between the technical nuances of the three models and provides a decisive recommendation.", "revisions": ["Quantify the 'semantic dilution' mentioned in the recommendation by defining specific metrics (e.g., precision/recall decay) that the three-tier model aims to prevent.", "Provide more technical detail on the 'cosine-deduplication' mechanism in Tier 2 to clarify how it maintains integrity during high-frequency writes.", "Explicitly define the 'cross-project synthesis' metric to ensure the proposed benchmarking in the next steps is measurable and objective."]}
  *refs:* —

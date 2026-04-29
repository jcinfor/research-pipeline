# Project 9 — Research Synthesis

**Goal:** Compare three agent-memory architectures (mem0 flat-store, Zep graph, and the three-tier blackboard+wiki). Recommend one for a multi-agent research pipeline use case and identify the strongest open question.

**Agents:** `scout`, `hypogen`, `critic`

**KPI (rubric, 1-5):** citation_quality=5.0, novelty=4.0, relevance_to_goal=5.0, rigor=4.0


---

## Executive summary

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

---

## Reviewer Assessment

**Scores:** coverage=5, evidence_density=4, rigor=4, clarity=5, actionability=5


The report provides a highly structured and clear comparison of memory architectures, successfully linking technical specifications to the specific needs of a research pipeline. It excels in identifying a concrete research gap regarding the scalability of vector search versus graph retrieval.


**Suggested revisions:**

- Quantify the 'high-entropy' vs 'semantic ossification' debate by defining specific metrics for semantic drift or interference.

- Provide a brief comparative table of the three architectures across key dimensions (latency, complexity, retrieval type) to enhance quick digestibility.

- Elaborate on the 'kind-typing' mechanism to explain how it specifically mitigates the 'catastrophic interference' mentioned in hypothesis #776.

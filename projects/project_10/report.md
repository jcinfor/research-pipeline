# Project 10 — Research Synthesis

**Goal:** Compare three agent-memory architectures (mem0 flat-store, Zep graph, and the three-tier blackboard+wiki). Recommend one for a multi-agent research pipeline use case and identify the strongest open question.

**Agents:** `scout`, `hypogen`, `critic`

**KPI (rubric, 1-5):** citation_quality=5.0, novelty=4.0, relevance_to_goal=5.0, rigor=4.0


---

## Executive summary

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

---

## Reviewer Assessment

**Scores:** coverage=5, evidence_density=4, rigor=4, clarity=5, actionability=5


The report is highly structured and provides a clear, logical progression from architectural comparison to specific, testable hypotheses. It excels at distinguishing between the technical nuances of the three models and provides a decisive recommendation.


**Suggested revisions:**

- Quantify the 'semantic dilution' mentioned in the recommendation by defining specific metrics (e.g., precision/recall decay) that the three-tier model aims to prevent.

- Provide more technical detail on the 'cosine-deduplication' mechanism in Tier 2 to clarify how it maintains integrity during high-frequency writes.

- Explicitly define the 'cross-project synthesis' metric to ensure the proposed benchmarking in the next steps is measurable and objective.

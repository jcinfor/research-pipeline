# Project 2 — Research Synthesis

**Goal:** Evaluate whether a Zep-style temporal knowledge graph could replace our current blackboard + embedding-retrieval layer for agent memory, and where the tradeoffs fall.

**Agents:** `scout`, `hypogen`, `critic`

**KPI (rubric, 1-5):** citation_quality=5.0, novelty=4.0, relevance_to_goal=5.0, rigor=5.0


---

## Executive summary

This report evaluates the feasibility of replacing a current blackboard + embedding-retrieval memory layer with a Zep-style temporal knowledge graph (TKG) architecture. Zep utilizes a "Graphiti" engine to create a temporally-aware knowledge graph that synthesizes unstructured and structured data, maintaining a timeline of facts and relationships [zep-temporal-knowledge-graph.pdf]. While Zep demonstrates superior performance in Deep Memory Retrieval (DMR) benchmarks—achieving 94.8% compared to MemGPT's 93.4%—and significant latency reductions in LongMemEval (up to 90%) [zep-temporal-knowledge-graph.pdf], significant architectural risks have been identified. Specifically, the transition from retrieval-based memory to graph-based memory introduces a "Write-Amplification Trap," where the computational savings in retrieval are offset by the high overhead of continuous node creation and temporal maintenance [agent_5, agent_6].

## Evidence surfaced

*   **Performance Benchmarks:** Zep outperforms MemGPT in the Deep Memory Retrieval (DMR) benchmark [zep-temporal-knowledge-graph.pdf]. In the LongMemEval benchmark, which focuses on complex temporal reasoning, Zep showed accuracy improvements of up to 18.5% and reduced response latency by 90% [zep-temporal-knowledge-graph.pdf].
*   **Architectural Components:** The Zep architecture (Graphiti) employs a bi-temporal model consisting of a chronological timeline ($T$) and a transactional ingestion timeline ($T'$) [zep-temporal-knowledge-graph.pdf]. The graph is organized into three hierarchical tiers: an episode subgraph, a semantic entity subgraph, and a community subgraph [zep-temporal-knowledge-graph.pdf].
*   **Extraction Mechanisms:** Zep utilizes specific logic for entity and fact extraction, including duplicate detection to ensure node integrity and the extraction of relationships between distinct nodes with concise, all-caps relation types [zep-temporal-knowledge-graph.pdf].
*   **Performance Anomalies:** A notable decrease in performance was observed for single-session-assistant questions (17.7% for gpt-4o and 9.06% for gpt-4o-mini), suggesting limitations in certain conversational contexts [zep-temporal-knowledge-graph.pdf].

## Hypotheses advanced

### REFUTED
*   **[hyp #193] (Replacement Feasibility):** Refuted by multiple agents. The transition from a blackboard to a TKG is viewed as a category error because Zep's strengths lie in retrieval metrics (DMR) rather than replacing the semantic discovery capabilities of embeddings [agent_6]. Furthermore, the "Write-Amplification Trap" suggests that the cost of maintaining temporal consistency and node creation logic will exceed the latency saved during retrieval [agent_5].
*   **[hyp #207] (Truth-Anchoring):** Refuted. A TKG may fail to act as a "truth-anchor" if node creation relies on structured extraction; if an agent's intent shifts without explicit entity state changes, the TKG remains static while embeddings capture the semantic drift [agent_5, agent_6].
*   **[hyp #215] (Compute Optimization):** Refuted. The claim that temporal pruning reduces total compute is contested by the "Write-Amplification Trap," where compute saved on retrieval is redirected into high-frequency node creation and temporal extraction [agent_5, agent_6].

### UNDER_TEST
*   **[hyp #207] (Semantic Drift Detection):** Whether a TKG can detect "semantic drift" when a node's meaning evolves without a timestamped state change remains unverified [agent_5].

## Critiques & open questions

*   **The "Write-Amplification Trap":** A recurring critique from both the hypogen (agent_5) and critic (agent_6) archetypes is that the overhead of maintaining a dynamic, temporally-aware graph (node creation, duplicate detection, and temporal extraction) may create a net increase in compute and complexity compared to simple RAG/embedding-retrieval [agent_5, agent_6].
*   **Retrieval vs. State Management:** Critics argue that Zep's success in DMR benchmarks proves it is a superior *retrieval* mechanism, but does not prove it is a superior *state management* system [agent_6].
*   **The "Cold Start" Problem:** A KG cannot prune or manage information it has not yet structured, meaning it cannot replace the "discovery" aspect of an embedding-based blackboard for unstructured data [agent_6].
*   **Open Question:** How can the system handle "semantic drift" where an entity's meaning changes subtly without an explicit change in its structured attributes?

## Recommended next steps

*   **Conduct a Cost-Benefit Audit:** Perform a side-by-side comparison of total compute costs (Write + Read) for the current blackboard/embedding system versus the Zep/Graphiti architecture to validate or refute the "Write-Amplification Trap" [agent_5, agent_6].
*   **Test Semantic Drift Resilience:** Evaluate how the TKG handles entities that undergo gradual semantic evolution that does not trigger explicit state-change extractions [agent_5].
*   **Hybrid Implementation Research:** Investigate a hybrid model that uses embeddings for "semantic discovery" and the TKG for "structured temporal reasoning" to mitigate the "Cold Start" and "Semantic Drift" issues identified by critics [agent_6].

---

## Reviewer Assessment

**Scores:** coverage=4, evidence_density=5, rigor=4, clarity=5, actionability=4


The report provides a high-quality, structured analysis that effectively balances benchmark successes against significant architectural risks like the 'Write-Amplification Trap.' It moves beyond surface-level performance metrics to address fundamental systemic trade-offs.


**Suggested revisions:**

- Quantify the 'Write-Amplification Trap' by defining specific metrics (e.g., tokens per write vs. tokens per read) to move the hypothesis from qualitative to quantitative.

- Expand the 'Performance Anomalies' section to include a brief hypothesis on why single-session performance drops, as this is critical for determining if the TKG is suitable for short-term vs. long-term memory.

- Include a preliminary architectural diagram or flow comparison between the current 'Blackboard' and the proposed 'TKG' to better visualize the complexity shift.

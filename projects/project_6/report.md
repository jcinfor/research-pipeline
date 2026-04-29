# Project 6 — Research Synthesis

**Goal:** Compare Zep-style temporal knowledge graphs against Karpathy-style LLM Wiki as agent long-term memory architectures. Which is better suited for (a) compounding research knowledge across sessions, (b) precise temporal reasoning (relative dates, state changes), (c) robust retrieval under semantic drift, and (d) low-ops local-first deployment?

**Agents:** `hypogen`, `critic`, `experimenter`, `reviewer`, `reviewer`

**KPI (rubric, 1-5):** 


---

## Executive summary

This report evaluates two competing long-term memory architectures for LLM agents: Zep-style Temporal Knowledge Graphs (TKGs) and Karpathy-style "LLM Wikis." Zep utilizes the Graphiti engine to maintain a dynamic, temporally-aware knowledge graph $G = (N, E, \phi)$ that tracks entities, relationships, and their periods of validity [6]. In contrast, the LLM Wiki is formalized here as a **hierarchical RAG architecture** consisting of evolving, distilled document summaries and associated vector-indexed text chunks [source: llm-wiki.md].

Current evidence shows Zep outperforms MemGPT in Deep Memory Retrieval (DMR) benchmarks, achieving 94.8% accuracy [source: zep-temporal-knowledge-graph.pdf]. However, a significant theoretical debate exists regarding "semantic rot"—the risk that LLM-driven extraction errors will propagate through the rigid relational constraints of a KG, potentially causing structural collapse more rapidly than the additive, unstructured nature of a Wiki [hyp #309].

## Evidence surfaced

*   **Zep/Graphiti Architecture:** Zep employs a bi-temporal model consisting of a chronological timeline ($T$) and a transactional ingestion timeline ($T'$) [source: zep-temporal-knowledge-graph.pdf]. It utilizes a hierarchical subgraph structure: episode, semantic entity, and community subgraphs [source: zep-temporal-knowledge-graph.pdf].
*   **Temporal Reasoning:** Zep uses reference timestamps ($t_{ref}$) to extract relative or partial dates (e.g., "next Thursday") from unstructured messages, enabling precise temporal modeling [source: zep-temporal-knowledge-graph.pdf].
*   **Performance Benchmarks:** 
    *   **DMR (Deep Memory Retrieval):** Zep achieved 94.8% accuracy, outperforming MemGPT's 93.4% [source: zep-temporal-knowledge-graph.pdf].
    *   **LongMemEval:** Zep demonstrated accuracy improvements of up to 18.5% and a 90% reduction in response latency compared to baseline implementations [source: zep-temporal-knowledge-graph.pdf].
*   **LLM Wiki Architecture (Formalized):** Defined as a hierarchical RAG system where LLMs distill conversation history into structured, evolving document summaries (the "Wiki pages") supported by a flat vector store of raw text chunks [source: llm-wiki.md].
*   **Deployment Profile:** Current evidence focuses on retrieval accuracy and latency; however, Zep is positioned as a production-grade memory layer service [source: zep-temporal-knowledge-graph.pdf], whereas the Wiki pattern is a conceptual framework for personal knowledge bases [source: llm-wiki.md].

## Hypotheses advanced

*   **[UNDER_TEST] Hyp #309 (Semantic Rot vs. Structural Rigidity):** The hypogen agent proposes that Zep-style TKGs are vulnerable to "semantic rot," where drifting LLM representations poison the graph with hallucinated temporal links, causing the entire temporal chain to collapse [hyp #309]. Conversely, the critic agent argues that a TKG may be more resilient because it allows for "surgical" edge pruning and targeted updates, whereas a Wiki requires rewriting entire pages to correct facts [hyp #309].
*   **[UNDER_TEST] Write-time Drift Tax:** This hypothesis posits that both architectures incur an "LLM-drift tax" during the extraction phase. This tax is quantified by the **Extraction Error Rate (EER)**: the frequency of hallucinated entities or incorrect temporal attributes per 100 ingestion cycles. The differentiator is whether Zep's $t_{ref}$ can be used to repair drifted edges during query-time [hyp #309].

## Critiques & open questions

*   **Baseline Definition:** The critic agent notes that the "LLM Wiki" baseline was previously undefined; it is now formalized as a hierarchical RAG system to ensure the comparison with Zep is non-falsifiable [agent_23].
*   **Error Propagation vs. Factual Error:** A critique suggests that the debate conflates "factual error" with "structural collapse." It remains unclear if the failure mode of a KG is its rigid structure or the underlying drift of the source LLM [agent_23].
*   **Mechanism of Correction:** An open question remains whether the primary differentiator is "structure vs. unstructured" or the specific mechanism of error correction (e.g., surgical edge deletion in TKGs vs. re-synthesis in Wikis) [agent_23].
*   **Local-First Deployment:** A significant gap exists in evaluating "low-ops local-first deployment." While Zep is a production service, the operational overhead of maintaining a dynamic TKG locally versus a simpler hierarchical RAG (Wiki) remains unquantified.

## Recommended next steps

The experimenter agent proposes several protocols to resolve the current impasse:

1.  **Temporal Entropy Benchmark:** Compare Zep's TKG against a "Wiki" defined as a hierarchical RAG system (summaries + vector docs) by injecting 100 state-flips and measuring retrieval accuracy [agent_24].
2.  **Closed-Loop Temporal Decay Protocol:** Create a synthetic environment with an evolving world state and inject a "drift signal" by altering the LLM's system prompt every 50 cycles. The decisive metric will be the "Relational Integrity Delta"—the divergence between perceived state and ground truth after 1,000 cycles [agent_24].
3.  **State-Correction Stress Test:** Inject a false fact via LLM-extraction and then issue a correction to measure "Recovery Latency" (the number of cycles required to purge the error) [agent_24].

---

## Reviewer Assessment

**Scores:** coverage=4, evidence_density=5, rigor=4, clarity=4, actionability=4


The report provides a high-quality, technically dense comparison of two distinct memory architectures, utilizing formal definitions and specific performance metrics to ground the debate. While it excels in theoretical framing, it lacks empirical data regarding the 'low-ops local-first' requirement specified in the goal.


**Suggested revisions:**

- Quantify the operational complexity (CPU/RAM/Disk overhead) for both architectures to address the 'low-ops local-first' dimension of the research goal.

- Explicitly map the findings back to the four specific sub-goals (a, b, c, d) in a summary table to improve immediate utility.

- Provide a more granular distinction between 'semantic rot' and 'structural collapse' to resolve the critique regarding conflated failure modes.

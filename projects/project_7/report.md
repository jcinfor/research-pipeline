# Project 7 — Research Synthesis

**Goal:** Compare FIVE agent-memory architectures on temporal fidelity, write-time cost, read-time cost, and operational fit for frequent-write blackboard workloads: (1) our Karpathy+Zep hybrid, (2) Zep temporal knowledge graph, (3) Mem0 (extract-consolidate), (4) M-Flow (four-level Episode/Facet/FacetPoint/Entity cone), (5) Supermemory (consolidated profile + chunk fallback + explicit forgetting/TTL). EMPIRICAL CONTEXT from E1 benchmark (2026-04-24): hybrid_flat 1/3, hybrid_recency 0/3 (worse than flat — global recency window evicts older-but-still-current entity data when streams interleave), zep_lite 3/3 at 101s ingest, mem0_lite 3/3 at 53s ingest. Supermemory is being added to E1 now. Focus specifically on: (a) what supermemory's TTL/forgetting adds that mem0 lacks, (b) whether supermemory's consolidated-profile + chunk-fallback is the strict superset pattern we should adopt for our hybrid, (c) where m_flow's graph hierarchy is still needed given that mem0/supermemory's flat consolidation already gives 3/3 fidelity.

**Agents:** `hypogen`, `hypogen`, `critic`, `critic`, `reviewer`, `reviewer`

**KPI (rubric, 1-5):** 


---

## Executive summary

This report evaluates five agent-memory architectures—Karpathy+Zep hybrid, Zep temporal knowledge graph, Mem0 (extract-consolidate), M-Flow (four-level hierarchy), and Supermemory (consolidated profile + chunk fallback + TTL)—against the requirements of frequent-write "blackboard" workloads. Empirical data from the E1 benchmark (2026-04-24) indicates that while Mem0 and Zep-lite achieve 3/3 temporal fidelity, the current Karpathy+Zep hybrid suffers from `hybrid_recency` failures (0/3), where global recency windows evict critical interleaved entity data. The analysis focuses on whether Supermemory’s architecture represents a "strict superset" of Mem0 or introduces new temporal liabilities via its TTL and consolidation mechanisms.

## Evidence surfaced

### Architectural Comparisons
*   **Supermemory vs. Mem0**: Supermemory is characterized as a "strict superset" of Mem0's extract-consolidate pattern, adding explicit TTL/forgetting and a chunk fallback mechanism alongside the consolidated profile (supermemory_notes.md).
*   **Supermemory vs. Zep**: Supermemory trades Zep’s full temporal history (`valid_from` chains) for simpler retrieval and explicit forgetting (supermemory_notes.md).
*   **Supermemory vs. M-Flow**: Unlike M-Flow’s four-level Episode/Facet/FacetPoint/Entity cone hierarchy, Supermemory utilizes a flatter structure consisting of a consolidated profile paired with a chunk fallback (supermemory_notes.md).
*   **Supermemory vs. Current Hybrid**: The current research-pipeline hybrid utilizes a three-tier approach with chunks tagged with `t_ref` for cosine retrieval (agent-memory-architecture.md). Supermemory adds a consolidated profile layer on top of this chunk store (supermemory_notes.md).

### Performance & Operational Metrics
*   **Temporal Fidelity**: Mem0-lite and Zep-lite both achieved 3/3 fidelity at specific ingest rates (53s and 101s respectively) (E1 benchmark context).
*   **Zep Operational Overhead**: Zep’s memory graph is noted for extreme token inefficiency (600k+ tokens) and significant operational latency, where immediate retrieval often fails until background asynchronous LLM calls complete (mem0.pdf).
*   **Mem0 Efficiency**: Mem0 achieves high responsiveness, with graph construction completing in under a minute, and maintains a significantly lower token footprint (approx. 7k tokens per conversation) compared to Zep (mem0.pdf).

## Hypotheses advanced

### [STATE: REFUTED]
*   **The "Strict Superset" Utility (agent_27, agent_28, agent_29, agent_30)**: The claim that Supermemory is a strict superset of Mem0 is refuted as a "structural illusion" or "lie of omission." While it adds features like TTL, it lacks the structured lineage of M-Flow or the `valid_from` temporal chains of Zep, potentially making it a different trade-off rather than an upgrade (supermemory_notes.md; agent_27; agent_29).

### [STATE: UNDER_TEST]
*   **Profile-Drift Collapse (agent_28)**: In blackboard workloads, frequent writes may cause Supermemory to suffer "Profile-Drift Collapse," where rapid consolidation erodes structural depth (supermemory_notes.md).
*   **The Consistency-Intelligence Trade-off (agent_27)**: For high-velocity workloads, the "intelligence" of a memory system (Zep/M-Flow) is inversely proportional to its temporal fidelity due to the "consistency lag" between observation and structural integration (agent_27).
*   **TTL as a High-Pass Filter (agent_27, agent_28)**: Supermemory’s TTL may act as a high-pass filter that creates "knowledge gaps" by pruning context required for resolution, potentially exacerbating the `hybrid_recency` 0/3 failure (supermemory_notes.md; agent_27).
*   **Semantic Gap/Collision (agent_28, agent_30)**: The split between profile and chunk fallback may create a "semantic gap" or "semantic collision" where the system deletes chunks necessary to resolve interleaved stream drift (supermemory_notes.md; agent_30).

## Critiques & open questions

### Critiques
*   **Structural vs. Temporal Latency (agent_29)**: Critics argue that the "lag" observed in complex architectures (Zep/M-Flow) may be a failure of retrieval logic rather than architecture. A system could maintain perfect fidelity if "in-flight" raw chunks are treated as a first-class fallback (agent_29).
*   **Feature Count vs. Architecture (agent_30)**: There is a critique against conflating "feature count" with "architectural superiority," noting that Supermemory's extra layers may function as a "latency tax" rather than an upgrade (agent_30).
*   **The "Visibility Lag" (agent_29)**: Even with low-latency vector retrieval, if index updates are decoupled from writes, a "visibility lag" remains where facts exist in the buffer but are invisible to `as_of` filters (agent_29).

### Open Questions
*   **M-Flow Necessity**: Given that Mem0/Supermemory's flat consolidation achieves 3/3 fidelity, is M-Flow's hierarchical graph still required for specific relational tasks? (Goal context).
*   **Write-time Cost**: What is the specific LLM cost per document for M-Flow's "memorize" step involving coreference and graph construction? (m_flow_notes.md).
*   **Scaling Overhead**: Does the overhead of reconciling a consolidated profile against a pruned chunk set scale exponentially during high-frequency writes? (agent_29).

## Recommended next steps

1.  **Implement Tiered "Hot/Cold" Architecture**: Explore a model where the current hybrid handles the "hot" unrefined stream (immediate availability) while a more structured system (like M-Flow) handles the "cold" structured archive to mitigate the consistency-availability trade-off (agent_29).
2.  **Quantify the "Stale Window"**: Develop a metric to decouple write-time LLM cost from retrieval-time graph traversal complexity to determine if structural depth survives high-velocity bursts (agent_29).
3.  **Stress-test Supermemory TTL**: Validate whether Supermemory's TTL/forgetting mechanism triggers the same 0/3 failure seen in `hybrid_recency` by monitoring for "knowledge gaps" in interleaved streams.
4.  **Evaluate Profile+Chunk Fallback**: Determine if the Supermemory pattern is a viable "superset" for the current hybrid or if it introduces a "resolution trap" that collapses structural depth (agent_27).

---

## Reviewer Assessment

**Scores:** coverage=5, evidence_density=4, rigor=5, clarity=4, actionability=5


An exceptionally high-quality technical report that successfully moves beyond feature comparison into deep architectural trade-off analysis, specifically regarding temporal fidelity and consistency lag. The distinction between 'structural illusion' and actual architectural upgrades provides significant value for decision-making.


**Suggested revisions:**

- Quantify the 'semantic gap' between profile and chunk fallback with a specific retrieval-error metric to move the 'Under Test' hypothesis toward a 'Refuted/Confirmed' state.

- Explicitly define the 'blackboard workload' parameters (e.g., writes per second, token density) to provide a baseline for the 'Write-time Cost' open question.

- Include a brief comparative table of the five architectures across the four primary axes (temporal fidelity, write cost, read cost, operational fit) for immediate executive reference.

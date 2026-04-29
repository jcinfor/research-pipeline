# Project 8 — Research Synthesis

**Goal:** Project 8 — innovate in agent memory by addressing the primary issue of existing solutions. EMPIRICAL GROUNDING from E1-E7-XL (docs/agent-memory-benchmarks.md): at 26B extractor with 256K context over 124 conversational turns, 5 of 7 systems converge to 11/12 (~92%) — architectural differences NEARLY VANISH at frontier-scale extraction. But specific failures reveal the real structural issue: zep_lite failed distant pronouns (latest-per-key collapse hid them); zep_rich failed 'current value' queries (exposing all 200+ triples confused the LLM); mem0 has a hard ceiling on cross-entity temporal queries (E6: 0/3) because overwrite destroys history; ALL systems hallucinate 'no' when the correct answer is 'unknown' (no first-class uncertainty). PROPOSED PRIMARY ISSUE: no memory system adapts its retrieval strategy to query intent. Storage-query coupling is fixed at design time; query intents vary (current / historical / cross-entity / existence / summary) and each demands a different strategy. PROPOSED INNOVATION: (1) append-only substrate that persists raw turns + triples + chunks side-by-side; (2) LLM-based query-intent classifier that routes queries to the right retrieval strategy; (3) uncertainty metadata surfaced by construction (last-update timestamp, contradiction count, confirmation count) so answers can calibrate 'I don't know' vs 'as of last check, X'. TASK: (a) stress-test this framing — is 'storage-query coupling' genuinely THE primary issue, or are we missing a deeper one? (b) identify at least ONE testable prediction that distinguishes this design from existing systems (a query our E1-E7-XL suite cannot answer well but a dynamic-routing system should); (c) propose an experimental protocol that would falsify or confirm the design.

**Agents:** `critic`, `critic`, `hypogen`, `hypogen`, `experimenter`, `reviewer`

**KPI (rubric, 1-5):** 


---

## Executive summary

Project 8 aims to innovate agent memory by addressing the "storage-query coupling" issue, where fixed retrieval strategies fail to adapt to varying query intents (e.g., current vs. historical vs. cross-entity). The proposed solution involves an append-only substrate (raw turns, triples, and chunks), an LLM-based query-intent classifier for dynamic routing, and uncertainty metadata (contradiction/confirmation counts) to enable calibrated "I don't know" responses. 

Empirical data from E1-E7-XL benchmarks indicates that while most extraction-based systems converge to ~92% accuracy at scale, specific structural failures persist: Mem0 suffers from a "hard ceiling" on cross-entity temporal queries (0/3 on E6) due to state destruction via overwrite, and various systems hallucinate "no" when the correct answer is "unknown."

## Evidence surfaced

*   **Convergence at Scale:** At 26B extractor with 256K context over 124 turns, 5 of 7 systems converge to ~92% accuracy; architectural differences nearly vanish at frontier-scale extraction (agent_None).
*   **Mem0 Architectural Failures:** 
    *   Mem0 exhibits a hard ceiling on cross-entity temporal queries (E6: 0/3) because its overwrite mechanism destroys history (agent_None).
    *   Mem0 suffers from cross-thread attribute-key collisions (e.g., the "approach" attribute being reused, causing newer data to evict older) (agent_None).
    *   Mem0 fails on preference evolution (e.g., returning "mutex or event-queue" when a user reverts to a previous state) (agent_None).
*   **System-Specific Weaknesses:**
    *   **Zep Lite:** Failed distant pronouns due to "latest-per-key collapse" (agent_None).
    *   **Zep Rich:** Failed "current value" queries by exposing too many triples (200+), confusing the LLM (agent_None).
    *   **M-flow:** Faces disambiguation burdens in its "cone" when multiple attribute-facets match a pronoun (agent_None).
    *   **Supermemory:** Hallucinates "no" instead of "unknown" on queries regarding non-existent updates (agent_None).
*   **Retrieval Limitations:** Supermemory's chunk fallback failed at cosine-only retrieval; it requires explicit temporal retrieval (chunks near timestamp T) (agent_None).

## Hypotheses advanced

*   **[REFUTED] Storage-query coupling as the primary bottleneck:** Multiple critics (agent_33, agent_34, agent_35, agent_36) argue that if extraction-based systems already converge at 9/10, the bottleneck is not the *routing* of queries, but the *loss of temporal fidelity* and *state-resolution* during extraction (agent_33, agent_34, agent_36).
*   **[UNDER_TEST] Intent-routing as a complete solution:** Critics suggest routing is a "band-aid" or "secondary optimization" if the underlying substrate is lossy. Routing to a broken index (where history has been overwritten) still yields broken results (agent_33, agent_35, agent_36).
*   **[SUPPORTED/REFINED] Append-only substrate requirement:** There is consensus that an append-only substrate is a necessary prerequisite to prevent the "destruction of state" seen in Mem0 (agent_35, agent_37).
*   **[NEW] MVCC/Temporal-Logical Log:** Hypotheses suggest the innovation should focus on treating memory as a temporal log with Multi-Version Concurrency Control (MVCC) to resolve conflicting states, rather than just a semantic search index (agent_35, agent_36, agent_37).

## Critiques & open questions

*   **Category Error:** Critics argue that "storage-query coupling" assumes the problem is *access*, whereas the actual problem is *entropy* and the loss of the "delta" during extraction (agent_33).
*   **Routing to a Void:** A major critique is that intent-routing is moot if the substrate lacks the ability to reconstruct state. If the extraction process collapses temporal state into a single "current" value, the router merely chooses which way to fail (agent_33, agent_34).
*   **Semantic Drift:** Even with an append-only log, if the intent classifier misinterprets a "current state" query as a "historical summary" query, it may retrieve a coherent but obsolete snapshot (agent_34).
*   **Open Question:** Is the primary issue "access" (routing) or "retention" (the substrate)?

## Recommended next steps

*   **Shift Focus to State-Resolution:** Pivot the design from "intent-routing" to "temporal-logical state reconstruction" using an append-only substrate (agent_36, agent_37).
*   **Implement MVCC:** Treat the append-only substrate as a Multi-Version Concurrency Control system to allow the retrieval of specific temporal snapshots (agent_35, agent_37).
*   **Conflict-Resolution Stress Test:** Design an experimental protocol that injects 10 contradictory attribute updates and evaluates if the system can reconstruct the correct state sequence (agent_37).
*   **Uncertainty Metadata Integration:** Proceed with the proposal to surface contradiction counts and confirmation counts to address the "hallucination of certainty" (agent_35).

---

## Reviewer Assessment

**Scores:** coverage=5, evidence_density=5, rigor=4, clarity=4, actionability=5


This is an exceptional research report that effectively uses empirical failure modes to pivot from a flawed initial hypothesis to a more robust architectural requirement. The transition from 'intent-routing' to 'temporal-logical state reconstruction' demonstrates high-level critical thinking and alignment with the provided benchmark data.


**Suggested revisions:**

- Explicitly define the schema for the 'uncertainty metadata' to ensure it can be mathematically integrated into the LLM's reasoning process rather than just being passive text.

- Strengthen the 'Experimental Protocol' section by defining the specific metrics (e.g., Temporal Reconstruction Accuracy) that will be used to compare the MVCC approach against the baseline extraction models.

- Clarify the relationship between the LLM-based intent classifier and the MVCC substrate to ensure the classifier is not seen as a replacement for, but a controller of, the temporal log.

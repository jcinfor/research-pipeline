# Top Risks

## R1: Classifier-Induced Retrieval Failure (Routing Error)
- Likelihood: high
- Impact: high
- Mitigation: Implement a "fallback-to-semantic" mechanism where if the intent classifier's confidence is below a threshold, the system defaults to a standard hybrid-flat cosine search.
- Evidence: [hyp #717]

## R2: Substrate Entropy and Semantic Decay
- Likelihood: medium
- Impact: high
- Mitigation: Move beyond simple append-only logs to a Multi-Version Concurrency Control (MVCC) model that explicitly manages state-resolution and conflict-handling during the write phase.
- Evidence: [critique #716], [critique #734]

## R3: Extraction-Driven State Destruction
- Likelihood: high
- Impact: high
- Mitigation: Ensure the "append-only substrate" is the primary source of truth for reconstruction, treating extracted triples only as an indexed view rather than the definitive state to prevent Mem0-style overwrites.
- Evidence: [critique #700], [critique #711]

## R4: Latency Overhead of Multi-Stage Processing
- Likelihood: medium
- Impact: medium
- Mitigation: Use a highly optimized, small-parameter model (e.g., a fine-tuned SLM) for the intent classifier to minimize the "routing tax" before retrieval begins.
- Evidence: [src #556] (noting existing hybrid systems prioritize cost/speed)

## R5: Intent Misalignment in Complex Queries
- Likelihood: medium
- Impact: medium
- Mitigation: Design the query-intent classifier to support multi-label intents (e.g., a query that is both "temporal" and "cross-entity") to prevent the system from discarding necessary retrieval modalities.
- Evidence: [hyp #701], [critique #706]
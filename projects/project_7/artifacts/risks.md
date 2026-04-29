# Top Risks

## R1: Semantic Smoothing via Consolidation
- Likelihood: high
- Impact: high
- Mitigation: Implement a "high-frequency bypass" that preserves raw, un-consolidated chunks for recent temporal windows, preventing the LLM from averaging out transient state changes into a single static profile.
- Evidence: [hyp #458], [hyp #478]

## R2: Catastrophic Forgetting via TTL-driven Entropy
- Likelihood: medium
- Impact: high
- Mitigation: Replace simple TTL (Time-To-Live) with "importance-weighted decay," where the decay rate is a function of entity access frequency and semantic volatility rather than just wall-clock time.
- Evidence: [hyp #488], [hyp #496], [id #502]

## R3: Index-Write Race Conditions (Consistency Lag)
- Likelihood: high
- Impact: medium
- Mitigation: Adopt a "Read-Your-Writes" consistency model where the retrieval engine queries both the primary index and a high-speed, un-indexed "hot buffer" of recent writes to bridge the structural integration gap.
- Evidence: [hyp #470], [hyp #473]

## R4: Retrieval-Induced Hallucination (False Voids)
- Likelihood: medium
- Impact: high
- Mitigation: Implement "structural completeness checks" during retrieval; if a query hits a partially-indexed graph or a fragmented profile, the system must trigger a fallback to raw chunk retrieval rather than returning a partial/incorrect answer.
- Evidence: [hyp #477]

## R5: Latency Wall in High-Density Workloads
- Likelihood: high
- Impact: medium
- Mitigation: Decouple the extraction/indexing pipeline from the write path using an asynchronous, priority-queued worker pattern, ensuring that M-Flow's coreference indexing or Zep's graph construction does not block the blackboard ingest.
- Evidence: [hyp #463], [critique #471]
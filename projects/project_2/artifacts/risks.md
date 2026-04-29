# Top Risks

## R1: Write-Amplification Latency Trap
- Likelihood: high
- Impact: high
- Mitigation: Implement an asynchronous, tiered ingestion pipeline where raw episodic data is immediately available via vector search, while the heavy temporal KG construction and hyper-edge extraction occur as a background process.
- Evidence: [hyp #202], [crit #194]

## R2: Semantic Discovery Blind Spots
- Likelihood: medium
- Impact: high
- Mitigation: Maintain a hybrid retrieval architecture where the KG handles state and temporal logic, but a lightweight embedding-retrieval layer remains active to capture "semantic drift" and nodes not yet structured into the graph.
- Evidence: [hyp #196], [hyp #199], [crit #200]

## R3: State Explosion and Consistency Overhead
- Likelihood: high
- Impact: medium
- Mitigation: Define strict TTL (Time-to-Live) policies and pruning heuristics for the semantic entity subgraph to prevent the complexity of maintaining temporal consistency from scaling linearly with conversation length.
- Evidence: [crit #194], [crit #202]

## R4: The KG "Cold Start" Problem
- Likelihood: medium
- Impact: medium
- Mitigation: Use the existing blackboard/embedding layer as a "buffer" or "staging area" for new information, only promoting data to the Zep-style KG once sufficient context (e.g., $n=4$ messages) is available to ensure reliable entity extraction.
- Evidence: [crit #203], [src #74]

## R5: Metric Misalignment (DMR vs. Operational Latency)
- Likelihood: medium
- Impact: medium
- Mitigation: Supplement Deep Memory Retrieval (DMR) benchmarks with end-to-end system latency audits and cost-per-query evaluations before decommissioning the blackboard layer.
- Evidence: [crit #197], [crit #200]
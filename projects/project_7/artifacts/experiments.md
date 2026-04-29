# Proposed Verification Experiments

## E1 verifies [hyp #457]
- Protocol: Subject the five architectures to a "High-Velocity Contradiction Stream." Feed a continuous stream of 500+ rapid-fire blackboard updates where entity attributes are frequently toggled (e.g., "Sensor A: Status=Active" followed 2 seconds later by "Sensor A: Status=Error"). Measure the delta between the ground truth state and the retrieved state via LLM-based extraction.
- Minimum viable test: A script injecting 100 state-toggles per minute into all five architectures and querying the current state of the specific entity every 5 seconds.
- Predicted outcome if hypothesis holds: Mem0 and Zep will show high "semantic drift" (returning a hallucinated average or the wrong state) due to LLM consolidation errors, while the hybrid_flat architecture will maintain 100% accuracy despite lower "intelligence."
- Predicted outcome if hypothesis fails: All architectures maintain high fidelity, or Mem0/Zep outperform flat architectures by correctly resolving the latest state through intelligent consolidation.
- Estimated cost/complexity: medium
- Rationale: This directly tests if the "intelligence" (extraction/consolidation) of Mem0/Zep is actually a source of corruption (hallucination) in high-velocity environments.

## E2 verifies [hyp #463]
- Protocol: Execute a "Density Stress Test." Increase the number of unique entities being written to the blackboard per second (from 1 to 100) while measuring the end-to-end write latency for M-Flow.
- Minimum viable test: Measure the time from "write command issued" to "index ready for retrieval" for M-Flow as the number of concurrent entities in the session scales.
- Predicted outcome if hypothesis holds: M-Flow's write latency will scale super-linearly with entity density, creating a "latency wall" that exceeds the blackboard's update frequency.
- Predicted outcome if hypothesis fails: M-Flow's write latency remains constant or scales linearly, proving it can handle high-density workloads.
- Estimated cost/complexity: low
- Rationale: This isolates whether M-Flow's coreference pre-indexing is an operational blocker for real-time blackboard workloads.

## E3 verifies [hyp #469]
- Protocol: Perform a "Retrieval Complexity Benchmark." Using a standardized set of complex, multi-hop queries (e.g., "Find all entities affected by the change in Sensor A's status"), measure the latency and token cost of retrieval across the flat KNN (Hybrid) vs. the graph-based paths (M-Flow).
- Minimum viable test: A benchmark comparing the milliseconds and LLM tokens required to resolve a 3-hop relationship in M-Flow vs. a single vector search in the Hybrid architecture.
- Predicted outcome if hypothesis holds: M-Flow will incur a significant "Read-Time Tax" in latency and cost compared to the Hybrid's flat retrieval.
- Predicted outcome if hypothesis fails: M-Flow's structured retrieval is as fast or faster than flat KNN due to more precise pruning of the search space.
- Estimated cost/complexity: medium
- Rationale: This tests if the structural benefits of M-Flow are offset by the computational overhead of traversing its hierarchy during retrieval.

## E4 verifies [hyp #470]
- Protocol: Conduct a "Consistency Lag Audit." In a high-velocity write scenario, perform "Read-After-Write" tests where a query is issued immediately (within <10ms) after a write command is sent to M-Flow and Zep.
- Minimum viable test: A loop that writes a new key-value pair and immediately attempts to retrieve it, recording the percentage of "stale" reads (where the old value is returned).
- Predicted outcome if hypothesis holds: M-Flow and Zep will show a high rate of stale reads due to the asynchronous nature of graph/index construction.
- Predicted outcome if hypothesis fails: The indexing processes are sufficiently atomic or fast that stale reads are negligible.
- Estimated cost/complexity: low
- Rationale: This identifies if the failure mode is semantic (drift) or structural (race conditions/consistency lag).
# Proposed Verification Experiments

## E1 verifies [hyp #701]
- Protocol: Construct a "Dual-Intent Benchmark" consisting of two query types: (1) *Semantic Search* (e.g., "What are the general themes of the documents?") and (2) *State Reconstruction* (e.g., "What was the value of X at time T?"). Deploy a routing layer that directs (1) to a vector-only index and (2) to an append-only temporal log. Compare performance against a baseline "Single-Index" system (e.g., Zep) using the same data.
- Minimum viable test: A dataset of 50 interleaved updates to a single variable (e.g., `temperature`). Query the value at $t=25$ and $t=50$.
- Predicted outcome if hypothesis holds: The routing system achieves >90% accuracy on temporal queries, while the Single-Index system fails or returns the latest value ($t=50$) for both.
- Predicted outcome if hypothesis fails: Both systems perform equally poorly on temporal queries, or the routing overhead introduces significant latency/error without accuracy gains.
- Estimated cost/complexity: medium
- Rationale: This experiment isolates whether "intent-aware routing" actually improves retrieval accuracy or if the bottleneck is purely the underlying data structure.

## E2 verifies [hyp #708]
- Protocol: Implement two memory substrates: (A) a "State-Overwrite" substrate (standard Mem0-style) and (B) a "Temporal-Log" substrate (append-only turns + timestamps). Run the E6 Cross-Entity Temporal Correlation workload.
- Minimum viable test: Execute the E6 query: "What was Entity B's status when Entity A reached value Y?" using both substrates.
- Predicted outcome if hypothesis holds: Substrate B recovers the correct historical state for Entity B; Substrate A returns "unknown" or the current (incorrect) state because the historical state was overwritten.
- Predicted outcome if hypothesis fails: Both substrates fail the E6 query, suggesting that even with a temporal log, the retrieval mechanism (graph/vector) is the failure point.
- Estimated cost/complexity: medium
- Rationale: This bisects the "routing vs. substrate" debate by testing if routing to a broken (overwrite-based) index can ever succeed.

## E3 verifies [hyp #718]
- Protocol: Create a "Contradiction Corpus" where an entity's attributes are explicitly changed in ways that create logical conflicts (e.g., "Alice is in London" at $t=1$, "Alice is in Paris" at $t=2$). Introduce a "Probabilistic Existence Index" that tracks the frequency and recency of these conflicting claims.
- Minimum viable test: Query "Where is Alice?" and measure the system's ability to return a calibrated response (e.g., "She was in London, but most recent data says Paris" vs. a hallucinated single location).
- Predicted outcome if hypothesis holds: The system provides uncertainty metadata or a multi-state answer; standard systems provide a single, potentially incorrect, "truth."
- Predicted outcome if hypothesis fails: The system still collapses to a single "latest" value or fails to acknowledge the contradiction.
- Estimated cost/complexity: high
- Rationale: This tests if the "uncertainty" failure is a retrieval problem or a fundamental lack of metadata regarding the "truthfulness" of stored facts.

## E4 verifies [hyp #726]
- Protocol: Deploy a "Contested Graph" architecture where every memory update is treated as a new node in a graph with a "confidence" weight, rather than an update to an existing node. Compare this against a standard Knowledge Graph (KG) approach.
- Minimum viable test: Introduce three conflicting updates to the same triple (Subject-Predicate-Object) and query for the "most likely" current state vs. the "history of claims."
- Predicted outcome if hypothesis holds: The system can successfully navigate the "contested" history to answer "how has the view of X changed?" whereas the KG system only shows the final state.
- Predicted outcome if hypothesis fails: The system becomes too noisy to answer simple "current state" queries effectively.
- Estimated cost/complexity: high
- Rationale: This tests the radical shift from "database" (single truth) to "contested graph" (multiple observations).
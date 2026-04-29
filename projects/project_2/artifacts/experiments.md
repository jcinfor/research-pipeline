# Proposed Verification Experiments

## E1 verifies [hyp #196]
- Protocol: Deploy two parallel agent environments: (A) Zep-style KG-only memory and (B) Blackboard + Embedding-retrieval. Introduce a "discovery task" where the agent must identify a concept or entity that has never been explicitly named or structured in a graph node but is semantically implied by the conversation context (e.g., a new project codename mentioned via metaphor).
- Minimum viable test: Measure the success rate of the agent retrieving the correct semantic concept in a "zero-node" scenario where the entity exists only in the vector space of recent messages.
- Predicted outcome if hypothesis holds: Environment B (Embeddings) will successfully retrieve the concept, while Environment A (KG) will fail because the entity was never instantiated as a node.
- Predicted outcome if hypothesis fails: Environment A will successfully infer or create the node via its episodic subgraph, matching the retrieval performance of Environment B.
- Estimated cost/complexity: medium
- Rationale: This tests whether the KG's reliance on explicit entity extraction creates a blind spot for semantic concepts that haven't yet been formalized into nodes.

## E2 verifies [hyp #199]
- Protocol: Conduct a "Semantic Drift" stress test. Over a long-running conversation, use a specific term (e.g., "Project Phoenix") that undergoes a gradual shift in meaning (from "a marketing campaign" to "a software refactor" to "a company restructuring") without any explicit timestamped state updates or "re-definitions."
- Minimum viable test: Query the agent about the current status/nature of "Project Phoenix" at three distinct stages of the drift.
- Predicted outcome if hypothesis holds: The KG will return the original definition (stale semantic node), whereas the Embedding-retrieval will return contextually relevant recent snippets reflecting the drift.
- Predicted outcome if hypothesis fails: The KG's temporal/episodic logic will successfully update the node's semantic properties or provide the most recent contextually relevant version.
- Estimated cost/complexity: medium
- Rationale: This isolates whether temporal logic is sufficient to capture meaning changes that occur through context rather than explicit state transitions.

## E3 verifies [hyp #202]
- Protocol: Implement a "Write-Heavy Agent" simulation. Run an agent through a high-velocity stream of unstructured data (e.g., a live Slack feed) where it must maintain a Zep-style KG vs. a simple Blackboard/Embedding system.
- Minimum viable test: Measure the ratio of `Latency_per_Message` to `Retrieval_Accuracy` as the number of entities/relations grows.
- Predicted outcome if hypothesis holds: The KG system will show an exponential increase in ingestion latency (Write-Amplification) due to the overhead of entity extraction, temporal consistency checks, and subgraph updates, eventually exceeding the latency of a simple vector write.
- Predicted outcome if hypothesis fails: The KG system maintains a linear or sub-linear latency increase, proving the "Write-Amplification Trap" is manageable within operational bounds.
- Estimated cost/complexity: high
- Rationale: This directly tests the economic and computational tradeoff between the complexity of maintaining a structured graph and the utility of the retrieved data.
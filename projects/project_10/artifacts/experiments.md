# Verification Experiments

> *Verification experiments per leading hypothesis*
>
> **Project #10** — Compare three agent-memory architectures (mem0 flat-store, Zep graph, and the three-tier blackboard+wiki). Recommend one for a multi-agent research pipeline use case and identify the strongest open question.  
> Generated 2026-04-28 23:06 UTC  
> Bundle: [claims](./claims.md) · [hypotheses](./hypotheses.md) · **experiments** · [decision](./decision.md) · [risks](./risks.md)

---

## E1 verifies [hyp #796]
- Protocol: Deploy three identical multi-agent research clusters (Agent A, B, and C) tasked with a longitudinal literature review. Cluster A uses Mem0 (flat-store), Cluster B uses Zep (TKG), and Cluster C uses a three-tier blackboard+wiki architecture. Agents must perform iterative research where new findings must be integrated with previous findings to answer increasingly complex queries.
- Minimum viable test: Measure the "Reasoning Accuracy Score" (via LLM-as-a-judge) on a set of 50 "integration queries" that require connecting disparate facts found in early research phases to conclusions in later phases.
- Predicted outcome if hypothesis holds: Mem0 achieves the highest accuracy/lowest latency because its recency-weighting prevents the "contextual noise" that plagues complex graph traversals in high-turnover research sessions.
- Predicted outcome if hypothesis fails: Mem0 fails to answer queries requiring multi-hop connections, while Zep or the three-tier model shows significantly higher accuracy.
- Estimated cost/complexity: high
- Rationale: This experiment directly tests whether simplicity/recency (Mem0) provides a better signal-to-noise ratio for reasoning than the structural overhead of graphs or hierarchies.

## E2 verifies [hyp #799]
- Protocol: Create a "Cross-Project Synthesis" benchmark consisting of three distinct research projects (e.g., Project Alpha: Biology, Project Beta: Chemistry, Project Gamma: Materials Science) that share overlapping entities (e.g., a specific molecule or researcher). Use Zep's TKG and the three-tier model to store the data.
- Minimum viable test: Ask the agents to identify a non-obvious relationship between an entity in Project Alpha and an entity in Project Gamma that was only implied through a chain of connections across all three projects.
- Predicted outcome if hypothesis holds: Zep's TKG identifies the connection with high precision due to its entity-linkage density, whereas the three-tier model's siloed wiki/blackboard structure fails to bridge the project boundaries.
- Predicted outcome if hypothesis fails: The three-tier model's explicit "wiki" layer provides a more structured global context that allows for better cross-project synthesis than the graph-based approach.
- Estimated cost/complexity: medium
- Rationale: This experiment isolates "cross-project synthesis" as the primary variable, testing if relational density (Zep) is the superior mechanism for high-level knowledge integration compared to hierarchical organization.

---

## Citations

- `[src #N]` references blackboard entry N — source-doc evidence ingested into project 10.
- `[hyp #N]` references blackboard entry N — a hypothesis. See [hypotheses.md](./hypotheses.md).
- `[crit #N]` references blackboard entry N — a critique posted by an agent.

Run `rp project blackboard <project_id>` to view all entries with their numeric ids and source docs.


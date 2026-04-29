# Risks

> *Top risks with likelihood × impact → mitigation*
>
> **Project #10** — Compare three agent-memory architectures (mem0 flat-store, Zep graph, and the three-tier blackboard+wiki). Recommend one for a multi-agent research pipeline use case and identify the strongest open question.  
> Generated 2026-04-28 23:06 UTC  
> Bundle: [claims](./claims.md) · [hypotheses](./hypotheses.md) · [experiments](./experiments.md) · [decision](./decision.md) · **risks**

---

## R1: Cognitive overhead of memory maintenance (Write-to-Read bottleneck)
- Likelihood: high
- Impact: high
- Mitigation: Implement a decoupled "background maintenance" agent that performs graph/wiki updates asynchronously from the primary research agents to prevent latency and reasoning loops.
- Evidence: [crit #797]

## R2: Context window saturation from graph subgraph expansion
- Likelihood: medium
- Impact: high
- Mitigation: Implement a hierarchical summarization layer or a "subgraph pruning" mechanism that selects only the most semantically relevant nodes/triples rather than attempting to expose all related entities.
- Evidence: [src #788]

## R3: Multi-hop temporal reasoning failure
- Likelihood: high
- Impact: medium
- Mitigation: Supplement vector retrieval with explicit metadata filtering (e.g., timestamp-based SQL queries) to provide the LLM with structured temporal bounds before it attempts reasoning.
- Evidence: [src #783]

## R4: Semantic depth vs. simplicity trade-off
- Likelihood: medium
- Impact: medium
- Mitigation: Use a hybrid approach where Mem0-style flat stores handle transient/session-based context, while Zep-style TKGs are reserved for long-term, high-value structural research facts.
- Evidence: [hyp #796, crit #800]

## R5: LLM extraction error propagation in graph construction
- Likelihood: medium
- Impact: high
- Mitigation: Implement a "verification loop" where a secondary LLM pass validates extracted entities and relationships against existing graph nodes to prevent duplicate or hallucinated entities.
- Evidence: [src #788]

---

## Citations

- `[src #N]` references blackboard entry N — source-doc evidence ingested into project 10.
- `[hyp #N]` references blackboard entry N — a hypothesis. See [hypotheses.md](./hypotheses.md).
- `[crit #N]` references blackboard entry N — a critique posted by an agent.

Run `rp project blackboard <project_id>` to view all entries with their numeric ids and source docs.


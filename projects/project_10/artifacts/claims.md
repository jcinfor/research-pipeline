# Claims

> *Falsifiable claims with confidence + evidence refs + falsifier*
>
> **Project #10** — Compare three agent-memory architectures (mem0 flat-store, Zep graph, and the three-tier blackboard+wiki). Recommend one for a multi-agent research pipeline use case and identify the strongest open question.  
> Generated 2026-04-28 23:05 UTC  
> Bundle: **claims** · [hypotheses](./hypotheses.md) · [experiments](./experiments.md) · [decision](./decision.md) · [risks](./risks.md)

---

## C1: Mem0's flat-store architecture is likely to underperform in multi-agent research tasks compared to complex graph or multi-tier models due to a structural mismatch between its recency-weighted stream and the hierarchical nature of research [src #790, #800].
- Confidence: high
- Supporting: [src #781], [src #790], [hyp #796], [crit #800]
- Falsifier: "This claim would be wrong if Mem0's flat-store architecture outperformed Zep's TKG or the three-tier model in multi-agent reasoning tasks."
- Status: supported

## C2: Mem0's architecture struggles with multi-hop temporal reasoning and may lose historical state during updates [src #783].
- Confidence: high
- Supporting: [src #783]
- Falsifier: "This claim would be wrong if Mem0 could reliably perform multi-hop temporal reasoning and maintain full history during contradictory state updates."
- Status: unverified

## C3: Zep's temporal knowledge graph (TKG) provides superior temporal precision and cross-entity reasoning compared to flat-store systems [src #787].
- Confidence: medium
- Supporting: [src #785], [src #787]
- Falsifier: "This claim would be wrong if a flat-store system could perform bi-temporal queries (e.g., 'as of January 1st, what was the user's role?') with equal or greater precision than Zep."
- Status: unverified

## C4: Zep's performance may degrade when the relevant graph subgraph exceeds 10,000 triples per project [src #788].
- Confidence: medium
- Supporting: [src #788]
- Falsifier: "This claim would be wrong if Zep's 'expose all triples' approach maintained high performance and stayed within context limits at scales exceeding 10,000 triples per project."
- Status: unverified

## C5: The three-tier memory model (working / project / wiki) uses kind-typing to manage different temporal structures in research workflows [src #790, #791].
- Confidence: high
- Supporting: [src #790], [src #791]
- Falsifier: "This claim would be wrong if the three-tier model did not utilize kind-typed entries (e.g., evidence, hypothesis, experiment) to separate short-lived project data from long-term knowledge."
- Status: unverified

---

## Citations

- `[src #N]` references blackboard entry N — source-doc evidence ingested into project 10.
- `[hyp #N]` references blackboard entry N — a hypothesis. See [hypotheses.md](./hypotheses.md).
- `[crit #N]` references blackboard entry N — a critique posted by an agent.

Run `rp project blackboard <project_id>` to view all entries with their numeric ids and source docs.


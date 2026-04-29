# Decision

> *Recommended next action + predicted outcome + confidence*
>
> **Project #10** — Compare three agent-memory architectures (mem0 flat-store, Zep graph, and the three-tier blackboard+wiki). Recommend one for a multi-agent research pipeline use case and identify the strongest open question.  
> Generated 2026-04-28 23:06 UTC  
> Bundle: [claims](./claims.md) · [hypotheses](./hypotheses.md) · [experiments](./experiments.md) · **decision** · [risks](./risks.md)

---

Conduct a comparative stress test of the three architectures using a "Consistency-under-Expansion" benchmark, specifically measuring the cognitive overhead (Write-to-Read bottleneck) and the accuracy of cross-project synthesis when agents are tasked with updating a shared knowledge base. This test must move beyond simple retrieval latency to measure how much "agentic effort" is required to maintain structural integrity in the Zep graph and the three-tier wiki versus the Mem0 flat-store as the volume of interconnected research facts increases.

## Predicted Outcome

The results should reveal a performance inflection point where the Mem0 architecture fails due to semantic dilution (loss of relational depth), while the Zep and three-tier models show a sharp increase in "Write-to-Read" latency or failure rates due to the complexity of maintaining consistency. This will identify whether the primary constraint for multi-agent research is retrieval precision (favoring Zep/Three-tier) or maintenance overhead (favoring Mem0).

## Confidence

Medium — While the critiques (id=797, id=800) correctly identify the missing dimension of "maintenance overhead," the current hypotheses are in direct conflict regarding whether simplicity or relational depth is the priority. A controlled benchmark is required to resolve the tension between [hyp #796] and [hyp #799].

## Rooted in

- [hyp #796]: The debate over whether Mem0's simplicity outperforms complex models.
- [hyp #799]: The counter-argument that research requires relational depth provided by Zep/TKG.
- [src #797]: The identification of the "Write-to-Read" bottleneck as a critical missing metric.
- [src #800]: The critique that simplicity is a liability in hierarchical research contexts.

---

## Citations

- `[src #N]` references blackboard entry N — source-doc evidence ingested into project 10.
- `[hyp #N]` references blackboard entry N — a hypothesis. See [hypotheses.md](./hypotheses.md).
- `[crit #N]` references blackboard entry N — a critique posted by an agent.

Run `rp project blackboard <project_id>` to view all entries with their numeric ids and source docs.


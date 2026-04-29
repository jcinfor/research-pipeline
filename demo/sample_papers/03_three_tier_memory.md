# A three-tier memory model for multi-agent research pipelines

*Sample paper for `rp demo`. Educational content describing the architecture this repo ships.*

## Abstract

Multi-agent research workflows have a temporal structure that flat-store memory systems handle awkwardly: agents work within a single project (short-lived, dense), the project produces lasting outputs (claims, hypotheses, experiments), and outputs accumulate across projects into a long-term knowledge base. We propose a three-tier memory model — **working / project / wiki** — that maps cleanly onto this structure and avoids the "one substrate fits all workloads" failure mode of mem0 and Zep.

## Tier 1 — Working memory

Per-turn, in-prompt only. Regenerated each turn by selecting the top-K relevant evidence, hypotheses-in-play, recent posts, and last-turn KPI feedback. No storage; the prompt is the unit of working memory. Bounded to ~2k tokens so each turn stays cheap.

## Tier 2 — Project blackboard

Per-project, kind-typed durable store. Every agent post becomes an `evidence` / `hypothesis` / `critique` / `experiment` / `result` / `draft` / `review` entry on the blackboard. Cosine-deduplicated on write (echo-clustered when similarity ≥ 0.85). Hypotheses carry a state machine: `proposed → supported / refuted / verified`.

The kind-typing is the key architectural choice. mem0's flat memories don't distinguish between "user reported a fact" and "user's hypothesis is that X causes Y" — both are just memory entries. The blackboard's `kind` column lets retrieval ask narrower questions ("what critiques target hypothesis #3?") that flat stores can't answer without LLM scaffolding.

## Tier 3 — User wiki

Cross-project long-term memory. Promoted from T2 on healthy runs (rubric ≥ floor). Karpathy LLM-Wiki structure (markdown-first, append-only, human-readable) plus a single capability stolen from Zep: a `t_ref` time-anchor column for "as-of" filters. No graph DB, no full bi-temporal model. The wiki compounds across projects on the same user, seeding new projects with relevant prior knowledge.

## Why three tiers

The temptation is to use one substrate at all timescales. Doing so forces tradeoffs that hurt every workload:

- A flat store optimized for quick recall (mem0) loses the structured-fact precision needed for cross-entity reasoning.
- A graph optimized for cross-entity reasoning (Zep) carries operational and latency cost that's wasteful for simple lookup.
- A document-pattern wiki optimized for compounding knowledge (Karpathy) lacks the per-turn working-memory pattern agents need.

Three tiers let each layer specialize. T1 is fast and ephemeral; T2 is structured and project-scoped; T3 is durable and queryable across time.

## Open questions

- Does this architecture transfer to non-research workloads (customer support, code agents)?
- At what wiki-size does the cosine-search retrieval start to underperform a graph approach?
- Is the kind taxonomy (evidence/hypothesis/critique/...) overfit to research workflows, or general?

These questions are exactly what `research-pipeline`'s agents would discuss. Run `rp project run <id>` and watch them.

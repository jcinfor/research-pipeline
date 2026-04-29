# E7 — Conversational Memory Stress Test

*Minimum viable benchmark for agent-platform memory (Claude Code / Claude Work regime). First test in the E-series that matches multi-session conversational workload, not document or attribute churn.*

## What it measures

When an engineer has multiple sessions with a coding assistant over a week, can the memory system correctly handle:

1. **Pronoun resolution** — "her concern", "that bug", "she said…" referring to entities named earlier
2. **Cross-session reference** — "what did we decide yesterday?", "what did she flag Monday?"
3. **Preference evolution** — user changes mind mid-session, then reverts; final state is the reverted value, not the intermediate one
4. **Granularity spectrum** — broad recall ("who flagged this?") AND precise lookup ("what line number?")
5. **Forgetting / stale-update detection** — a topic raised Monday with no follow-up; correct answer to "was it resolved?" is "unknown", not a hallucinated "yes"

## Scenario

A 4-session dialog about an auth-refactor project:

- **Monday**: User describes a token-refresh race condition flagged by Alice (security team). Discusses mutex vs event-queue; picks mutex. Notes the CI is slow.
- **Tuesday**: User starts implementing; finds the race condition at RefreshService.js line 142. Briefly pivots to event-queue, then reverts to mutex (Alice's original suggestion).
- **Wednesday**: Adds tests; asks Claude to recall Alice's original concern.
- **Friday**: Deploys. Asks: who was it who flagged this? what did I end up choosing? is the CI still slow?

23 turns total across the four sessions.

## Scoring

Substring match for correctness + rejection of superseded / wrong keys.

Query forbidden-keys are chosen to trip up "almost-right" answers — e.g. q3 rejects "event-queue" since the user DID say it but REVERTED; a memory system that doesn't track temporal ordering correctly will output the intermediate preference and fail.

## Running it

```bash
cd research-pipeline
uv run python -m benchmarks.e7_conversational.run
```

Expected runtime on local vLLM: ~3-5 minutes (5 systems × 23 turns extraction + 30 query calls). Output: `benchmarks/e7_conversational/results/run_YYYYMMDD_HHMMSS.md`.

## What this benchmark does NOT test

- Face-recognition partitioning (m-flow feature).
- Very long sessions (100+ turns). 23 turns is enough to reveal architectural differences but not stress real deployment scale.
- LLM-as-judge for broad summary queries — all 6 queries are substring-scorable by design.
- Multi-user / permission isolation.
- Async consolidation (real mem0 does this asynchronously; our MVP is sync).
- Cross-user entity linking (real supermemory / m-flow do this; our Lite variants don't).

## Predictions (for the architectural thesis)

Before running, I predict the following axis pattern:

| axis | hybrid | zep | mem0 | supermemory | m_flow |
|---|---|---|---|---|---|
| pronoun | 0-1/2 | 1-2/2 | 0-1/2 | 1-2/2 | 1-2/2 |
| cross_session | 0-1/1 | 1/1 | 0-1/1 | 1/1 | 1/1 |
| preference_evolution | 0/1 | 1/1 | 0/1 (overwritten) | 0-1/1 | 1/1 |
| granularity_precise | 0-1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| granularity_broad | n/a | - | - | - | - |
| forgetting | 0/1 | 0/1 | 0/1 | 0-1/1 | 0-1/1 |

**Key sensitivities:**
- mem0's overwriting consolidation should fail on `q3_final_choice` — if it extracted "event-queue" at turn 5 and "mutex" at turn 7, the LATER value wins, which is mutex. Actually that might be correct! Let me think harder: the last value mem0 sees is "mutex" (from the revert). So it should get q3 right. This is a case where mem0's overwrite happens to align with preference-evolution semantics because the reverted value IS the latest.
- The real preference-evolution failure mode for mem0 would be if extraction at turn 5 ("event-queue") happens LATER than extraction at turn 7 ("mutex") due to async processing — which we don't simulate here.
- So on THIS E7 design, mem0 may surprise by keeping up. The architectural difference would show on a scenario where the intermediate preference was simply never re-stated — mem0 would carry it forward indefinitely, while zep's valid_from-aware queries would notice the user never confirmed it was final.

## Interpretation notes

- **If m_flow dominates pronoun+cross_session:** its cone/entity indexing has measurable value for conversational memory. This is the headline evidence for adopting it in agent platforms.
- **If supermemory matches m_flow:** consolidation + chunk fallback is sufficient; the cone's extra structure is untested (same verdict as E1).
- **If all four extraction systems tie:** E7 is too easy; the 2B Gemma backend is doing the pronoun resolution implicitly at query time via full-context prompt, masking the architectural difference.
- **If the forgetting query trips EVERYONE:** extraction-based systems have no inherent "I don't know" signal; they surface whatever they have. A real forgetting architecture needs explicit "last-updated + staleness threshold" logic — which none of our Lite variants implement.

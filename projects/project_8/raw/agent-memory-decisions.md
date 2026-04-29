# Agent Memory — What We Decided and Why

*Companion to [agent-memory-benchmarks.md](./agent-memory-benchmarks.md). Converts the empirical findings across E4/E1/E1-TTL/E5/E7 into concrete decisions for our research pipeline and a shortlist for the broader agent-platform question.*

## 1. Decisions for our research pipeline (grounded by data)

### 1.1 No change to the wiki (TIER 3)
**Keep the Karpathy+Zep hybrid.** E4 confirmed 5/6 correctness on sparse-contradiction document retrieval at 8× cheaper writes than pure zep. The one miss was a substring-scoring edge, not a retrieval failure. No identified gap; shipping as-is.

### 1.2 No urgent change to the blackboard (TIER 2)
E1 showed the hybrid pattern fails at 1/3 on high-velocity per-entity attribute churn. **But our actual blackboard workload is not E1's workload** — we have kind-typed entries (evidence, hypothesis, critique, experiment, result, draft, review) where each entry is a NEW fact, not an attribute update on an existing entity. The closest analog is hypothesis state transitions (proposed → supported → refuted → verified), which happen 1-3 times per hypothesis, not 20.

**Action: none for now.** E1 is a stress test for a workload we don't currently have. Revisit IF we add features like "track Prod-01's rolling status" that introduce genuine attribute churn.

### 1.3 Optional small change for hypothesis state temporal queries
If we want to answer "when was hypothesis #3 first supported?" or "show me hypotheses that were refuted and then re-supported", we'd need zep-style (entity, attribute, value, valid_from) triples for the state field. Today we just overwrite the state column. **Priority: low. Defer unless the feature request lands.**

### 1.4 Document the architecture decision
Merge the empirical conclusions back into [agent-memory-architecture.md](./agent-memory-architecture.md) §9 ("What we haven't proven") — that section can now be retitled "What we've measured" with links to the E-series results. Done as part of this consolidation.

## 2. Findings we should share externally (Claude Code / Claude Work teams)

### 2.1 Conversational memory: zep triples win at our scale
**E7 data:** on a 23-turn multi-session dialog, zep's triples-with-valid_from got **6/6**; supermemory and m-flow tied at 5/6; mem0 (overwrite) at 4/6; our hybrid (chunks only) at 4/6.

**The mechanism:** conversations generate multiple facts about the same entity (Alice's role, her bug, her suggestion, her team). Zep accumulates all of them; mem0 overwrites and loses context; m-flow's cone creates a disambiguation burden when multiple attribute-Facets match a pronoun; supermemory's arbitration prompt hallucinates on "did this happen?" queries with no recorded update.

**Specific failure modes worth naming:**
- **Mem0 on preference evolution (q3):** user said "mutex" → "event-queue" → "revert to mutex". Mem0 returned *"mutex or event-queue"* — the intermediate state leaked into the answer.
- **M-flow on pronoun ambiguity (q2):** "what was her concern?" — the cone surfaced multiple attribute-Facets about Alice; the LLM picked "mutex" (her suggestion) instead of "race condition" (her concern).
- **Supermemory on "did the CI get fixed?" (q6):** correct answer was *"unknown"*; system said *"no"*. Prompt preferred answering over deferring.

### 2.2 Our hybrid (chunks + t_ref only) is insufficient for conversational memory
E7 had it at 4/6. Same ceiling as mem0. Cheapest (5s ingest) but missing on precise-lookup queries (line 142) where the relevant turn wasn't in the cosine top-k.

### 2.3 Caveats before anyone ships on this
- Single trial per experiment.
- Substring scoring.
- 26B Gemma backend (google/gemma-4-26B). Frontier-scale extraction. At smaller models, architectural differences would likely be more pronounced — our results may UNDERSTATE the gap between architectures.
- 23-turn conversation — real Claude Code sessions reach 100-500 turns where zep's accumulating-triples context-length cost may dominate. **E7-long is the next serious-benchmark experiment.**
- "Lite" reimplementations, not the real products (~50-150 LOC each).

## 3. What we haven't answered (honest open list)

| question | experiment needed | cost |
|---|---|---|
| Does zep's E7 win survive at 100-500 turns? | E7-long | 1 day to author |
| Does m-flow's graph-path retrieval beat zep on cross-entity queries? | E6 (proposed, not built) | 2-3 hrs |
| Do the real commercial products behave like our Lite MVPs? | Integration benchmark with real SDKs | 1 week |
| Does the prompt-arbitration fix rescue supermemory on E5? | E5 re-run (in progress 2026-04-24) | minutes |
| Are any of these findings trial-variance artifacts? | 5-trial repeats | low ingest cost, ~10× compute |
| Do results change with GPT-4-class extraction? | Re-run with better backend | hosted API cost |

## 4. Recommended next actions (priority order)

1. **(Done — result was negative)** E5 re-run with revised arbitration prompt: supermemory STILL 1/3. Answers changed but overall didn't rescue. **The true root cause is cosine top-k's recency-blindness under dense-churn chunk populations — not the arbitration prompt.** To rescue E5, supermemory would need recency-weighted cosine or per-entity chunk partitioning (architectural, not prompt). E1-TTL rescue still holds because only one chunk competes for "favourite_color" there.
2. **(If pursuing agent-platform thesis seriously)** Build E6 and E7-long. E7-long is the harder lift and the one that could invalidate the zep-wins-conversational claim.
3. **(If this research wraps up here)** Ship the documentation as-is. The conclusions are defensible at the "single data point on each axis" level the work was scoped for.
4. **(If taking it public)** Multi-trial + LLM judge + larger backend. This is the "serious benchmark" path.

## 5. My personal architectural take (not empirically settled)

The thing our benchmarks confirm: **there is no single winning architecture across workloads.**

- **Attribute-churn (blackboard):** consolidate-on-update (mem0) is cheap and sufficient.
- **Sparse-contradiction documents (wiki):** our Karpathy+Zep hybrid is the Pareto winner.
- **Multi-session conversation (Claude Code):** zep's temporal triples preserve the multi-fact-per-entity pattern conversations generate.
- **Cold-fact survival + forgetting:** supermemory's chunk fallback (with correct arbitration prompt) is a genuine architectural addition.

The **right product probably layers these** rather than adopting any single one wholesale. Zep's triples for conversational memory + supermemory's chunk fallback for cold-attribute insurance + TTL for explicit forgetting = the hybrid that all five reference products gesture at but none fully combines.

M-flow's four-level cone is the most structurally ambitious option but its claimed differentiator (graph-path retrieval + cross-Entity linking) is untested by our E-series. On the workloads we DID test, its richer structure hurt as often as it helped (E7 q2 disambiguation failure). **Worth testing on E6 before writing it off.**
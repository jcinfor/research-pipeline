# Top Risks

## R1: Temporal Entropy Collapse via Attention Dilution
- Likelihood: high
- Impact: high
- Mitigation: Implement a "temporal decay" weighting in the retriever that penalizes nodes with high density but low recent relevance, preventing the attention mechanism from treating timestamps as mere noise.
- Evidence: [hyp #229]

## R2: Semantic Interference from Overlapping Validity Intervals
- Likelihood: high
- Impact: medium
- Mitigation: Transition from a simple timestamped log to an "Event Calculus" framework where facts are stored with explicit validity intervals $[t_{start}, t_{end}]$ rather than single points in time.
- Evidence: [hyp #223], [src #225], [src #222]

## R3: Chronological Drift due to Lack of State-Transition Logic
- Likelihood: medium
- Impact: high
- Mitigation: Augment the KG schema to include explicit state-transition edges that model how an entity's attributes evolve, rather than treating temporal metadata as static attributes.
- Evidence: [hyp #226], [src #228]

## R4: High-Entropy Collision of Stale Facts
- Likelihood: medium
- Impact: medium
- Mitigation: Implement an automated pruning or "forgetting" mechanism that removes or archives expired state-transitions to prevent the accumulation of high-entropy, outdated information.
- Evidence: [crit #227]

## R5: Category Error in Retrieval Logic (Structure vs. Continuity)
- Likelihood: medium
- Impact: high
- Mitigation: Validate that the retrieval engine uses temporal metadata as a logical constraint (a "logic gate") for filtering, rather than just a feature for semantic similarity.
- Evidence: [crit #224], [crit #230]
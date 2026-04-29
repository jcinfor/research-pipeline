# Claims

## C1: High temporal density in Zep-style KGs causes semantic interference and chronological drift.
- Confidence: high
- Supporting: [hyp #223], [hyp #226], [hyp #229], [src #225], [src #228]
- Falsifier: "This claim would be wrong if increasing temporal density does not lead to the agent conflating past states with current truths or treating outdated facts as concurrent truths."
- Status: supported

## C2: Zep-style KGs without state-transition logic fail to model the evolution of relationships.
- Confidence: medium
- Supporting: [src #228]
- Falsifier: "This claim would be wrong if a Zep-style KG lacking state-transition logic can still accurately model the evolution of relationships over time."
- Status: unverified

## C3: Zep outperforms MemGPT in the Deep Memory Retrieval (DMR) benchmark.
- Confidence: high
- Supporting: [src #234]
- Falsifier: "This claim would be wrong if Zep's performance in the DMR benchmark is equal to or lower than MemGPT's performance."
- Status: unverified

## C4: Temporal density in KGs can lead to "Temporal Entropy Collapse" where timestamps are treated as noise.
- Confidence: medium
- Supporting: [hyp #229]
- Falsifier: "This claim would be wrong if, as temporal density increases, the agent's attention mechanism continues to treat timestamps as logical constraints rather than noise features."
- Status: unverified

## C5: Zep utilizes a bi-temporal model consisting of a chronological timeline (T) and a second timeline (T').
- Confidence: high
- Supporting: [src #239]
- Falsifier: "This claim would be wrong if Zep implements only a single timeline for temporal information rather than a bi-temporal model."
- Status: unverified
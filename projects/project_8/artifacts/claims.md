# Claims

## C1: The primary bottleneck in memory architectures is not retrieval routing, but the loss of temporal fidelity during the extraction process.
- Confidence: high
- Supporting: [hyp #701], [hyp #713], [hyp #719], [crit #700], [crit #705], [crit #712]
- Falsifier: "This claim would be wrong if improving retrieval routing (intent-based) significantly outperforms improving the substrate's ability to preserve historical state (e.g., preventing Mem0's 0/3 failure [src #566])."
- Status: supported

## C2: Existing memory systems suffer from data destruction via overwrite, which prevents successful cross-entity temporal queries.
- Confidence: high
- Supporting: [src #566], [hyp #707], [hyp #711], [crit #706], [crit #712]
- Falsifier: "This claim would be wrong if Mem0's 0/3 failure on E6 [src #566] could be resolved solely by a better retrieval router without changing the underlying storage to an append-only or MVCC-based substrate."
- Status: supported

## C3: At frontier-scale extraction (e.g., 26B extractor with 256K context), architectural differences in memory systems nearly vanish.
- Confidence: high
- Supporting: [src #564]
- Falsifier: "This claim would be wrong if a significant performance gap between different memory architectures persisted at 124 conversational turns with a 26B extractor."
- Status: supported

## C4: Intent-based routing is a secondary optimization if the underlying storage substrate is lossy.
- Confidence: medium
- Supporting: [hyp #707], [hyp #719], [crit #711]
- Falsifier: "This claim would be wrong if a system with a lossy/overwrite-based substrate (like Mem0) achieved high scores on E6 temporal queries simply by implementing an LLM-based query-intent classifier."
- Status: unverified
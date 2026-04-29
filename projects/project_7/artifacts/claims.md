# Claims

## C1: Mem0's consolidation and M-Flow's hierarchy may cause "semantic smoothing" that erases high-frequency state changes in blackboard workloads.
- Confidence: medium
- Supporting: [hyp #458], [hyp #464], [crit #465]
- Falsifier: "This claim would be wrong if high-frequency state changes are preserved with 100% fidelity during the consolidation/hierarchy update process."
- Status: unverified

## C2: Supermemory's "consolidated profile + chunk fallback" pattern is not a strict superset of Mem0 and may trade off temporal fidelity for retrieval ease.
- Confidence: high
- Supporting: [hyp #494], [crit #490], [crit #491], [crit #496]
- Falsifier: "This claim would be wrong if Supermemory maintains the same temporal chain granularity as Zep while providing its consolidated profile."
- Status: unverified

## C3: In high-velocity blackboard workloads, the primary failure mode is an index-write race condition (consistency lag) rather than semantic drift.
- Confidence: medium
- Supporting: [hyp #470], [hyp #473], [crit #474], [crit #475]
- Falsifier: "This claim would be wrong if the time between a fact being observed and its structural integration into the memory remains negligible regardless of write-frequency."
- Status: unverified

## C4: Mem0's consolidation-based architecture is sufficient for high temporal fidelity, rendering complex hierarchies like M-Flow's "dead weight" for certain workloads.
- Confidence: low
- Supporting: [hyp #489], [hyp #489]
- Falsifier: "This claim would be wrong if Mem0's 3/3 fidelity score fails to hold when compared against a hierarchical model in a high-velocity stream."
- Status: refuted

## C5: Supermemory's TTL/forgetting mechanism may accelerate entropy and induce catastrophic forgetting in interleaved, high-velocity streams.
- Confidence: medium
- Supporting: [hyp #488], [hyp #494], [crit #496], [crit #502]
- Falsifier: "This claim would be wrong if TTL-driven forgetting successfully removes only irrelevant data without impacting the retrieval of older but still current entity data."
- Status: unverified
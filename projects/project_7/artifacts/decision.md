# Recommended Next Action

Execute a controlled E1-style benchmark specifically designed to measure "Temporal Aliasing" and "Consolidation Collapse" by comparing the Supermemory implementation against the existing Mem0 and Karpathy+Zep hybrid under a high-velocity, interleaved stream of state-changing updates (e.g., a single entity's status toggling rapidly). The test must specifically measure the delta between the *actual* ground truth state and the *retrieved* state at varying write-frequencies to determine if Supermemory's TTL/forgetting mechanism induces "catastrophic forgetting" of interleaved entity data (replicating the `hybrid_recency` failure) or if its consolidated-profile + chunk-fallback pattern successfully mitigates the "semantic smoothing" observed in Mem0.

## Predicted Outcome

If Supermemory's TTL/forgetting is a "patch for entropy" rather than a scalable architecture, we will observe a sharp drop in fidelity (below 3/3) as write-frequency increases, specifically where older but still relevant entity data is prematurely evicted. If the "consolidated-profile + chunk-fallback" pattern is a valid superset, we should see higher temporal fidelity than Mem0 during high-velocity bursts, as the chunk fallback will catch the "smoothed" or "forgotten" details that the consolidated profile loses.

## Confidence

Medium — While the E1 benchmark provides a strong baseline for comparing Mem0 and Zep, the specific failure modes of Supermemory (TTL-induced entropy vs. profile-driven stability) are currently theoretical and require empirical validation to resolve the conflict between [hyp #488] and [hyp #489].

## Rooted in

- [hyp #488]: The "consolidated profile + chunk fallback" pattern is a trap; high-frequency writes cause "consolidation collapse" where TTL-driven forgetting erases vital data.
- [hyp #489]: Supermemory’s TTL/fallback is a patch for Mem0's lack of entropy, not a true architectural superset.
- [hyp #494]: Supermemory's TTL may accelerate entropy in interleaved streams, potentially inheriting the `hybrid_recency` eviction failure.
- [src #486]: Supermemory trades Zep’s temporal chains for simplified retrieval, risking the loss of temporal fidelity.
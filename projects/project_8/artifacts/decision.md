# Recommended Next Action

Perform a "Differential State Reconstruction" test by constructing a synthetic dataset specifically designed to trigger the "overwrite vs. append" failure mode. The dataset must consist of a sequence of 50+ turns where a single entity's attribute undergoes a series of non-monotonic changes (e.g., $A \to B \to A \to C \to B$), followed by a query that requires distinguishing between the *current* state, the *most recent* state, and the *historical frequency* of a state. This test must be run against both a standard triple-store (representing the current state-of-the-art) and a prototype "Append-Only Temporal Log" to determine if the failure is indeed the loss of temporal fidelity (the "void" identified in critiques) rather than a failure of retrieval routing.

## Predicted Outcome

If the "storage-query coupling" hypothesis is secondary to the "substrate loss" hypothesis, the standard triple-store will fail the non-monotonic queries (returning only the latest state $B$) regardless of the retrieval strategy used. The Append-Only Temporal Log should succeed by allowing the LLM to reconstruct the timeline, demonstrating that the primary bottleneck is the availability of the "delta" (the history of changes) rather than the intelligence of the router.

## Confidence

High — The critiques (id=705, 706, 711, 712, 716, 719, 734) are highly consistent and grounded in the specific empirical failure of Mem0's 0/3 score on E6 [src #566]. They collectively argue that routing to a lossy substrate is a category error, making this specific test the most direct way to falsify the current design direction.

## Rooted in

- [hyp #707]: Routing is insufficient if the substrate is lossy; we must solve for temporal-logical state reconstruction.
- [hyp #713]: The bottleneck isn't routing; it's the loss of temporal fidelity during extraction.
- [src #566]: Mem0's 0/3 score on E6 demonstrates that overwrite destroys the history necessary for temporal queries.
# Proposed Verification Experiments

## E1 verifies [hyp #314]
- Protocol: Implement a "Contradictory Narrative" injection. Feed a sequence of 50 messages to both architectures where an entity's properties are described with increasing semantic ambiguity (e.g., "The CEO is John" $\rightarrow$ "John is leading the firm" $\rightarrow$ "The leadership is shifting away from John"). Measure the ability of each system to resolve the *current* state vs. the *historical* state.
- Minimum viable test: A 5-step state change (A $\rightarrow$ B $\rightarrow$ C $\rightarrow$ D $\rightarrow$ E) where the semantic description of the state becomes progressively more abstract/vague at each step.
- Predicted outcome if hypothesis holds: The Wiki-style architecture (re-synthesizing context via summaries) will maintain higher accuracy for the current state, while the TKG will suffer from "graph rot" as ambiguous edges create conflicting relational paths.
- Predicted outcome if hypothesis fails: Zep's $t_{ref}$ [src #271] will successfully isolate the most recent valid state regardless of semantic ambiguity in the text.
- Estimated cost/complexity: medium
- Rationale: This bisects the hypothesis by testing if the TKG's structural rigidity becomes a liability when the input text lacks precise semantic markers.

## E2 verifies [hyp #319]
- Protocol: The "Drift-Injection Loop." Use an LLM to generate 200 messages of a continuous narrative. Introduce a "semantic drift" parameter where the LLM is instructed to slowly change its terminology for the same entity (e.g., "Project Alpha" $\rightarrow$ "The Alpha Initiative" $\rightarrow$ "The Project"). Monitor the TKG's edge creation.
- Minimum viable test: Measure the ratio of "duplicate entities" created in the TKG versus the "merged entities" in the Wiki-style summary.
- Predicted outcome if hypothesis holds: The TKG will exhibit "semantic rot," creating fragmented, disconnected subgraphs for the same entity due to the drifting LLM extraction [src #265].
- Predicted outcome if hypothesis fails: The TKG's extraction logic will successfully map drifting terms to the same semantic entity node.
- Estimated cost/complexity: medium
- Rationale: Directly tests whether the TKG's structural advantage is neutralized by the very LLM used to populate it.

## E3 verifies [hyp #327]
- Protocol: The "Error Propagation Race." Inject a single false relation (e.g., "Entity A is a subsidiary of Entity B") into a dense graph of 100 interconnected entities. Over 50 subsequent turns, introduce "corrections" and "new facts" that touch the vicinity of the error.
- Minimum viable test: Measure the "Error Radius"—how many subsequent incorrect retrievals are triggered by the initial false edge before the system self-corrects.
- Predicted outcome if hypothesis holds: The TKG's rigid edges will propagate the error through the graph, causing a cascade of incorrect inferences, whereas the Wiki's additive/summarization approach will "dilute" the error.
- Predicted outcome if hypothesis fails: Zep's temporal indexing [src #271] will allow the system to prune the erroneous edge as soon as a conflicting temporal timestamp is introduced.
- Estimated cost/complexity: high
- Rationale: Tests the trade-off between the stability of a KG and the error-resilience of a fluid, summary-based Wiki.

## E4 verifies [hyp #334]
- Protocol: The "Query-Time Repair" test. Construct a scenario where a state change is described incorrectly (e.g., "The price is \$10" when it is actually \$20) and then corrected in a later message.
- Minimum viable test: Compare the retrieval accuracy of the *correct* value when queried using a $t_{ref}$ [src #271] constraint versus a semantic similarity search.
- Predicted outcome if hypothesis holds: The differentiator is not the extraction, but whether the query mechanism can use temporal metadata to "bypass" or "repair" a drifted edge at runtime.
- Predicted outcome if hypothesis fails: Both architectures will fail equally because the error is baked into the storage layer during the "write-time drift tax."
- Estimated cost/complexity: low
- Rationale: Shifts the focus from the ingestion problem (which both share) to the retrieval/resolution capability.
# Recommended Next Action

Define a formal, comparative specification for the "Karpathy-style LLM Wiki" baseline and design a controlled "drift-injection" experiment to test both architectures. The specification must define the Wiki as a hierarchical, additive document structure (rather than a flat vector store) to ensure a fair comparison against Zep's TKG. The experiment should simulate "semantic rot" by using a drifting LLM to perform write-time extractions into both structures, then measure the ability of each to resolve temporal contradictions and recover state using $t_{ref}$ (for Zep) versus context re-synthesis (for the Wiki).

## Predicted Outcome

A falsifiable experimental design that moves the debate from speculative "structural panacea" arguments to empirical measurements of error propagation. Success will be marked by the ability to quantify the "write-time drift tax" and determine if Zep's $t_{ref}$ provides a measurable advantage in query-time error correction compared to the Wiki's additive approach.

## Confidence

Medium — The current hypotheses are heavily focused on the *mechanism* of failure (semantic rot vs. structural rigidity), but the lack of a defined baseline for the Wiki makes any current conclusion a straw man. Defining the baseline is the prerequisite for high-confidence testing.

## Rooted in

- [hyp #315]: Identifies the lack of a formal spec for the "Wiki" baseline as a primary blocker.
- [hyp #320]: Explicitly calls for a defined baseline to make the comparison falsifiable.
- [hyp #334]: Points to the critical differentiator being "query-time resolution" of drifted data.
- [src #271]: Provides the technical mechanism ($t_{ref}$) that must be tested against the Wiki's re-synthesis.
- [src #265]: Identifies the shared vulnerability (LLM-driven extraction/write-time drift) that necessitates the experiment.
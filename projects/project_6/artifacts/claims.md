# Claims

## C1: Zep utilizes a bi-temporal model to enable accurate extraction of both absolute and relative timestamps.
- Confidence: high
- Supporting: [src #271], [src #274]
- Falsifier: "This claim would be wrong if Zep's temporal modeling could only represent absolute dates and failed to resolve relative temporal expressions like 'two weeks ago'."
- Status: supported

## C2: Zep's architecture employs a dual-storage approach consisting of an episodic subgraph and a semantic entity subgraph.
- Confidence: high
- Supporting: [src #269], [src #270]
- Falsifier: "This claim would be wrong if Zep stored all information in a single, undifferentiated flat structure without distinguishing between raw episodic data and derived semantic entities."
- Status: supported

## C3: Zep-style Temporal Knowledge Graphs (TKGs) may be susceptible to "semantic rot" if the underlying LLM-driven extraction process drifts.
- Confidence: medium
- Supporting: [hyp #309], [hyp #319], [src #265]
- Falsifier: "This claim would be wrong if it could be proven that the structural constraints of a TKG are entirely immune to the errors or drifts produced by the LLM performing the initial entity and relation extraction."
- Status: unverified

## C4: The use of reference timestamps ($t_{ref}$) in Zep provides a mechanism for temporal reasoning that distinguishes it from standard RAG.
- Confidence: high
- Supporting: [src #271], [hyp #309], [hyp #323]
- Falsifier: "This claim would be wrong if the $t_{ref}$ metadata provided no functional advantage in resolving state changes or relative dating compared to a non-temporal retrieval system."
- Status: supported

## C5: Both Zep-style TKGs and Karpathy-style Wiki architectures incur a "write-time drift tax" due to their reliance on LLM-driven distillation.
- Confidence: medium
- Supporting: [hyp #334], [critique #324], [critique #335], [src #265]
- Falsifier: "This claim would be wrong if one of the architectures could be shown to operate via a deterministic process that does not rely on LLM extraction for its primary knowledge updates."
- Status: unverified
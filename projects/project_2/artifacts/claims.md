# Claims

## C1: Zep outperforms MemGPT in the Deep Memory Retrieval (DMR) benchmark.
- Confidence: high
- Supporting: [src #68]
- Falsifier: "This claim would be wrong if Zep's performance on the Deep Memory Retrieval benchmark was equal to or lower than MemGPT's."
- Status: supported

## C2: Zep utilizes a bi-temporal model to track chronological ordering and other timestamps.
- Confidence: high
- Supporting: [src #73], [src #76]
- Falsifier: "This claim would be wrong if Zep's temporal model only tracked a single timeline or lacked the ability to distinguish between chronological event ordering and other timestamp types."
- Status: unverified

## C3: Using Zep's temporal logic to prune a blackboard entirely is an architectural fallacy because a KG cannot prune information it has not yet structured.
- Confidence: medium
- Supporting: [hyp #193], [hyp #203], [src #92]
- Falsifier: "This claim would be wrong if a temporal KG could successfully prune a blackboard using only temporal constraints without requiring the underlying data to be first structured into nodes and edges."
- Status: supported

## C4: Replacing a blackboard with a Zep-style KG creates a "Write-Amplification Trap" where the cost of maintaining temporal consistency exceeds the latency saved.
- Confidence: medium
- Supporting: [hyp #202], [src #73], [src #92]
- Falsifier: "This claim would be wrong if the computational and latency costs of maintaining temporal consistency in the KG were lower than the latency savings achieved by removing the embedding-retrieval layer."
- Status: unverified

## C5: Embedding-retrieval is necessary for semantic discovery of nodes not yet captured in the graph.
- Confidence: medium
- Supporting: [hyp #196], [src #92]
- Falsifier: "This claim would be wrong if the temporal knowledge graph could achieve full semantic discovery of all agentic information without the assistance of an embedding-retrieval layer."
- Status: unverified
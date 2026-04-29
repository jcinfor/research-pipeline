# Project 7 blackboard


## evidence (120)

- **[turn 0, system]** 5
2
0
2

r
p
A
8
2

]
L
C
.
s
c
[

1
v
3
1
4
9
1
.
4
0
5
2
:
v
i
X
r
a

Mem0: Building Production-Ready AI Agents with
Scalable Long-Term Memory

Prateek Chhikara, Dev Khant, Saket Aryan, Taranjeet Singh, and Deshraj Yadav

research@mem0.ai
  *refs:* source=mem0.pdf
- **[turn 0, system]** Large Language Models (LLMs) have demonstrated remarkable prowess in generating contextually coherent
responses, yet their fixed context windows pose fundamental challenges for maintaining consistency over
prolonged multi-session dialogues. We introduce Mem0, a scalable memory-centric architecture that addresses
this issue by dynamically extracting, consolidating, and retrieving salient information from ongoing conver-
sations. Building on this foundation, we further propose an enhanced variant that leverages graph-based
memory representations to capture complex relational structures among conversational elements. Through
comprehensive evaluations on the LOCOMO benchmark, we systematically compare our approaches against six
baseline categories: (i) established memory-augmented systems, (ii) retrieval-augmented generation (RAG)
with varying chunk sizes and k-values, (iii) a full-context approach that processes the entire conversation
history, (iv) an open-source memory solution, (v) a proprietary model system, and (vi) a dedicated memory
management platform. Empirical results demonstrate that our methods consistently outperform all existing
memory systems across four question categories: single-hop, temporal, multi-hop, and open-domain. No-
tably, Mem0 achieves 26% relative improvements in the LLM-as-a-Judge metric over OpenAI, while Mem0 with
graph memory achieves around 2% higher overall score than the base Mem0 configuration. Beyond accuracy
gains, we also markedly reduce computational overhead compared to the full-context approach. In particular,
Mem0 attains a 91% lower p95 latency and saves more than 90% token cost, thereby offering a compelling
balance between advanced reasoning capabilities and practical deployment constraints. Our findings highlight
the critical role of structured, persistent memory mechanisms for long-term conversational coherence, paving
the way for more reliable and efficient LLM-driven AI agents.
  *refs:* source=mem0.pdf
- **[turn 0, system]** Code can be found at: https://mem0.ai/research

1. Introduction

Human memory is a foundation of intelligence—it shapes our identity, guides decision-making, and enables
us to learn, adapt, and form meaningful relationships (Craik and Jennings, 1992). Among its many roles,
memory is essential for communication: we recall past interactions, infer preferences, and construct evolving
mental models of those we engage with (Assmann, 2011). This ability to retain and retrieve information
over extended periods enables coherent, contextually rich exchanges that span days, weeks, or even months.
AI agents, powered by large language models (LLMs), have made remarkable progress in generating fluent,
contextually appropriate responses (Yu et al., 2024, Zhang et al., 2024). However, these systems are
fundamentally limited by their reliance on fixed context windows, which severely restrict their ability to
maintain coherence over extended interactions (Bulatov et al., 2022, Liu et al., 2023). This limitation stems
from LLMs’ lack of persistent memory mechanisms that can extend beyond their finite context windows.
While humans naturally accumulate and organize experiences over time, forming a continuous narrative

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory
  *refs:* source=mem0.pdf, Zhang et al., Bulatov et al., Liu et al., 1992, 2011, 2024, 2022, 2023
- **[turn 0, system]** Figure 1: Illustration of memory im-
portance in AI agents. Left: Without
persistent memory, the system forgets
critical user information (vegetarian,
dairy-free preferences) between ses-
sions, resulting in inappropriate rec-
ommendations. Right: With effective
memory, the system maintains these
dietary preferences across interactions,
enabling contextually appropriate sug-
gestions that align with previously es-
tablished constraints.

of interactions, AI systems cannot inherently persist information across separate sessions or after context
overflow. The absence of persistent memory creates a fundamental disconnect in human-AI interaction.
Without memory, AI agents forget user preferences, repeat questions, and contradict previously established
facts. Consider a simple example illustrated in Figure 1, where a user mentions being vegetarian and
avoiding dairy products in an initial conversation. In a subsequent session, when the user asks about dinner
recommendations, a system without persistent memory might suggest chicken, completely contradicting
the established dietary preferences. In contrast, a system with persistent memory would maintain this
critical user information across sessions and suggest appropriate vegetarian, dairy-free options. This common
scenario highlights how memory failures can fundamentally undermine user experience and trust.
  *refs:* source=mem0.pdf
- **[turn 0, system]** Beyond conversational settings, memory mechanisms have been shown to dramatically enhance agent
performance in interactive environments (Majumder et al., Shinn et al., 2023). Agents equipped with
memory of past experiences can better anticipate user needs, learn from previous mistakes, and generalize
knowledge across tasks (Chhikara et al., 2023). Research demonstrates that memory-augmented agents
improve decision-making by leveraging causal relationships between actions and outcomes, leading to more
effective adaptation in dynamic scenarios (Rasmussen et al., 2025). Hierarchical memory architectures
(Packer et al., 2023, Sarthi et al., 2024) and agentic memory systems capable of autonomous evolution (Xu
et al., 2025) have further shown that memory enables more coherent, long-term reasoning across multiple
dialogue sessions.
  *refs:* source=mem0.pdf, Majumder et al., Shinn et al., Chhikara et al., Rasmussen et al., Packer et al., Sarthi et al., 2023, 2025, 2024
- **[turn 0, system]** Unlike humans, who dynamically integrate new information and revise outdated beliefs, LLMs effectively
“reset" once information falls outside their context window (Zhang, 2024, Timoneda and Vera, 2025). Even
as models like OpenAI’s GPT-4 (128K tokens) (Hurst et al., 2024), o1 (200K context) (Jaech et al., 2024),
Anthropic’s Claude 3.7 Sonnet (200K tokens) (Anthropic, 2025), and Google’s Gemini (at least 10M tokens)
(Team et al., 2024) push the boundaries of context length, these improvements merely delay rather than
solve the fundamental limitation. In practical applications, even these extended context windows prove
insufficient for two critical reasons. First, as meaningful human-AI relationships develop over weeks or
months, conversation history inevitably exceeds even the most generous context limits. Second, and perhaps
more importantly, real-world conversations rarely maintain thematic continuity. A user might mention dietary
preferences (being vegetarian), then engage in hours of unrelated discussion about programming tasks,
before returning to food-related queries about dinner options. In such scenarios, a full-context approach
would need to reason through mountains of irrelevant information, with the critical dietary preferences
potentially buried among thousands of tokens of coding discussions. Moreover, simply presenting longer
contexts does not ensure effective retrieval or utilization of past information, as attention mechanisms

2

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory
  *refs:* source=mem0.pdf, Hurst et al., Jaech et al., Team et al., 2024, 2025
- **[turn 0, system]** degrade over distant tokens (Guo et al., 2024, Nelson et al., 2024). This limitation is particularly problematic
in high-stakes domains such as healthcare, education, and enterprise support, where maintaining continuity
and trust is crucial (Hatalis et al., 2023). To address these challenges, AI agents must adopt memory systems
that go beyond static context extension. A robust AI memory should selectively store important information,
consolidate related concepts, and retrieve relevant details when needed—mirroring human cognitive processes
(He et al., 2024). By integrating such mechanisms, we can develop AI agents that maintain consistent
personas, track evolving user preferences, and build upon prior exchanges. This shift will transform AI from
transient, forgetful responders into reliable, long-term collaborators, fundamentally redefining the future of
conversational intelligence.
  *refs:* source=mem0.pdf, Guo et al., Nelson et al., Hatalis et al., 2024, 2023
- **[turn 0, system]** In this paper, we address a fundamental limitation in AI systems: their inability to maintain coher-
ent reasoning across extended conversations across different sessions, which severely restricts meaningful
long-term interactions with users. We introduce Mem0 (pronounced as mem-zero), a novel memory archi-
tecture that dynamically captures, organizes, and retrieves salient information from ongoing conversations.
Building on this foundation, we develop Mem0g, which enhances the base architecture with graph-based
memory representations to better model complex relationships between conversational elements. Our
experimental results on the LOCOMO benchmark demonstrate that our approaches consistently outperform
existing memory systems—including memory-augmented architectures, retrieval-augmented generation
(RAG) methods, and both open-source and proprietary solutions—across diverse question types, while
simultaneously requiring significantly lower computational resources. Latency measurements further reveal
that Mem0 operates with 91% lower response times than full-context approaches, striking an optimal balance
between sophisticated reasoning capabilities and practical deployment constraints. These contributions
represent a meaningful step toward AI systems that can maintain coherent, context-aware conversations over
extended durations—mirroring human communication patterns and opening new possibilities for applications
in personal tutoring, healthcare, and personalized assistance.

2. Proposed Methods
  *refs:* source=mem0.pdf
- **[turn 0, system]** We introduce two memory architectures for AI agents. (1) Mem0 implements a novel paradigm that extracts,
evaluates, and manages salient information from conversations through dedicated modules for memory
extraction and updation. The system processes a pair of messages between either two user participants or a
user and an assistant. (2) Mem0g extends this foundation by incorporating graph-based memory representa-
tions, where memories are stored as directed labeled graphs with entities as nodes and relationships as edges.
This structure enables a deeper understanding of the connections between entities. By explicitly modeling
both entities and their relationships, Mem0g supports more advanced reasoning across interconnected facts,
especially for queries that require navigating complex relational paths across multiple memories.

2.1. Mem0

Our architecture follows an incremental processing paradigm, enabling it to operate seamlessly within
ongoing conversations. As illustrated in Figure 2, the complete pipeline architecture consists of two phases:
extraction and update.

The extraction phase initiates upon ingestion of a new message pair (mt−1, mt), where mt

represents the
the preceding one. This pair typically consists of a user message and an assistant
current message and mt−1
response, capturing a complete interaction unit. To establish appropriate context for memory extraction, the
system employs two complementary sources: (1) a conversation summary S retrieved from the database that

3

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory
  *refs:* source=mem0.pdf
- **[turn 0, system]** Figure 2: Architectural overview of the Mem0 system showing extraction and update phase. The extraction phase
processes messages and historical context to create new memories. The update phase evaluates these extracted
memories against similar existing ones, applying appropriate operations through a Tool Call mechanism. The database
serves as the central repository, providing context for processing and storing updated memories.
  *refs:* source=mem0.pdf
- **[turn 0, system]** encapsulates the semantic content of the entire conversation history, and (2) a sequence of recent messages
{mt−m, mt−m+1, ..., mt−2} from the conversation history, where m is a hyperparameter controlling the recency
window. To support context-aware memory extraction, we implement an asynchronous summary generation
module that periodically refreshes the conversation summary. This component operates independently of the
main processing pipeline, ensuring that memory extraction consistently benefits from up-to-date contextual
information without introducing processing delays. While S provides global thematic understanding across
the entire conversation, the recent message sequence offers granular temporal context that may contain
relevant details not consolidated in the summary. This dual contextual information, combined with the new
message pair, forms a comprehensive prompt P = (S, {mt−m, ..., mt−2}, mt−1, mt) for an extraction function
ϕ implemented via an LLM. The function ϕ(P) then extracts a set of salient memories Ω = {ω1, ω2, ..., ωn}
specifically from the new exchange while maintaining awareness of the conversation’s broader context,
resulting in candidate facts for potential inclusion in the knowledge base.
  *refs:* source=mem0.pdf
- **[turn 0, system]** Following extraction, the update phase evaluates each candidate fact against existing memories to
maintain consistency and avoid redundancy. This phase determines the appropriate memory management
operation for each extracted fact ωi ∈ Ω. Algorithm 1, mentioned in Appendix B, illustrates this process. For
each fact, the system first retrieves the top s semantically similar memories using vector embeddings from the
database. These retrieved memories, along with the candidate fact, are then presented to the LLM through
a function-calling interface we refer to as a ‘tool call.’ The LLM itself determines which of four distinct
operations to execute: ADD for creation of new memories when no semantically equivalent memory exists;
UPDATE for augmentation of existing memories with complementary information; DELETE for removal of
memories contradicted by new information; and NOOP when the candidate fact requires no modification to
the knowledge base. Rather than using a separate classifier, we leverage the LLM’s reasoning capabilities
to directly select the appropriate operation based on the semantic relationship between the candidate fact
and existing memories. Following this determination, the system executes the provided operations, thereby
maintaining knowledge base coherence and temporal consistency.

4

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory
  *refs:* source=mem0.pdf
- **[turn 0, system]** Figure 3: Graph-based memory architecture of Mem0g illustrating entity extraction and update phase. The extraction
phase uses LLMs to convert conversation messages into entities and relation triplets. The update phase employs conflict
detection and resolution mechanisms when integrating new information into the existing knowledge graph.

In our experimental evaluation, we configured the system with ‘m’ = 10 previous messages for contextual
reference and ‘s’ = 10 similar memories for comparative analysis. All language model operations utilized
GPT-4o-mini as the inference engine. The vector database employs dense embeddings to facilitate efficient
similarity search during the update phase.

2.2. Mem0g

The Mem0g pipeline, illustrated in Figure 3, implements a graph-based memory approach that effectively
captures, stores, and retrieves contextual information from natural language interactions (Zhang et al.,
2022). In this framework, memories are represented as a directed labeled graph G = (V, E, L), where:

• Nodes V represent entities (e.g., A lice, San_Fr ancisco)
• Edges E represent relationships between entities (e.g., lives_in)
• Labels L assign semantic types to nodes (e.g., A l ice - Person, San_Fr ancisco - City)

Each entity node v ∈ V contains three components: (1) an entity type classification that categorizes
that captures the entity’s semantic
. Relationships in our system are structured as
are source and destination entity nodes, respectively, and r is
  *refs:* source=mem0.pdf, Zhang et al., 2022
- **[turn 0, system]** the entity (e.g., Person, Location, Event), (2) an embedding vector ev
meaning, and (3) metadata including a creation timestamp tv
triplets in the form (vs, r, vd), where vs
the labeled edge connecting them.

and vd

The extraction process employs a two-stage pipeline leveraging LLMs to transform unstructured text into
structured graph representations. First, an entity extractor module processes the input text to identify a set
of entities along with their corresponding types. In our framework, entities represent the key information
elements in conversations—including people, locations, objects, concepts, events, and attributes that merit
representation in the memory graph. The entity extractor identifies these diverse information units by
analyzing the semantic importance, uniqueness, and persistence of elements in the conversation. For instance,
in a conversation about travel plans, entities might include destinations (cities, countries), transportation
modes, dates, activities, and participant preferences—essentially any discrete information that could be
relevant for future reference or reasoning.

5

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory
  *refs:* source=mem0.pdf
- **[turn 0, system]** Next, a relationship generator component derives meaningful connections between these entities,
establishing a set of relationship triplets that capture the semantic structure of the information. This LLM-
based module analyzes the extracted entities and their context within the conversation to identify semantically
significant connections. It works by examining linguistic patterns, contextual cues, and domain knowledge to
determine how entities relate to one another. For each potential entity pair, the generator evaluates whether
a meaningful relationship exists and, if so, classifies this relationship with an appropriate label (e.g., ‘lives_in’,
‘prefers’, ‘owns’, ‘happened_on’). The module employs prompt engineering techniques that guide the LLM
to reason about both explicit statements and implicit information in the dialogue, resulting in relationship
triplets that form the edges in our memory graph and enable complex reasoning across interconnected
information. When integrating new information, Mem0g employs a sophisticated storage and update strategy.
For each new relationship triple, we compute embeddings for both source and destination entities, then
search for existing nodes with semantic similarity above a defined threshold ‘t’. Based on node existence,
the system may create both nodes, create only one node, or use existing nodes before establishing the
relationship with appropriate metadata. To maintain a consistent knowledge graph, we implement a conflict
detection mechanism that identifies potentially conflicting existing relationships when new information
arrives. An LLM-based update resolver determines if certain relationships should be obsolete, marking them
as invalid rather than physically removing them to enable temporal reasoning.
  *refs:* source=mem0.pdf
- **[turn 0, system]** The memory retrieval functionality in Mem0g implements a dual-approach strategy for optimal information
access. The entity-centric method first identifies key entities within a query, then leverages semantic similarity
to locate corresponding nodes in the knowledge graph. It systematically explores both incoming and outgoing
relationships from these anchor nodes, constructing a comprehensive subgraph that captures relevant
contextual information. Complementing this, the semantic triplet approach takes a more holistic view by
encoding the entire query as a dense embedding vector. This query representation is then matched against
textual encodings of each relationship triplet in the knowledge graph. The system calculates fine-grained
similarity scores between the query and all available triplets, returning only those that exceed a configurable
relevance threshold, ranked in order of decreasing similarity. This dual retrieval mechanism enables Mem0g to
handle both targeted entity-focused questions and broader conceptual queries with equal effectiveness.

From an implementation perspective, the system utilizes Neo4j1 as the underlying graph database. LLM-
based extractors and update module leverage GPT-4o-mini with function calling capabilities, allowing for
structured extraction of information from unstructured text. By combining graph-based representations with
semantic embeddings and LLM-based information extraction, Mem0g achieves both the structural richness
needed for complex reasoning and the semantic flexibility required for natural language understanding.
  *refs:* source=mem0.pdf
- **[turn 0, system]** 3. Experimental Setup

3.1. Dataset

The LOCOMO (Maharana et al., 2024) dataset is designed to evaluate long-term conversational memory in
dialogue systems. It comprises 10 extended conversations, each containing approximately 600 dialogues and
26000 tokens on average, distributed across multiple sessions. Each conversation captures two individuals
discussing daily experiences or past events. Following these multi-session dialogues, each conversation is
accompanied by 200 questions on an average with corresponding ground truth answers. These questions
are categorized into multiple types: single-hop, multi-hop, temporal, and open-domain. The dataset
originally included an adversarial question category, which was designed to test systems’ ability to recognize

1

https://neo4j.com/

6

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

unanswerable questions. However, this category was excluded from our evaluation because ground truth
answers were unavailable, and the expected behavior for this question type is that the agent should recognize
them as unanswerable.

3.2. Evaluation Metrics

Our evaluation framework implements a comprehensive approach to assess long-term memory capabilities
in dialogue systems, considering both response quality and operational efficiency. We categorize our metrics
into two distinct groups that together provide a holistic understanding of system performance.
  *refs:* source=mem0.pdf, Maharana et al., 2024
- **[turn 0, system]** (1) Performance Metrics Previous research in conversational AI (Goswami, 2025, Soni et al., 2024, Singh
et al., 2020) has predominantly relied on lexical similarity metrics such as F1 Score (F1) and BLEU-1 (B1).
However, these metrics exhibit significant limitations when evaluating factual accuracy in conversational
contexts. Consider a scenario where the ground truth answer is ‘Alice was born in March’ and a system
generates ‘Alice is born in July.’ Despite containing a critical factual error regarding the birth month, traditional
metrics would assign relatively high scores due to lexical overlap in the remaining tokens (‘Alice,’ ‘born,’ etc.).
This fundamental limitation can lead to misleading evaluations that fail to capture semantic correctness.
To address these shortcomings, we use LLM-as-a-Judge (J) as a complementary evaluation metric. This
approach leverages a separate, more capable LLM to assess response quality across multiple dimensions,
including factual accuracy, relevance, completeness, and contextual appropriateness. The judge model
analyzes the question, ground truth answer and the generated answer, providing a more nuanced evaluation
that aligns better with human judgment. Due to the stochastic nature of J evaluations, we conducted 10
independent runs for each method on the entire dataset and report the mean scores along with ±1 standard
deviation. More details about the J is present in Appendix A.
  *refs:* source=mem0.pdf, Soni et al., Singh et al., 2025, 2024, 2020
- **[turn 0, system]** (2) Deployment Metrics Beyond response quality, practical deployment considerations are crucial for real-
world applications of long-term memory in AI agents. We systematically track Token Consumption, using
‘cl100k_base’ encoding from tiktoken, measuring the number of tokens extracted during retrieval that
serve as context for answering queries. For our memory-based models, these tokens represent the memories
retrieved from the knowledge base, while for RAG-based models, they correspond to the total number of
tokens in the retrieved text chunks. This distinction is important as it directly affects operational costs and
system efficiency—whether processing concise memory facts or larger raw text segments. We further monitor
Latency, (i) search latency: which captures the total time required to search the memory (in memory-based
solutions) or chunk (in RAG-based solutions) and (ii) total latency: time to generate appropriate responses,
consisting of both retrieval time (accessing memories or chunks) and answer generation time using the LLM.

The relationship between these metrics reveals important trade-offs in system design. For instance,
more sophisticated memory architectures might achieve higher factual accuracy but at the cost of increased
token consumption and latency. Our multi-dimensional evaluation methodology enables researchers and
practitioners to make informed decisions based on their specific requirements, whether prioritizing response
quality for critical applications or computational efficiency for real-time deployment scenarios.

3.3. Baselines
  *refs:* source=mem0.pdf
- **[turn 0, system]** To comprehensively evaluate our approach, we compare against six distinct categories of baselines that
represent the current state of conversational memory systems. These diverse baselines collectively provide a

7

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

robust framework for evaluating the effectiveness of different memory architectures across various dimensions,
including factual accuracy, computational efficiency, and scalability to extended conversations. Where
applicable, unless otherwise specified, we set the temperature to 0 to ensure the runs are as reproducible as
possible.

Established LOCOMO Benchmarks We first establish a comparative foundation by evaluating previously
benchmarked methods on the LOCOMO dataset. These include five established approaches: LoCoMo (Maha-
rana et al., 2024), ReadAgent (Lee et al., 2024), MemoryBank (Zhong et al., 2024), MemGPT (Packer et al.,
2023), and A-Mem (Xu et al., 2025). These established benchmarks not only provide direct comparison
points with published results but also represent the evolution of conversational memory architectures across
different algorithmic paradigms. For our evaluation, we select the metrics where gpt-4o-mini was used
for the evaluation. More details about these benchmarks are mentioned in Appendix C.
  *refs:* source=mem0.pdf, Lee et al., Zhong et al., Packer et al., 2024, 2023, 2025
- **[turn 0, system]** Open-Source Memory Solutions Our second category consists of promising open-source memory architec-
tures such as LangMem2 (Hot Path) that have demonstrated effectiveness in related conversational tasks but
have not yet been evaluated on the LOCOMO dataset. By adapting these systems to our evaluation framework,
we broaden the comparative landscape and identify potential alternative approaches that may offer competi-
tive performance. We initialized the LLM with gpt-4o-mini and used text-embedding-small-3 as the
embedding model.

Retrieval-Augmented Generation (RAG) As a baseline, we treat the entire conversation history as a
document collection and apply a standard RAG pipeline. We first segment each conversation into fixed-length
chunks (128, 256, 512, 1024, 2048, 4096, and 8192 tokens), where 8192 is the maximum chunk size
supported by our embedding model. All chunks are embedded using OpenAI’s text-embedding-small-3
to ensure consistent vector quality across configurations. At query time, we retrieve the top k chunks by
semantic similarity and concatenate them as context for answer generation. Throughout our experiments we
set k∈{1,2}: with k=1 only the single most relevant chunk is used, and with k=2 the two most relevant
chunks (up to 16384 tokens) are concatenated. We avoid k > 2 since the average conversation length (26000
tokens) would be fully covered, negating the benefits of selective retrieval. By varying chunk size and k, we
systematically evaluate RAG performance on long-term conversational memory tasks.
  *refs:* source=mem0.pdf, 2048
- **[turn 0, system]** Full-Context Processing We adopt a straightforward approach by passing the entire conversation history
within the context window of the LLM. This method leverages the model’s inherent ability to process
sequential information without additional architectural components. While conceptually simple, this approach
faces practical limitations as conversation length increases, eventually increasing token cost and latency.
Nevertheless, it establishes an important reference point for understanding the value of more sophisticated
memory mechanisms compared to direct processing of available context.

Proprietary Models We evaluate OpenAI’s memory3 feature available in their ChatGPT interface, specifically
using gpt-4o-mini for consistency. We ingest entire LOCOMO conversations with a prompt (see Appendix A)
into single chat sessions, prompting memory generation with timestamps, participant names, and conversation

2

3

https://langchain-ai.github.io/langmem/
https://openai.com/index/memory-and-new-controls-for-chatgpt/

8

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory
  *refs:* source=mem0.pdf
- **[turn 0, system]** Table 1: Performance comparison of memory-enabled systems across different question types in the LOCOMO dataset.
Evaluation metrics include F1 score (F1), BLEU-1 (B1), and LLM-as-a-Judge score (J), with higher values indicating
better performance. A-Mem∗ represents results from our re-run of A-Mem to generate LLM-as-a-Judge scores by setting
temperature as 0. Mem0g indicates our proposed architecture enhanced with graph memory. Bold denotes the best
performance for each metric across all methods. (↑) represents higher score is better.

Method

LoCoMo
ReadAgent
MemoryBank
MemGPT
A-Mem
A-Mem*
LangMem
Zep
OpenAI

Mem0
Mem0g

Single Hop
B1 ↑

J ↑

Multi-Hop
B1 ↑

J ↑

F1 ↑

Open Domain
B1 ↑

J ↑

F1 ↑

19.75
6.48
4.77
17.72
20.09
14.90
26.86
23.30
23.72

–
–
–
–
–
39.79 ± 0.38
62.23 ± 0.75
61.70 ± 0.32
63.79 ± 0.46

11.16
12.04
5.12
5.31
5.94
5.56
7.44
9.15
12.00
12.14
8.81
9.22
26.04 22.32
14.82
19.37
15.42
20.09

–
–
–
–
–
18.85 ± 0.31
47.92 ± 0.47
41.35 ± 0.48
42.92 ± 0.63

29.05
7.66
5.16
34.34
37.06
27.58
33.63

–
40.36
–
9.67
–
6.61
–
41.04
–
44.65
54.05 ± 0.22
33.34
40.91
71.12 ± 0.20
49.56 38.92 76.60 ± 0.13
62.29 ± 0.12
39.31

31.16

Temporal
B1 ↑

J ↑

14.77
8.87
6.99
19.44
36.67
31.08
25.84
34.53
11.25

–
–
–
–
–
49.91 ± 0.31
23.43 ± 0.39
49.31 ± 0.50
21.71 ± 0.20

F1 ↑

18.41
12.60
9.68
25.52
45.85
35.40
30.75
42.00
14.04

F1 ↑

25.02
9.15
5.00
26.65
27.02
20.76
35.51
35.74
34.30

38.72 27.13 67.13 ± 0.65 28.64 21.58 51.15 ± 0.31
47.19 ± 0.67
38.09

65.71 ± 0.45

26.03

24.32

18.82

47.65
38.72
49.27 40.30

72.93 ± 0.11
75.71 ± 0.21
  *refs:* source=mem0.pdf
- **[turn 0, system]** 55.51 ± 0.34
48.93 40.51
51.55 40.28 58.13 ± 0.44

text. These generated memories are then used as complete context for answering questions about each
conversation, intentionally granting the OpenAI approach privileged access to all memories rather than
only question-relevant ones. This methodology accommodates the lack of external API access for selective
memory retrieval in OpenAI’s system for benchmarking.

Memory Providers We incorporate Zep (Rasmussen et al., 2025), a memory management platform designed
for AI agents. Using their platform version, we conduct systematic evaluations across the LOCOMO dataset,
maintaining temporal fidelity by preserving timestamp information alongside conversational content. This
temporal anchoring ensures that time-sensitive queries can be addressed through appropriately contextualized
memory retrieval, particularly important for evaluating questions that require chronological awareness.
This baseline represents an important commercial implementation of memory management specifically
engineered for AI agents.

4. Evaluation Results, Analysis and Discussion.

4.1. Performance Comparison Across Memory-Enabled Systems

Table 1 reports F1, B1 and J scores for our two architectures—Mem0 and Mem0g —against a suite of competitive
baselines, as mentioned in Section 3, on single-hop, multi-hop, open-domain, and temporal questions. Overall,
both of our models set new state-of-the-art marks in all the three evaluation metrics for most question types.
  *refs:* source=mem0.pdf, Rasmussen et al., 2025
- **[turn 0, system]** Single-Hop Question Performance Single-hop queries involve locating a single factual span contained
within one dialogue turn. Leveraging its dense memories in natural language text, Mem0 secures the strongest
results:F1=38.72, B1=27.13, and J=67.13. Augmenting the natural language memories with graph memory
(Mem0g) yields marginal performance drop compared to Mem0, indicating that relational structure provides
limited utility when the retrieval target occupies a single turn. Among the existing baselines, the full-context
OpenAI run attains the next-best J score, reflecting the benefits of retaining the entire conversation in context,
while LangMem and Zep both score around 8% relatively less against our models on J score. Previous LOCOMO

9

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

benchmarks such as A-mem lag by more than 25 points in J, underscoring the necessity of fine-grained,
structured memory indexing even for simple retrieval tasks.
  *refs:* source=mem0.pdf
- **[turn 0, system]** Multi-Hop Question Performance Multi-hop queries require synthesizing information dispersed across
multiple conversation sessions, posing significant challenges in memory integration and retrieval. Mem0 clearly
outperforms other methods with an F1 score of 28.64 and a J score of 51.15, reflecting its capability to
efficiently retrieve and integrate disparate information stored across sessions. Interestingly, the addition
of graph memory in Mem0g does not provide performance gains here, indicating potential inefficiencies
or redundancies in structured graph representations for complex integrative tasks compared to dense
natural language memory alone. Baselines like LangMem show competitive performances, but their scores
substantially trail those of Mem0, emphasizing the advantage of our refined memory indexing and retrieval
mechanisms for complex query processing.
  *refs:* source=mem0.pdf
- **[turn 0, system]** Open-Domain Performance In open-domain settings, the baseline Zep achieves the highest F1 (49.56) and
J (76.60) scores, edging out our methods by a narrow margin. In particular, Zep’s J score of 76.60 surpasses
Mem0g’s 75.71 by just 0.89 percentage points and outperforms Mem0’s 72.93 by 3.67 points, highlighting a
consistent, if slight, advantage in integrating conversational memory with external knowledge. Mem0gremains
a strong runner-up, with a J of 75.71 reflecting high factual retrieval precision, while Mem0 follows with 72.93,
demonstrating robust coherence. These results underscore that although structured relational memories (as
in Mem0 and Mem0g) substantially improve open-domain retrieval, Zep maintains a small but meaningful
lead.
  *refs:* source=mem0.pdf
- **[turn 0, system]** Temporal Reasoning Performance Temporal reasoning tasks hinge on accurate modeling of event se-
quences, their relative ordering, and durations within conversational history. Our architectures demonstrate
substantial improvements across all metrics, with Mem0g achieving the highest F1(51.55) and J (58.13),
suggesting that structured relational representations in addition to natural language memories significantly
aid in temporally grounded judgments. Notably, the base variant, Mem0, also provide a decent J score (55.51),
suggesting that natural language alone can aid in temporally grounded judgments. Among baselines, OpenAI
notably underperforms, with scores below 15%, primarily due to missing timestamps in most generated
memories despite explicit prompting in the OpenAI ChatGPT to extract memories with timestamps. Other
baselines such as A-Mem achieve respectable results, yet our models clearly advance the state-of-the-art,
emphasizing the critical advantage of accurately leveraging both natural language contextualization and
structured graph representations for temporal reasoning.

4.2. Cross-Category Analysis
  *refs:* source=mem0.pdf
- **[turn 0, system]** The comprehensive evaluation across diverse question categories reveals that our proposed architectures,
Mem0 and Mem0g, consistently achieve superior performance compared to baseline systems. For single-hop
queries, Mem0 demonstrates particularly strong performance, benefiting from its efficient dense natural
language memory structure. Although graph-based representations in Mem0g slightly lag behind in lexical
overlap metrics for these simpler queries, they significantly enhance semantic coherence, as demonstrated
by competitive J scores. This indicates that graph structures are more beneficial in scenarios involving
nuanced relational context rather than straightforward retrieval. For multi-hop questions, Mem0 exhibits clear
advantages by effectively synthesizing dispersed information across multiple sessions, confirming that natural
language memories provide sufficient representational richness for these integrative tasks. Surprisingly, the

10

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

Table 2: Performance comparison of various baselines with proposed methods. Latency measurements show p50
(median) and p95 (95th percentile) values in seconds for both search time (time taken to fetch memories/chunks) and
total time (time to generate the complete response). Overall LLM-as-a-Judge score (J) represents the quality metric of
the generated responses on the entire LOCOMO dataset.

K

1

2

Method

RAG

Full-context

A-Mem
LangMem
Zep
OpenAI

Mem0
Mem0g

Latency (seconds)

Search

Total

Overall
J

chunk size /
memory tokens

p50

p95

p50

p95
  *refs:* source=mem0.pdf
- **[turn 0, system]** 128
256
512
1024
2048
4096
8192

128
256
512
1024
2048
4096
8192

26031

2520
127
3911
4437

1764
3616

0.281
0.251
0.240
0.240
0.255
0.254
0.279

0.267
0.255
0.247
0.238
0.261
0.266
0.288

-

0.668
17.99
0.513
-

0.148
0.476

0.823
0.710
0.639
0.723
0.752
0.719
0.838

0.624
0.699
0.746
0.702
0.829
0.944
1.124

-

1.485
59.82
0.778
-

0.200
0.657

0.774
0.745
0.772
0.821
0.996
1.093
1.396

0.766
0.802
0.829
0.860
1.101
1.451
2.312

9.870

1.410
18.53
1.292
0.466

0.708
1.091

1.825
1.628
1.710
1.957
2.182
2.711
4.416

1.829
1.907
1.729
1.850
2.791
4.822
9.942

47.77 ± 0.23%
50.15 ± 0.16%
46.05 ± 0.14%
40.74 ± 0.17%
37.93 ± 0.12%
36.84 ± 0.17%
44.53 ± 0.13%

59.56 ± 0.19%
60.97 ± 0.20%
58.19 ± 0.18%
50.68 ± 0.13%
48.57 ± 0.22%
51.79 ± 0.15%
60.53 ± 0.16%

17.117

72.90 ± 0.19%

4.374
60.40
2.926
0.889

1.440
2.590

48.38 ± 0.15%
58.10 ± 0.21%
65.99 ± 0.16%
52.90 ± 0.14%

66.88 ± 0.15%
68.44 ± 0.17%

expected relational advantages of Mem0g do not translate into better outcomes here, suggesting potential
overhead or redundancy when navigating more intricate graph structures in multi-step reasoning scenarios.
  *refs:* source=mem0.pdf, 2048
- **[turn 0, system]** In temporal reasoning, Mem0g substantially outperforms other methods, validating that structured
relational graphs excel in capturing chronological relationships and event sequences. The presence of explicit
relational context significantly enhances Mem0g’s temporal coherence, outperforming Mem0’s dense memory
storage and highlighting the importance of precise relational representations when tracking temporally
sensitive information. Open-domain performance further reinforces the value of relational modeling. Mem0g,
benefiting from the relational clarity of graph-based memory, closely competes with the top-performing
baseline (Zep). This competitive result underscores Mem0g’s robustness in integrating external knowledge
through relational clarity, suggesting an optimal synergy between structured memory and open-domain
information synthesis.

11

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

(a) Comparison of search latency at p50 (median) and p95 (95th percentile) across different memory methods (Mem0, Mem0g, best
RAG variant, Zep, LangMem, and A-Mem). The bar heights represent J scores (left axis), while the line plots show search latency in
seconds (right axis scaled in log).

(b) Comparison of total response latency at p50 and p95 across different memory methods (Mem0, Mem0g, best RAG variant, Zep,
LangMem, OpenAI, full-context, and A-Mem). The bar heights represent J scores (left axis), and the line plots capture end-to-end
latency in seconds (right axis scaled in log).
  *refs:* source=mem0.pdf
- **[turn 0, system]** Figure 4: Latency Analysis of Different Memory Approaches. These subfigures illustrate the J scores and latency
comparison of various selected methods from Table 2. Subfigure (a) highlights the search/retrieval latency prior to
answer generation, while Subfigure (b) shows the total latency (including LLM inference). Both plots overlay each
method’s J score for a holistic view of their accuracy and efficiency.

Overall, our analysis indicates complementary strengths of Mem0 and Mem0g across various task demands:
dense, natural-language-based memory offers significant efficiency for simpler queries, while explicit rela-
tional modeling becomes essential for tasks demanding nuanced temporal and contextual integration. These
findings reinforce the importance of adaptable memory structures tailored to specific reasoning contexts in
AI agent deployments.

12

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

4.3. Performance Comparison of Mem0 and Mem0g Against RAG Approaches and Full-Context Model
  *refs:* source=mem0.pdf
- **[turn 0, system]** Comparisons in Table 2, focusing on the ‘Overall J’ column, reveal that both Mem0 and Mem0g consistently
outperform all RAG configurations, which vary chunk sizes (128–8192 tokens) and retrieve either one (k=1)
or two (k=2) chunks. Even the strongest RAG approach peaks at around 61% in the J metric, whereas
Mem0 reaches 67%—about a 10% relative improvement—and Mem0g reaches over 68%, achieving around
a 12% relative gain. These advances underscore the advantage of capturing only the most salient facts in
memory, rather than retrieving large chunk of original text. By converting the conversation history into
concise, structured representations, Mem0 and Mem0g mitigate noise and surface more precise cues to the
LLM, leading to better answers as evaluated by an external LLM (J).
  *refs:* source=mem0.pdf
- **[turn 0, system]** Despite these improvements, a full-context method that ingests a chunk of roughly 26,000 tokens still
achieves the highest J score (approximately 73%). However, as shown in Figure 4b, it also incurs a very
high total p95 latency—around 17 seconds—since the model must read the entire conversation on every
query. By contrast, Mem0 and Mem0g significantly reduce token usage and thus achieve lower p95 latencies of
around 1.44 seconds (a 92% reduction) and 2.6 seconds (a 85% reduction), respectively over full-context
approach. Although the full-context approach can provide a slight accuracy edge, the memory-based systems
offer a more practical trade-off, maintaining near-competitive quality while imposing only a fraction of the
token and latency cost. As conversation length increases, full-context approaches suffer from exponential
growth in computational overhead (evident in Table 2 where total p95 latency increases significantly with
larger k values or chunk sizes). This increase in input chunks leads to longer response times and higher
token consumption costs. In contrast, memory-focused approaches like Mem0 and Mem0g maintain consistent
performance regardless of conversation length, making them substantially more viable for production-scale
deployments where efficiency and responsiveness are critical.

4.4. Latency Analysis
  *refs:* source=mem0.pdf
- **[turn 0, system]** Table 2 provides a comprehensive performance comparison of various retrieval and memory methodologies,
presenting median (p50) and tail (p95) latencies for both the search phase and total response generation
across the LOCOMO dataset. Our analysis reveals distinct performance patterns governed by architectural
choices. Memory-centric architectures demonstrate different performance characteristics. A-Mem, despite its
larger memory store, incurs substantial search overhead (p50: 0.668s), resulting in total median latencies of
1.410s. LangMem exhibits even higher search latencies (p50: 17.99s, p95: 59.82s), rendering it impractical
for interactive applications. Zep achieves moderate performance (p50 total: 1.292s). The full-context
baseline, which processes the entire conversation history without retrieval, fundamentally differs from
retrieval-based approaches. By passing the entire conversation context (26000 tokens) directly to the LLM, it
eliminates search overhead but incurs extreme total latencies (p50: 9.870s, p95: 17.117s). Similarly, the
OpenAI implementation does not perform memory search, as it processes manually extracted memories from
their playground. While this approach achieves impressive response generation times (p50: 0.466s, p95:
0.889s), it requires pre-extraction of relevant context, which is not reflected in the reported metrics.
  *refs:* source=mem0.pdf
- **[turn 0, system]** Our proposed Mem0 approach achieves the lowest search latency among all methods (p50: 0.148s, p95:
0.200s) as illustrated in Figure 4a. This efficiency stems from our selective memory retrieval mechanism
and infra improvements that dynamically identifies and retrieves only the most salient information rather
than fixed-size chunks. Consequently, Mem0 maintains the lowest total median latency (0.708s) with
remarkably contained p95 values (1.440s), making it particularly suitable for latency-sensitive applications
such as interactive AI agents. The graph-enhanced Mem0g variant introduces additional relational modeling
capabilities at a moderate latency cost, with search times (0.476s) still outperforming all existing memory

13

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

solutions and baselines. Despite this increase, Mem0g maintains competitive total latencies (p50: 1.091s, p95:
2.590s) while achieving the highest J score (68.44%) across all methods—trailing only the computationally
prohibitive full-context approach. This performance profile demonstrates our methods’ ability to balance
response quality and computational efficiency, offering a compelling solution for production AI agents where
both factors are critical constraints.

4.5. Memory System Overhead: Token Analysis and Construction Time
  *refs:* source=mem0.pdf
- **[turn 0, system]** We measure the average token budget required to materialise each system’s long-term memory store.
Mem0 encodes complete dialogue turns in a natural language representation and therefore occupies only 7k
tokens per conversation on an average. Where as Mem0g roughly doubles the footprint to 14k tokens, due to
the introduction of graph memories which includes nodes and corresponding relationships. In stark contrast,
Zep’s memory graph consumes in excess of 600k tokens. The inflation arises from Zep’s design choice to
cache a full abstractive summary at every node while also storing facts on the connecting edges, leading
to extensive redundancy across the graph. For perspective, supplying the entire raw conversation context
to the language model—without any memory abstraction—amounts to roughly 26k tokens on average, 20
times less relative to Zep’s graph. Beyond token inefficiency, our experiments revealed significant operational
bottlenecks with Zep. After adding memories to Zep’s system, we observed that immediate memory retrieval
attempts often failed to answer our queries correctly. Interestingly, re-running identical searches after a
delay of several hours yielded considerably better results. This latency suggests that Zep’s graph construction
involves multiple asynchronous LLM calls and extensive background processing, making the memory system
impractical for real-time applications. In contrast, Mem0 graph construction completes in under a minute even
in worst-case scenarios, allowing users to immediately leverage newly added memories for query responses.
  *refs:* source=mem0.pdf
- **[turn 0, system]** These findings highlight that Zep not only replicates identical knowledge fragments across multiple
nodes, but also introduces significant operational delays. Our architectures—Mem0 and Mem0g—preserve the
same information at a fraction of the token cost and with substantially faster memory availability, offering a
more memory-efficient and operationally responsive representation.

5. Conclusion and Future Work
  *refs:* source=mem0.pdf
- **[turn 0, system]** We have introduced Mem0 and Mem0g, two complementary memory architectures that overcome the intrinsic
limitations of fixed context windows in LLMs. By dynamically extracting, consolidating, and retrieving
compact memory representations, Mem0 achieves state-of-the-art performance across single-hop and multi-hop
reasoning, while Mem0g’s graph-based extensions unlock significant gains in temporal and open-domain tasks.
On the LOCOMO benchmark, our methods deliver 5%, 11%, and 7% relative improvements in single-hop,
temporal, and multi-hop reasoning question types over best performing methods in respective question
type and reduce p95 latency by over 91% compared to full-context baselines—demonstrating a powerful
balance between precision and responsiveness. Mem0’s dense memory pipeline excels at rapid retrieval
for straightforward queries, minimizing token usage and computational overhead. In contrast, Mem0g’s
structured graph representations provide nuanced relational clarity, enabling complex event sequencing
and rich context integration without sacrificing practical efficiency. Together, they form a versatile memory
toolkit that adapts to diverse conversational demands while remaining deployable at scale.

Future research directions include optimizing graph operations to reduce the latency overhead in Mem0g,
exploring hierarchical memory architectures that blend efficiency with relational representation, and de-
veloping more sophisticated memory consolidation mechanisms inspired by human cognitive processes.

14
  *refs:* source=mem0.pdf
- **[turn 0, system]** Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

Additionally, extending our memory frameworks to domains beyond conversational scenarios, such as proce-
dural reasoning and multimodal interactions, would further validate their broader applicability. By addressing
the fundamental limitations of fixed context windows, our work represents a significant advancement toward
conversational AI systems capable of maintaining coherent, contextually rich interactions over extended
periods, much like their human counterparts.

6. Acknowledgments

We would like to express our sincere gratitude to Harsh Agarwal, Shyamal Anadkat, Prithvijit Chattopadhyay,
Siddesh Choudhary, Rishabh Jain, and Vaibhav Pandey for their invaluable insights and thorough reviews of
early drafts. Their constructive comments and detailed suggestions helped refine the manuscript, enhancing
both its clarity and overall quality. We deeply appreciate their generosity in dedicating time and expertise to
this work.

References

Anthropic. Model card and evaluations for claude models. Technical report, Anthropic, February 2025. URL

https://www.anthropic.com/news/claude-3-7-sonnet.

Jan Assmann. Communicative and cultural memory. In Cultural memories: The geographical point of view,

pages 15–27. Springer, 2011.

Aydar Bulatov, Yury Kuratov, and Mikhail Burtsev. Recurrent memory transformer. Advances in Neural

Information Processing Systems, 35:11079–11091, 2022.
  *refs:* source=mem0.pdf, 2025, 2011, 2022
- **[turn 0, system]** Prateek Chhikara, Jiarui Zhang, Filip Ilievski, Jonathan Francis, and Kaixin Ma. Knowledge-enhanced agents
for interactive text games. In Proceedings of the 12th Knowledge Capture Conference 2023, pages 157–165,
2023.

Fergus IM Craik and Janine M Jennings. Human memory. 1992.

Gaurav Goswami. Dissecting the metrics: How different evaluation approaches yield diverse results for

conversational ai. Authorea Preprints, 2025.

Tianyu Guo, Druv Pai, Yu Bai, Jiantao Jiao, Michael Jordan, and Song Mei. Active-dormant attention
heads: Mechanistically demystifying extreme-token phenomena in llms. In NeurIPS 2024 Workshop on
Mathematics of Modern Machine Learning, 2024.

Kostas Hatalis, Despina Christou, Joshua Myers, Steven Jones, Keith Lambert, Adam Amos-Binks, Zohreh
Dannenhauer, and Dustin Dannenhauer. Memory matters: The need to improve long-term memory in
llm-agents. In Proceedings of the AAAI Symposium Series, volume 2, pages 277–280, 2023.

Zihong He, Weizhe Lin, Hao Zheng, Fan Zhang, Matt W Jones, Laurence Aitchison, Xuhai Xu, Miao Liu,
Per Ola Kristensson, and Junxiao Shen. Human-inspired perspectives: A survey on ai long-term memory.
arXiv preprint arXiv:2411.00489, 2024.

Aaron Hurst, Adam Lerer, Adam P Goucher, Adam Perelman, Aditya Ramesh, Aidan Clark, AJ Ostrow, Akila
Welihinda, Alan Hayes, Alec Radford, et al. Gpt-4o system card. arXiv preprint arXiv:2410.21276, 2024.

15

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory
  *refs:* source=mem0.pdf, arXiv:2411.00489, arXiv:2410.21276, 2023, 1992, 2025, 2024
- **[turn 0, system]** Aaron Jaech, Adam Kalai, Adam Lerer, Adam Richardson, Ahmed El-Kishky, Aiden Low, Alec Helyar, Alek-
sander Madry, Alex Beutel, Alex Carney, et al. Openai o1 system card. arXiv preprint arXiv:2412.16720,
2024.

Kuang-Huei Lee, Xinyun Chen, Hiroki Furuta, John Canny, and Ian Fischer. A human-inspired reading
agent with gist memory of very long contexts. In International Conference on Machine Learning, pages
26396–26415. PMLR, 2024.

Lei Liu, Xiaoyan Yang, Yue Shen, Binbin Hu, Zhiqiang Zhang, Jinjie Gu, and Guannan Zhang. Think-in-
memory: Recalling and post-thinking enable llms with long-term memory. arXiv preprint arXiv:2311.08719,
2023.

Adyasha Maharana, Dong-Ho Lee, Sergey Tulyakov, Mohit Bansal, Francesco Barbieri, and Yuwei Fang.
Evaluating very long-term conversational memory of llm agents. In Proceedings of the 62nd Annual Meeting
of the Association for Computational Linguistics (Volume 1: Long Papers), pages 13851–13870, 2024.

Bodhisattwa Prasad Majumder, Bhavana Dalvi Mishra, Peter Jansen, Oyvind Tafjord, Niket Tandon, Li Zhang,
Chris Callison-Burch, and Peter Clark. Clin: A continually learning language agent for rapid task adaptation
and generalization. In First Conference on Language Modeling.

Elliot Nelson, Georgios Kollias, Payel Das, Subhajit Chaudhury, and Soham Dan. Needle in the haystack for

memory based large language models. arXiv preprint arXiv:2407.01437, 2024.

Charles Packer, Vivian Fang, Shishir_G Patil, Kevin Lin, Sarah Wooders, and Joseph_E Gonzalez. Memgpt:

Towards llms as operating systems. 2023.
  *refs:* source=mem0.pdf, arXiv:2412.16720, arXiv:2311.08719, arXiv:2407.01437, 2024, 2023
- **[turn 0, system]** Preston Rasmussen, Pavlo Paliychuk, Travis Beauvais, Jack Ryan, and Daniel Chalef. Zep: A temporal

knowledge graph architecture for agent memory. arXiv preprint arXiv:2501.13956, 2025.

Parth Sarthi, Salman Abdullah, Aditi Tuli, Shubh Khanna, Anna Goldie, and Christopher D Manning. Raptor:
Recursive abstractive processing for tree-organized retrieval. In The Twelfth International Conference on
Learning Representations, 2024.

Noah Shinn, Federico Cassano, Ashwin Gopinath, Karthik Narasimhan, and Shunyu Yao. Reflexion: Language
agents with verbal reinforcement learning. Advances in Neural Information Processing Systems, 36:8634–
8652, 2023.

Prabhjot Singh, Prateek Chhikara, and Jasmeet Singh. An ensemble approach for extractive text summa-
rization. In 2020 International Conference on Emerging Trends in Information Technology and Engineering
(ic-ETITE), pages 1–7. IEEE, 2020.

Arpita Soni, Rajeev Arora, Anoop Kumar, and Dheerendra Panwar. Evaluating domain coverage in low-
resource generative chatbots: A comparative study of open-domain and closed-domain approaches using
bleu scores. In 2024 International Conference on Electrical Electronics and Computing Technologies (ICEECT),
volume 1, pages 1–6. IEEE, 2024.

Gemini Team, Petko Georgiev, Ving Ian Lei, Ryan Burnell, Libin Bai, Anmol Gulati, Garrett Tanzer, Damien
Vincent, Zhufeng Pan, Shibo Wang, et al. Gemini 1.5: Unlocking multimodal understanding across millions
of tokens of context. arXiv preprint arXiv:2403.05530, 2024.
  *refs:* source=mem0.pdf, arXiv:2501.13956, arXiv:2403.05530, 2025, 2024, 2023, 2020
- **[turn 0, system]** Joan C Timoneda and Sebastián Vallejo Vera. Memory is all you need: Testing how model memory affects

llm performance in annotation tasks. arXiv preprint arXiv:2503.04874, 2025.

16

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

Wujiang Xu, Zujie Liang, Kai Mei, Hang Gao, Juntao Tan, and Yongfeng Zhang. A-mem: Agentic memory for

llm agents. arXiv preprint arXiv:2502.12110, 2025.

Yangyang Yu, Haohang Li, Zhi Chen, Yuechen Jiang, Yang Li, Denghui Zhang, Rong Liu, Jordan W Suchow,
and Khaldoun Khashanah. Finmem: A performance-enhanced llm trading agent with layered memory and
character design. In Proceedings of the AAAI Symposium Series, volume 3, pages 595–597, 2024.

Jiarui Zhang. Guided profile generation improves personalization with large language models. In Findings of

the Association for Computational Linguistics: EMNLP 2024, pages 4005–4016, 2024.

Jiarui Zhang, Filip Ilievski, Kaixin Ma, Jonathan Francis, and Alessandro Oltramari. A study of zero-shot

adaptation with commonsense knowledge. In AKBC, 2022.

Zeyu Zhang, Xiaohe Bo, Chen Ma, Rui Li, Xu Chen, Quanyu Dai, Jieming Zhu, Zhenhua Dong, and Ji-
Rong Wen. A survey on the memory mechanism of large language model based agents. arXiv preprint
arXiv:2404.13501, 2024.

Wanjun Zhong, Lianghong Guo, Qiqi Gao, He Ye, and Yanlin Wang. Memorybank: Enhancing large language
models with long-term memory. In Proceedings of the AAAI Conference on Artificial Intelligence, volume 38,
pages 19724–19731, 2024.

17

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

Appendix
  *refs:* source=mem0.pdf, arXiv:2503.04874, arXiv:2502.12110, arXiv:2404.13501, 2025, 2024, 2022
- **[turn 0, system]** A. Prompts

In developing our LLM-as-a-Judge prompt, we adapt elements from the prompt released by Packer et al.
(2023).

P romp t Templat e for LLM as a Judge

Your task is to label an answer to a question as "CORRECT" or "WRONG". You will be given
the following data:
(ground truth) answer, (3) a generated answer which you will score as CORRECT/WRONG.

(1) a question (posed by one user to another user), (2) a ‘gold’

The point of the question is to ask about something one user should know about the other
user based on their prior conversations. The gold answer will usually be a concise and
short answer that includes the referenced topic, for example:
Question: Do you remember what I got the last time I went to Hawaii?
Gold answer:
The generated answer might be much longer, but you should be generous with your grading
- as long as it touches on the same topic as the gold answer, it should be counted as
CORRECT.

A shell necklace

For time related questions, the gold answer will be a specific date, month, year, etc. The
generated answer might be much longer or use relative time references (like ‘last Tuesday’
or ‘next month’), but you should be generous with your grading - as long as it refers to
the same date or time period as the gold answer, it should be counted as CORRECT. Even if
the format differs (e.g., ‘May 7th’ vs ‘7 May’), consider it CORRECT if it’s the same date.

Now it’s time for the real question:
Question: {question}
Gold answer:
Generated answer:

{generated_answer}

{gold_answer}
  *refs:* source=mem0.pdf, Packer et al., 2023
- **[turn 0, system]** First, provide a short (one sentence) explanation of your reasoning, then finish with
CORRECT or WRONG. Do NOT include both CORRECT and WRONG in your response, or it will break
the evaluation script.

Just return the label CORRECT or WRONG in a json format with the key as "label".

18

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

P romp t Templat e for Re sult s Gener ation (M e m 0 )

You are an intelligent memory assistant tasked with retrieving accurate information from
conversation memories.

# CONTEXT:

You have access to memories from two speakers in a conversation. These memories contain
timestamped information that may be relevant to answering the question.
  *refs:* source=mem0.pdf
- **[turn 0, system]** # INSTRUCTIONS:

1. Carefully analyze all provided memories from both speakers
2. Pay special attention to the timestamps to determine the answer
3. If the question asks about a specific event or fact, look for direct evidence in the
memories
4. If the memories contain contradictory information, prioritize the most recent memory
5. If there is a question about time references (like "last year", "two months ago",
etc.), calculate the actual date based on the memory timestamp. For example, if a memory
from 4 May 2022 mentions "went to India last year," then the trip occurred in 2021.
6. Always convert relative time references to specific dates, months, or years. For
example, convert "last year" to "2022" or "two months ago" to "March 2023" based on the
Ignore the reference while answering the question.
memory timestamp.
7. Focus only on the content of the memories from both speakers. Do not confuse character
names mentioned in memories with the actual users who created those memories.
8. The answer should be less than 5-6 words.
  *refs:* source=mem0.pdf, 2022, 2021, 2023
- **[turn 0, system]** # APPROACH (Think step by step):

1. First, examine all memories that contain information related to the question
2. Examine the timestamps and content of these memories carefully
3. Look for explicit mentions of dates, times, locations, or events that answer the
question
4. If the answer requires calculation (e.g., converting relative time references), show
your work
5. Formulate a precise, concise answer based solely on the evidence in the memories
6. Double-check that your answer directly addresses the question asked
7. Ensure your final answer is specific and avoids vague time references

Memories for user {speaker_1_user_id}:
{speaker_1_memories}

Memories for user {speaker_2_user_id}:
{speaker_2_memories}

Question: {question}

Answer:

19

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

P romp t Templat e for Re sult s Gener ation (M e m 0 g )

(same as previous )
  *refs:* source=mem0.pdf
- **[turn 0, system]** # APPROACH (Think step by step):

1. First, examine all memories that contain information related to the question
2. Examine the timestamps and content of these memories carefully
3. Look for explicit mentions of dates, times, locations, or events that answer the
question
4. If the answer requires calculation (e.g., converting relative time references), show
your work
5. Analyze the knowledge graph relations to understand the user’s knowledge context
6. Formulate a precise, concise answer based solely on the evidence in the memories
7. Double-check that your answer directly addresses the question asked
8. Ensure your final answer is specific and avoids vague time references

Memories for user {speaker_1_user_id}:
{speaker_1_memories}

Relations for user {speaker_1_user_id}:
{speaker_1_graph_memories}

Memories for user {speaker_2_user_id}:
{speaker_2_memories}

Relations for user {speaker_2_user_id}:
{speaker_2_graph_memories}

Question: {question}

Answer:

P romp t Templat e for Ope nAI ChatGP T

Can you please extract relevant information from this conversation and create memory
entries for each user mentioned?
addition to the timestamp provided for future reference and personalized interactions.

Please store these memories in your knowledge base in

(1:56 pm on 8 May, 2023) Caroline: Hey Mel! Good to see you! How have you been?
(1:56 pm on 8 May, 2023) Melanie:
kids & work.
What’s up with you?
(1:56 pm on 8 May, 2023) Caroline: I went to a LGBTQ support group yesterday and it was so
powerful.
...

Hey Caroline! Good to see you! I’m swamped with the
Anything new?

20
  *refs:* source=mem0.pdf, 2023
- **[turn 0, system]** 5:

6:

7:

8:

9:

10:

11:

12:

13:

14:

15:

16:

17:

18:

19:

20:

25:

26:

27:

28:

29:

30:

31:

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

B. Algorithm

Algorithm 1 Memory Management System: Update Operations

1: Input: Set of retrieved memories F, Existing memory store M = {m1, m2, . . . , mn}
2: Output: Updated memory store M
3: procedure Updat eMemory(F, M)
4:

for each fact f ∈ F do

′

operation ← ClassifyOper ation( f , M)

classification

if operation = ADD then

id ← GenerateUniqueID()
M ← M ∪ {(id, f , "ADD")}
else if operation = UPDATE then

▷ Execute appropriate operation based on

▷ Add new fact with unique identifier

mi ← FindRelatedMemory( f , M)
if InformationContent( f ) > InformationContent(mi) then

M ← (M \ {mi}) ∪ {(idi, f , "UPDATE")}

end if

▷ Replace with richer information

else if operation = DELETE then

mi ← FindContradictedMemory( f , M)
M ← M \ {mi}

else if operation = NOOP then
No operation performed

end if

end for
return M

21:
22: end procedure
23: function ClassifyOper ation( f , M)
if ¬SemanticallySimilar( f , M) then
24:

return ADD

else if Contradicts( f , M) then

return DELETE

else if Augments( f , M) then

return UPDATE

else

return NOOP

▷ Remove contradicted information

▷ Fact already exists or is irrelevant

▷ New information not present in memory

▷ Information conflicts with existing memory

▷ Enhances existing information in memory

▷ No change required

end if

32:
33: end function

C. Selected Baselines
  *refs:* source=mem0.pdf
- **[turn 0, system]** LoCoMo The LoCoMo framework implements a sophisticated memory pipeline that enables LLM agents to
maintain coherent, long-term conversations. At its core, the system divides memory into short-term and
long-term components. After each conversation session, agents generate summaries (stored as short-term
memory) that distill key information from that interaction. Simultaneously, individual conversation turns are

21

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

transformed into ‘observations’ - factual statements about each speaker’s persona and life events that are
stored in long-term memory with references to the specific dialog turns that produced them. When generating
new responses, agents leverage both the most recent session summary and selectively retrieve relevant
observations from their long-term memory. This dual-memory approach is further enhanced by incorporating
a temporal event graph that tracks causally connected life events occurring between conversation sessions.
By conditioning responses on retrieved memories, current conversation context, persona information, and
intervening life events, the system enables agents to maintain consistent personalities and recall important
details across conversations spanning hundreds of turns and dozens of sessions.
  *refs:* source=mem0.pdf
- **[turn 0, system]** ReadAgent ReadAgent addresses the fundamental limitations of LLMs by emulating how humans process
lengthy texts through a sophisticated three-stage pipeline. First, in Episode Pagination, the system intelligently
segments text at natural cognitive boundaries rather than arbitrary cutoffs. Next, during Memory Gisting,
it distills each segment into concise summaries that preserve essential meaning while drastically reducing
token count—similar to how human memory retains the substance of information without verbatim recall.
Finally, when tasked with answering questions, the Interactive Lookup mechanism examines these gists
and strategically retrieves only the most relevant original text segments for detailed processing. This
human-inspired approach enables LLMs to effectively manage documents up to 20 times longer than their
normal context windows. By balancing global understanding through gists with selective attention to
details, ReadAgent achieves both computational efficiency and improved comprehension, demonstrating that
mimicking human cognitive processes can significantly enhance AI text processing capabilities.
  *refs:* source=mem0.pdf
- **[turn 0, system]** MemoryBank The MemoryBank system enhances LLMs with long-term memory through a sophisticated
three-part pipeline. At its core, the Memory Storage component warehouses detailed conversation logs,
hierarchical event summaries, and evolving user personality profiles. When a new interaction occurs, the
Memory Retrieval mechanism employs a dual-tower dense retrieval model to extract contextually relevant
past information. The Memory Updating component, provides a human-like forgetting mechanism where
memories strengthen when recalled and naturally decay over time if unused. This comprehensive approach
enables AI companions to recall pertinent information, maintain contextual awareness across extended
interactions, and develop increasingly accurate user portraits, resulting in more personalized and natural
long-term conversations.
  *refs:* source=mem0.pdf
- **[turn 0, system]** MemGPT The MemGPT system introduces an operating system-inspired approach to overcome the context
window limitations inherent in LLMs. At its core, MemGPT employs a sophisticated memory management
pipeline consisting of three key components: a hierarchical memory system, self-directed memory operations,
and an event-based control flow mechanism. The system divides available memory into ‘main context’
(analogous to RAM in traditional operating systems) and ‘external context’ (analogous to disk storage).
The main context—which is bound by the LLM’s context window—contains system instructions, recent
conversation history, and working memory that can be modified by the model. The external context stores
unlimited information outside the model’s immediate context window, including complete conversation
histories and archival data. When the LLM needs information not present in main context, it can initiate
function calls to search, retrieve, or modify content across these memory tiers, effectively ‘paging’ relevant
information in and out of its limited context window. This OS-inspired architecture enables MemGPT to
maintain conversational coherence over extended interactions, manage documents that exceed standard
context limits, and perform multi-hop information retrieval tasks—all while operating with fixed-context

22

Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

models. The system’s ability to intelligently manage its own memory resources provides the illusion of
infinite context, significantly extending what’s possible with current LLM technology.
  *refs:* source=mem0.pdf
- **[turn 0, system]** A-Mem The A-Mem model introduces an agentic memory system designed for LLM agents. This system
dynamically structures and evolves memories through interconnected notes. Each note captures interactions
enriched with structured attributes like keywords, contextual descriptions, and tags generated by the
LLM. Upon creating a new memory, A-MEM uses semantic embeddings to retrieve relevant existing notes,
then employs an LLM-driven approach to establish meaningful links based on similarities and shared
attributes. Crucially, the memory evolution mechanism updates existing notes dynamically, refining their
contextual information and attributes whenever new relevant memories are integrated. Thus, memory
structure continually evolves, allowing richer and contextually deeper connections among memories. Retrieval
from memory is conducted through semantic similarity, providing relevant historical context during agent
interactions

23
  *refs:* source=mem0.pdf
- **[turn 0, system]** 5
2
0
2

n
a
J

0
2

]
L
C
.
s
c
[

1
v
6
5
9
3
1
.
1
0
5
2
:
v
i
X
r
a

ZEP: A TEMPORAL KNOWLEDGE GRAPH ARCHITECTURE FOR
AGENT MEMORY

Preston Rasmussen
Zep AI
preston@getzep.com

Pavlo Paliychuk
Zep AI
paul@getzep.com

Travis Beauvais
Zep AI
travis@getzep.com

Jack Ryan
Zep AI
jack@getzep.com

Daniel Chalef
Zep AI
daniel@getzep.com

ABSTRACT
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** We introduce Zep, a novel memory layer service for AI agents that outperforms the current state-
of-the-art system, MemGPT, in the Deep Memory Retrieval (DMR) benchmark. Additionally, Zep
excels in more comprehensive and challenging evaluations than DMR that better reﬂect real-world
enterprise use cases. While existing retrieval-augmented generation (RAG) frameworks for large
language model (LLM)-based agents are limited to static document retrieval, enterprise applications
demand dynamic knowledge integration from diverse sources including ongoing conversations and
business data. Zep addresses this fundamental limitation through its core component Graphiti—a
temporally-aware knowledge graph engine that dynamically synthesizes both unstructured conver-
sational data and structured business data while maintaining historical relationships. In the DMR
benchmark, which the MemGPT team established as their primary evaluation metric, Zep demon-
strates superior performance (94.8% vs 93.4%). Beyond DMR, Zep’s capabilities are further vali-
dated through the more challenging LongMemEval benchmark, which better reﬂects enterprise use
cases through complex temporal reasoning tasks. In this evaluation, Zep achieves substantial results
with accuracy improvements of up to 18.5% while simultaneously reducing response latency by
90% compared to baseline implementations. These results are particularly pronounced in enterprise-
critical tasks such as cross-session information synthesis and long-term context maintenance, demon-
strating Zep’s effectiveness for deployment in real-world applications.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** 1 Introduction

The impact of transformer-based large language models (LLMs) on industry and research communities has garnered
signiﬁcant attention in recent years [1]. A major application of LLMs has been the development of chat-based agents.
However, these agents’ capabilities are limited by the LLMs’ context windows, effective context utilization, and
knowledge gained during pre-training. Consequently, additional context is required to provide out-of-domain (OOD)
knowledge and reduce hallucinations.

Retrieval-Augmented Generation (RAG) has emerged as a key area of interest in LLM-based applications. RAG
leverages Information Retrieval (IR) techniques pioneered over the last ﬁfty years[2] to supply necessary domain
knowledge to LLMs.

Current approaches using RAG have focused on broad domain knowledge and largely static corpora—that is, docu-
ment contents added to a corpus seldom change. For agents to become pervasive in our daily lives, autonomously
solving problems from trivial to highly complex, they will need access to a large corpus of continuously evolving data
from users’ interactions with the agent, along with related business and world data. We view empowering agents with
this broad and dynamic "memory" as a crucial building block to actualize this vision, and we argue that current RAG
approaches are unsuitable for this future. Since entire conversation histories, business datasets, and other domain-
speciﬁc content cannot ﬁt effectively inside LLM context windows, new approaches need to be developed for agent

Using Knowledge Graphs to power LLM-Agent Memory
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** memory. Adding memory to LLM-powered agents isn’t a new idea—this concept has been explored previously in
MemGPT [3].

Recently, Knowledge Graphs (KGs) have been employed to enhance RAG architectures to address many of the short-
comings of traditional IR techniques[4].
In this paper, we introduce Zep[5], a memory layer service powered by
Graphiti[6], a dynamic, temporally-aware knowledge graph engine. Zep ingests and synthesizes both unstructured
message data and structured business data. The Graphiti KG engine dynamically updates the knowledge graph with
new information in a non-lossy manner, maintaining a timeline of facts and relationships, including their periods of
validity. This approach enables the knowledge graph to represent a complex, evolving world.

As Zep is a production system, we’ve focused heavily on the accuracy, latency, and scalability of its memory retrieval
mechanisms. We evaluate these mechanisms’ efﬁcacy using two existing benchmarks: a Deep Memory Retrieval task
(DMR) from MemGPT[3], as well as the LongMemEval benchmark[7].

2 Knowledge Graph Construction

In Zep, memory is powered by a temporally-aware dynamic knowledge graph G = (N , E, φ), where N represents
nodes, E represents edges, and φ : E → N × N represents a formal incidence function. This graph comprises three
hierarchical tiers of subgraphs: an episode subgraph, a semantic entity subgraph, and a community subgraph.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** • Episode Subgraph Ge: Episodic nodes (episodes), ni ∈ Ne, contain raw input data in the form of mes-
sages, text, or JSON. Episodes serve as a non-lossy data store from which semantic entities and relations are
extracted. Episodic edges, ei ∈ Ee ⊆ φ∗(Ne × Ns), connect episodes to their referenced semantic entities.
• Semantic Entity Subgraph Gs: The semantic entity subgraph builds upon the episode subgraph. Entity
nodes (entities), ni ∈ Ns, represent entities extracted from episodes and resolved with existing graph entities.
Entity edges (semantic edges), ei ∈ Es ⊆ φ∗(Ns × Ns), represent relationships between entities extracted
from episodes.

• Community Subgraph Gc: The community subgraph forms the highest level of Zep’s knowledge graph.
Community nodes (communities), ni ∈ Nc, represent clusters of strongly connected entities. Communities
contain high-level summarizations of these clusters and represent a more comprehensive, interconnected view
of Gs’s structure. Community edges, ei ∈ Ec ⊆ φ∗(Nc × Ns), connect communities to their entity members.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** The dual storage of both raw episodic data and derived semantic entity information mirrors psychological models of
human memory. These models distinguish between episodic memory, which represents distinct events, and semantic
memory, which captures associations between concepts and their meanings [8]. This approach enables LLM agents
using Zep to develop more sophisticated and nuanced memory structures that better align with our understanding of
human memory systems. Knowledge graphs provide an effective medium for representing these memory structures,
and our implementation of distinct episodic and semantic subgraphs draws from similar approaches in AriGraph [9].

Our use of community nodes to represent high-level structures and domain concepts builds upon work from GraphRAG
[4], enabling a more comprehensive global understanding of the domain. The resulting hierarchical organiza-
tion—from episodes to facts to entities to communities—extends existing hierarchical RAG strategies [10][11].

2.1 Episodes

Zep’s graph construction begins with the ingestion of raw data units called Episodes. Episodes can be one of three
core types: message, text, or JSON. While each type requires speciﬁc handling during graph construction, this paper
focuses on the message type, as our experiments center on conversation memory. In our context, a message consists
of relatively short text (several messages can ﬁt within an LLM context window) along with the associated actor who
produced the utterance.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** Each message includes a reference timestamp tref indicating when the message was sent. This temporal information
enables Zep to accurately identify and extract relative or partial dates mentioned in the message content (e.g., "next
Thursday," "in two weeks," or "last summer"). Zep implements a bi-temporal model, where timeline T represents the
chronological ordering of events, and timeline T ′ represents the transactional order of Zep’s data ingestion. While
the T ′ timeline serves the traditional purpose of database auditing, the T timeline provides an additional dimension
for modeling the dynamic nature of conversational data and memory. This bi-temporal approach represents a novel
advancement in LLM-based knowledge graph construction and underlies much of Zep’s unique capabilities compared
to previous graph-based RAG proposals.

2

Using Knowledge Graphs to power LLM-Agent Memory

The episodic edges, Ee, connect episodes to their extracted entity nodes. Episodes and their derived semantic edges
maintain bidirectional indices that track the relationships between edges and their source episodes. This design rein-
forces the non-lossy nature of Graphiti’s episodic subgraph by enabling both forward and backward traversal: semantic
artifacts can be traced to their sources for citation or quotation, while episodes can quickly retrieve their relevant enti-
ties and facts. While these connections are not directly examined in this paper’s experiments, they will be explored in
future work.

2.2 Semantic Entities and Facts

2.2.1 Entities
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** ntity extraction represents the initial phase of episode processing. During ingestion, the system processes both the
current message content and the last n messages to provide context for named entity recognition. For this paper and
in Zep’s general implementation, n = 4, providing two complete conversation turns for context evaluation. Given our
focus on message processing, the speaker is automatically extracted as an entity. Following initial entity extraction, we
employ a reﬂection technique inspired by reﬂexion[12] to minimize hallucinations and enhance extraction coverage.
The system also extracts an entity summary from the episode to facilitate subsequent entity resolution and retrieval
operations.

After extraction, the system embeds each entity name into a 1024-dimensional vector space. This embedding enables
the retrieval of similar nodes through cosine similarity search across existing graph entity nodes. The system also per-
forms a separate full-text search on existing entity names and summaries to identify additional candidate nodes. These
candidate nodes, together with the episode context, are then processed through an LLM using our entity resolution
prompt. When the system identiﬁes a duplicate entity, it generates an updated name and summary.

Following entity extraction and resolution, the system incorporates the data into the knowledge graph using predeﬁned
Cypher queries. We chose this approach over LLM-generated database queries to ensure consistent schema formats
and reduce the potential for hallucinations.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** Selected prompts for graph construction are provided in the appendix.

2.2.2 Facts

or each fact containing its key predicate. Importantly, the same fact can be extracted multiple times between different
entities, enabling Graphiti to model complex multi-entity facts through an implementation of hyper-edges.

Following extraction, the system generates embeddings for facts in preparation for graph integration. The system
performs edge deduplication through a process similar to entity resolution. The hybrid search for relevant edges is
constrained to edges existing between the same entity pairs as the proposed new edge. This constraint not only prevents
erroneous combinations of similar edges between different entities but also signiﬁcantly reduces the computational
complexity of the deduplication process by limiting the search space to a subset of edges relevant to the speciﬁc entity
pair.

2.2.3 Temporal Extraction and Edge Invalidation

A key differentiating feature of Graphiti compared to other knowledge graph engines is its capacity to manage dynamic
information updates through temporal extraction and edge invalidation processes.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** The system extracts temporal information about facts from the episode context using tref. This enables accurate ex-
traction and datetime representation of both absolute timestamps (e.g., "Alan Turing was born on June 23, 1912") and
relative timestamps (e.g., "I started my new job two weeks ago"). Consistent with our bi-temporal modeling approach,
the system tracks four timestamps: t′created and t′expired ∈ T ′ monitor when facts are created or invalidated in the
system, while tvalid and tinvalid ∈ T track the temporal range during which facts held true. These temporal data points
are stored on edges alongside other fact information.

The introduction of new edges can invalidate existing edges in the database. The system employs an LLM to compare
new edges against semantically related existing edges to identify potential contradictions. When the system identi-
ﬁes temporally overlapping contradictions, it invalidates the affected edges by setting their tinvalid to the tvalid of the
invalidating edge. Following the transactional timeline T ′, Graphiti consistently prioritizes new information when
determining edge invalidation.

This comprehensive approach enables the dynamic addition of data to Graphiti as conversations evolve, while main-
taining both current relationship states and historical records of relationship evolution over time.

3

Using Knowledge Graphs to power LLM-Agent Memory

2.3 Communities
  *refs:* source=zep-temporal-knowledge-graph.pdf, 1912
- **[turn 0, system]** After establishing the episodic and semantic subgraphs, the system constructs the community subgraph through com-
munity detection. While our community detection approach builds upon the technique described in GraphRAG[4],
we employ a label propagation algorithm [13] rather than the Leiden algorithm [14]. This choice was inﬂuenced by
label propagation’s straightforward dynamic extension, which enables the system to maintain accurate community
representations for longer periods as new data enters the graph, delaying the need for complete community refreshes.

The dynamic extension implements the logic of a single recursive step in label propagation. When the system adds
a new entity node ni ∈ Ns to the graph, it surveys the communities of neighboring nodes. The system assigns
the new node to the community held by the plurality of its neighbors, then updates the community summary and
graph accordingly. While this dynamic updating enables efﬁcient community extension as data ﬂows into the system,
the resulting communities gradually diverge from those that would be generated by a complete label propagation
run. Therefore, periodic community refreshes remain necessary. However, this dynamic updating strategy provides a
practical heuristic that signiﬁcantly reduces latency and LLM inference costs.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** Following [4], our community nodes contain summaries derived through an iterative map-reduce-style summarization
of member nodes. However, our retrieval methods differ substantially from GraphRAG’s map-reduce approach [4].
To support our retrieval methodology, we generate community names containing key terms and relevant subjects from
the community summaries. These names are embedded and stored to enable cosine similarity searches.

3 Memory Retrieval

The memory retrieval system in Zep provides powerful, complex, and highly conﬁgurable functionality. At a high
level, the Zep graph search API implements a function f : S → S that accepts a text-string query α ∈ S as input and
returns a text-string context β ∈ S as output. The output β contains formatted data from nodes and edges required for
an LLM agent to generate an accurate response to query α. The process f (α) → β comprises three distinct steps:

• Search (ϕ): The process begins by identifying candidate nodes and edges potentially containing relevant
information. While Zep employs multiple distinct search methods, the overall search function can be repre-
sented as ϕ : S → E n
c . Thus, ϕ transforms a query into a 3-tuple containing lists of semantic
edges, entity nodes, and community nodes—the three graph types containing relevant textual information.
• Reranker (ρ): The second step reorders search results. A reranker function or model accepts a list of search

s × N n

s × N n

results and produces a reordered version of those results: ρ : ϕ(α), ... → E n

s × N n

s × N n
c .
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** • Constructor (χ): The ﬁnal step, the constructor, transforms the relevant nodes and edges into text context:
s × N cn → S. For each ei ∈ Es, χ returns the fact and tvalid, tinvalid ﬁelds; for each ni ∈ Ns,

χ : E n
the name and summary ﬁelds; and for each ni ∈ Nc, the summary ﬁeld.

s × N n

With these deﬁnitions established, we can express f as a composition of these three components: f (α) =
χ(ρ(ϕ(α))) = β.

Sample context string template:

FACTS and ENTITIES represent relevant context to the current conversation.
These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during
this time.
format: FACT (Date range: from - to)
<FACTS>
{facts}
</FACTS>
These are the most relevant entities
ENTITY_NAME: entity summary
<ENTITIES>
{entities}
</ENTITIES>

3.1 Search

Zep implements three search functions: cosine semantic similarity search (ϕcos), Okapi BM25 full-text search (ϕbm25),
and breadth-ﬁrst search (ϕbfs). The ﬁrst two functions utilize Neo4j’s implementation of Lucene [15][16]. Each

4

Using Knowledge Graphs to power LLM-Agent Memory
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** search function offers distinct capabilities in identifying relevant documents, and together they provide comprehensive
coverage of candidate results before reranking. The search ﬁeld varies across the three object types: for Es, we search
the fact ﬁeld; for Ns, the entity name; and for Nc, the community name, which comprises relevant keywords and
phrases covered in the community. While developed independently, our community search approach parallels the
high-level key search methodology in LightRAG [17]. The hybridization of LightRAG’s approach with graph-based
systems like Graphiti presents a promising direction for future research.

While cosine similarity and full-text search methodologies are well-established in RAG [18], breadth-ﬁrst search over
knowledge graphs has received limited attention in the RAG domain, with notable exceptions in graph-based RAG
systems such as AriGraph [9] and Distill-SynthKG [19]. In Graphiti, the breadth-ﬁrst search enhances initial search
results by identifying additional nodes and edges within n-hops. Moreover, ϕbfs can accept nodes as parameters for the
search, enabling greater control over the search function. This functionality proves particularly valuable when using
recent episodes as seeds for the breadth-ﬁrst search, allowing the system to incorporate recently mentioned entities
and relationships into the retrieved context.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** The three search methods each target different aspects of similarity: full-text search identiﬁes word similarities, cosine
similarity captures semantic similarities, and breadth-ﬁrst search reveals contextual similarities—where nodes and
edges closer in the graph appear in more similar conversational contexts. This multi-faceted approach to candidate
result identiﬁcation maximizes the likelihood of discovering optimal context.

3.2 Reranker

While the initial search methods aim to achieve high recall, rerankers serve to increase precision by prioritizing the
most relevant results. Zep supports existing reranking approaches such as Reciprocal Rank Fusion (RRF) [20] and
Maximal Marginal Relevance (MMR) [21]. Additionally, Zep implements a graph-based episode-mentions reranker
that prioritizes results based on the frequency of entity or fact mentions within a conversation, enabling a system
where frequently referenced information becomes more readily accessible. The system also includes a node distance
reranker that reorders results based on their graph distance from a designated centroid node, providing context local-
ized to speciﬁc areas of the knowledge graph. The system’s most sophisticated reranking capability employs cross-
encoders—LLMs that generate relevance scores by evaluating nodes and edges against queries using cross-attention,
though this approach incurs the highest computational cost.

4 Experiments
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** This section analyzes two experiments conducted using LLM-memory based benchmarks. The ﬁrst evaluation employs
the Deep Memory Retrieval (DMR) task developed in [3], which uses a 500-conversation subset of the Multi-Session
Chat dataset introduced in "Beyond Goldﬁsh Memory: Long-Term Open-Domain Conversation" [22]. The second
evaluation utilizes the LongMemEval benchmark from "LongMemEval: Benchmarking Chat Assistants on Long-Term
Interactive Memory" [7]. Speciﬁcally, we use the LongMemEvals dataset, which provides an extensive conversation
context of on average 115,000 tokens.

For both experiments, we integrate the conversation history into a Zep knowledge graph through Zep’s APIs. We
then retrieve the 20 most relevant edges (facts) and entity nodes (entity summaries) using the techniques described in
Section 3. The system reformats this data into a context string, matching the functionality provided by Zep’s memory
APIs.

While these experiments demonstrate key retrieval capabilities of Graphiti, they represent a subset of the system’s
full search functionality. This focused scope enables clear comparison with existing benchmarks while reserving the
exploration of additional knowledge graph capabilities for future work.

4.1 Choice of models
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** Our experimental implementation employs the BGE-m3 models from BAAI for both reranking and embedding tasks
[23] [24]. For graph construction and response generation, we utilize gpt-4o-mini-2024-07-18 for graph construction,
and both gpt-4o-mini-2024-07-18 and gpt-4o-2024-11-20 for the chat agent generating responses to provided context.

To ensure direct comparability with MemGPT’s DMR results, we also conducted the DMR evaluation using gpt-4-
turbo-2024-04-09.

The experimental notebooks will be made publicly available through our GitHub repository, and relevant experimental
prompts are included in the Appendix.

5

Using Knowledge Graphs to power LLM-Agent Memory

Table 1: Deep Memory Retrieval

Model

Memory
Recursive Summarization† gpt-4-turbo
gpt-4-turbo
Conversation Summaries
MemGPT†
gpt-4-turbo
gpt-4-turbo
Full-conversation
gpt-4-turbo
Zep

Conversation Summaries
Full-conversation
Zep
† Results reported in [3].

gpt-4o-mini
gpt-4o-mini
gpt-4o-mini

Score

35.3%
78.6%
93.4%
94.4%
94.8%

88.0%
98.0%
98.2%

4.2 Deep Memory Retrieval (DMR)

The Deep Memory Retrieval evaluation, introduced by [3], comprises 500 multi-session conversations, each containing
5 chat sessions with up to 12 messages per session. Each conversation includes a question/answer pair for memory
evaluation. The MemGPT framework [3] currently leads performance metrics with 93.4% accuracy using gpt-4-turbo,
a signiﬁcant improvement over the 35.3% baseline achieved through recursive summarization.
  *refs:* source=zep-temporal-knowledge-graph.pdf, 2024
- **[turn 0, system]** To establish comparative baselines, we implemented two common LLM memory approaches: full-conversation con-
text and session summaries. Using gpt-4-turbo, the full-conversation baseline achieved 94.4% accuracy, slightly sur-
passing MemGPT’s reported results, while the session summary baseline achieved 78.6%. When using gpt-4o-mini,
both approaches showed improved performance: 98.0% for full-conversation and 88.0% for session summaries. We
were unable to reproduce MemGPT’s results using gpt-4o-mini due to insufﬁcient methodological details in their
published work.

We then evaluated Zep’s performance by ingesting the conversations and using its search functions to retrieve the top
10 most relevant nodes and edges. An LLM judge compared the agent’s responses to the provided golden answers.
Zep achieved 94.8% accuracy with gpt-4-turbo and 98.2% with gpt-4o-mini, showing marginal improvements over
both MemGPT and the respective full-conversation baselines. However, these results must be contextualized: each
conversation contains only 60 messages, easily ﬁtting within current LLM context windows.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** The limitations of the DMR evaluation extend beyond its small scale. Our analysis revealed signiﬁcant weaknesses
in the benchmark’s design. The evaluation relies exclusively on single-turn, fact-retrieval questions that fail to assess
complex memory understanding. Many questions contain ambiguous phrasing, referencing concepts like "favorite
drink to relax with" or "weird hobby" that were not explicitly characterized as such in the conversations. Most critically,
the dataset poorly represents real-world enterprise use cases for LLM agents. The high performance achieved by
simple full-context approaches using modern LLMs further highlights the benchmark’s inadequacy for evaluating
memory systems.

This inadequacy is further emphasized by ﬁndings in [7], which demonstrate rapidly declining LLM performance on
the LongMemEval benchmark as conversation length increases. The LongMemEval dataset [7] addresses many of
these shortcomings by presenting longer, more coherent conversations that better reﬂect enterprise scenarios, along
with more diverse evaluation questions.

4.3 LongMemEval (LME)
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** We evaluated Zep using the LongMemEvals dataset, which provides conversations and questions representative of real-
world business applications of LLM agents. The LongMemEvals dataset presents signiﬁcant challenges to existing
LLMs and commercial memory solutions [7], with conversations averaging approximately 115,000 tokens in length.
This length, while substantial, remains within the context windows of current frontier models, enabling us to establish
meaningful baselines for evaluating Zep’s performance.

The dataset incorporates six distinct question types: single-session-user, single-session-assistant, single-session-
preference, multi-session, knowledge-update, and temporal-reasoning. These categories are not uniformly distributed
throughout the dataset; for detailed distribution information, we refer readers to [7].

We conducted all experiments between December 2024 and January 2025. We performed testing using a consumer
laptop from a residential location in Boston, MA, connecting to Zep’s service hosted in AWS us-west-2. This dis-

6

Using Knowledge Graphs to power LLM-Agent Memory

tributed architecture introduced additional network latency when evaluating Zep’s performance, though this latency
was not present in our baseline evaluations.

For answer evaluation, we employed GPT-4o with the question-speciﬁc prompts provided in [7], which have demon-
strated high correlation with human evaluators.

4.3.1 LongMemEval and MemGPT
  *refs:* source=zep-temporal-knowledge-graph.pdf, 2024, 2025
- **[turn 0, system]** To establish a comparative benchmark between Zep and the current state-of-the-art MemGPT system [3], we attempted
to evaluate MemGPT using the LongMemEval dataset. Given that the current MemGPT framework does not support
direct ingestion of existing message histories, we implemented a workaround by adding conversation messages to the
archival history. However, we were unable to achieve successful question responses using this approach. We look
forward to seeing evaluations of this benchmark by other research teams, as comparative performance data would
beneﬁt the broader development of LLM memory systems.

4.3.2 LongMemEval results

Zep demonstrates substantial improvements in both accuracy and latency compared to the baseline across both model
variants. Using gpt-4o-mini, Zep achieved a 15.2% accuracy improvement over the baseline, while gpt-4o showed an
18.5% improvement. The reduced prompt size also led to signiﬁcant latency cost reductions compared to the baseline
implementations.

Table 2: LongMemEvals

Memory

Model

Score

Latency Latency IQR Avg Context Tokens

Full-context
Zep
Full-context
Zep

gpt-4o-mini
gpt-4o-mini
gpt-4o
gpt-4o

55.4% 31.3 s
63.8% 3.20 s
60.2% 28.9 s
71.2% 2.58 s

8.76 s
1.31 s
6.01 s
0.684 s

115k
1.6k
115k
1.6k
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** Analysis by question type reveals that gpt-4o-mini with Zep showed improvements in four of the six categories,
with the most substantial gains in complex question types: single-session-preference, multi-session, and temporal-
reasoning. When using gpt-4o, Zep further demonstrated improved performance in the knowledge-update category,
highlighting its effectiveness with more capable models. However, additional development may be needed to improve
less capable models’ understanding of Zep’s temporal data.

Table 3: LongMemEvals Question Type Breakdown

Question Type

Model

Full-context Zep

Delta

single-session-preference
single-session-assistant
temporal-reasoning
multi-session
knowledge-update
single-session-user

single-session-preference
single-session-assistant
temporal-reasoning
multi-session
knowledge-update
single-session-user

gpt-4o-mini
gpt-4o-mini
gpt-4o-mini
gpt-4o-mini
gpt-4o-mini
gpt-4o-mini

gpt-4o
gpt-4o
gpt-4o
gpt-4o
gpt-4o
gpt-4o

30.0%
81.8%
36.5%
40.6%
76.9%
81.4%

20.0%
94.6%
45.1%
44.3%
78.2%
81.4%

53.3% 77.7%↑
75.0% 9.06%↓
54.1% 48.2%↑
47.4% 16.7%↑
74.4% 3.36%↓
92.9% 14.1%↑

56.7% 184%↑
80.4% 17.7%↓
62.4% 38.4%↑
57.9% 30.7%↑
83.3% 6.52%↑
92.9% 14.1%↑

These results demonstrate Zep’s ability to enhance performance across model scales, with the most pronounced im-
provements observed in complex and nuanced question types when paired with more capable models. The latency
improvements are particularly noteworthy, with Zep reducing response times by approximately 90% while maintain-
ing higher accuracy.

7
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** Using Knowledge Graphs to power LLM-Agent Memory

The decrease in performance for single-session-assistant questions—17.7% for gpt-4o and 9.06% for gpt-4o-
mini—represents a notable exception to Zep’s otherwise consistent improvements, and suggest further research and
engineering work is needed.

5 Conclusion

We have introduced Zep, a graph-based approach to LLM memory that incorporates semantic and episodic memory
alongside entity and community summaries. Our evaluations demonstrate that Zep achieves state-of-the-art perfor-
mance on existing memory benchmarks while reducing token costs and operating at signiﬁcantly lower latencies.

The results achieved with Graphiti and Zep, while impressive, likely represent only initial advances in graph-based
memory systems. Multiple research avenues could build upon these frameworks, including integration of other
GraphRAG approaches into the Zep paradigm and novel extensions of our work.

Research has already demonstrated the value of ﬁne-tuned models for LLM-based entity and edge extraction within
the GraphRAG paradigm, improving accuracy while reducing costs and latency [19][25]. Similar models ﬁne-
tuned for Graphiti prompts may enhance knowledge extraction, particularly for complex conversations. Addition-
ally, while current research on LLM-generated knowledge graphs has primarily operated without formal ontologies
[9][4][17][19][26], domain-speciﬁc ontologies present signiﬁcant potential. Graph ontologies, foundational in pre-
LLM knowledge graph work, warrant further exploration within the Graphiti framework.
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** Our search for suitable memory benchmarks revealed limited options, with existing benchmarks often lacking ro-
bustness and complexity, frequently defaulting to simple needle-in-a-haystack fact-retrieval questions [3]. The ﬁeld
requires additional memory benchmarks, particularly those reﬂecting business applications like customer experience
tasks, to effectively evaluate and differentiate memory approaches. Notably, no existing benchmarks adequately assess
Zep’s capability to process and synthesize conversation history with structured business data. While Zep focuses on
LLM memory, its traditional RAG capabilities should be evaluated against established benchmarks such as those in
[17], [27], and [28].

Current literature on LLM memory and RAG systems insufﬁciently addresses production system scalability in terms
of cost and latency. We have included latency benchmarks for our retrieval mechanisms to begin addressing this gap,
following the example set by LightRAG’s authors in prioritizing these metrics.

6 Appendix

6.1 Graph Construction Prompts

6.1.1 Entity Extraction
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** <PREVIOUS MESSAGES>
{previous_messages}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{current_message}
</CURRENT MESSAGE>
Given the above conversation, extract entity nodes from the CURRENT MESSAGE that are explicitly or implicitly
mentioned:
Guidelines:
1. ALWAYS extract the speaker/actor as the ﬁrst node. The speaker is the part before the colon in each line of dialogue.
2. Extract other signiﬁcant entities, concepts, or actors mentioned in the CURRENT MESSAGE.
3. DO NOT create nodes for relationships or actions.
4. DO NOT create nodes for temporal information like dates, times or years (these will be added to edges later).
5. Be as explicit as possible in your node names, using full names.
6. DO NOT extract entities mentioned only

8

Using Knowledge Graphs to power LLM-Agent Memory

6.1.2 Entity Resolution
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** <PREVIOUS MESSAGES>
{previous_messages}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{current_message}
</CURRENT MESSAGE>
<EXISTING NODES>
{existing_nodes}
</EXISTING NODES>
Given the above EXISTING NODES, MESSAGE, and PREVIOUS MESSAGES. Determine if the NEW NODE
extracted from the conversation is a duplicate entity of one of the EXISTING NODES.
<NEW NODE>
{new_node}
</NEW NODE>
Task:
1. If the New Node represents the same entity as any node in Existing Nodes, return ’is_duplicate: true’ in the response.
Otherwise, return ’is_duplicate: false’
2. If is_duplicate is true, also return the uuid of the existing node in the response
3. If is_duplicate is true, return a name for the node that is the most complete full name.
Guidelines:
1. Use both the name and summary of nodes to determine if the entities are duplicates, duplicate nodes may have
different names

6.1.3 Fact Extraction

<PREVIOUS MESSAGES>
{previous_messages}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{current_message}
</CURRENT MESSAGE>
<ENTITIES>
{entities}
</ENTITIES>
Given the above MESSAGES and ENTITIES, extract all facts pertaining to the listed ENTITIES from the CURRENT
MESSAGE.
Guidelines:
1. Extract facts only between the provided entities.
2. Each fact should represent a clear relationship between two DISTINCT nodes.
3. The relation_type should be a concise, all-caps description of the fact (e.g., LOVES, IS_FRIENDS_WITH,
WORKS_FOR).
4. Provide a more detailed fact containing all relevant information.
5. Consider temporal aspects of relationships when relevant.

9

Using Knowledge Graphs to power LLM-Agent Memory
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** 6.1.4 Fact Resolution

Given the following context, determine whether the New Edge represents any of the edges in the list of Existing Edges.
<EXISTING EDGES>
{existing_edges}
</EXISTING EDGES>
<NEW EDGE>
{new_edge}
</NEW EDGE>
Task:
1. If the New Edges represents the same factual information as any edge in Existing Edges, return ’is_duplicate: true’
in the response. Otherwise, return ’is_duplicate: false’
2. If is_duplicate is true, also return the uuid of the existing edge in the response
Guidelines:
1. The facts do not need to be completely identical to be duplicates, they just need to express the same information.

6.1.5 Temporal Extraction
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** <PREVIOUS MESSAGES>
{previous_messages}
</PREVIOUS MESSAGES>
<CURRENT MESSAGE>
{current_message}
</CURRENT MESSAGE>
<REFERENCE TIMESTAMP>
{reference_timestamp}
</REFERENCE TIMESTAMP>
<FACT>
{fact}
</FACT>
IMPORTANT: Only extract time information if it is part of the provided fact. Otherwise ignore the time mentioned.
Make sure to do your best to determine the dates if only the relative time is mentioned. (eg 10 years ago, 2 mins ago)
based on the provided reference timestamp
If the relationship is not of spanning nature, but you are still able to determine the dates, set the valid_at only.
Deﬁnitions:
- valid_at: The date and time when the relationship described by the edge fact became true or was established.
- invalid_at: The date and time when the relationship described by the edge fact stopped being true or ended.
Task:
Analyze the conversation and determine if there are dates that are part of the edge fact. Only set dates if they explicitly
relate to the formation or alteration of the relationship itself.
Guidelines:
1. Use ISO 8601 format (YYYY-MM-DDTHH:MM:SS.SSSSSSZ) for datetimes.
2. Use the reference timestamp as the current time when determining the valid_at and invalid_at dates.
3. If the fact is written in the present tense, use the Reference Timestamp for the valid_at date
4. If no temporal information is found that establishes or changes the relationship, leave the ﬁelds as null.
5. Do not infer dates from related events. Only use dates that are directly stated to establish or change the relationship.
6. For relative time mentions directly related to the relationship, calculate the actual datetime based on the reference
timestamp.
7. If only a date is mentioned without a speciﬁc time, use 00:00:00 (midnight) for that date.
8. If only year is mentioned, use January 1st of that year at 00:00:00.
9. Always include the time zone offset (use Z for UTC if no speciﬁc time zone is mentioned).
  *refs:* source=zep-temporal-knowledge-graph.pdf
- **[turn 0, system]** References

[1] Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, Lukasz Kaiser,

and Illia Polosukhin. Attention is all you need, 2023.

[2] K. Sparck Jones. A statistical interpretation of term speciﬁcity and its application in retrieval. Journal of Docu-

mentation, 28(1):11–21, 1972.

10

Using Knowledge Graphs to power LLM-Agent Memory

[3] Charles Packer, Sarah Wooders, Kevin Lin, Vivian Fang, Shishir G. Patil, Ion Stoica, and Joseph E. Gonzalez.

Memgpt: Towards llms as operating systems, 2024.

[4] Darren Edge, Ha Trinh, Newman Cheng, Joshua Bradley, Alex Chao, Apurva Mody, Steven Truitt, and Jonathan

Larson. From local to global: A graph rag approach to query-focused summarization, 2024.

[5] Zep. Zep: Long-term memory for ai agents. https://www.getzep.com, 2024. Commercial memory layer for

AI applications.

[6] Zep.

applications.
https://github.com/getzep/graphiti, 2024. Graphiti builds dynamic, temporally aware Knowledge
Graphs that represent complex, evolving relationships between entities over time.

knowledge

Temporal

Graphiti:

agentic

graphs

for

[7] Di Wu, Hongwei Wang, Wenhao Yu, Yuwei Zhang, Kai-Wei Chang, and Dong Yu. Longmemeval: Benchmark-

ing chat assistants on long-term interactive memory, 2024.

[8] Wong Gonzalez and Daniela. The relationship between semantic and episodic memory: Exploring the effect of

semantic neighbourhood density on episodic memory. PhD thesis, University of Winsor, 2018.

[9] Petr Anokhin, Nikita Semenov, Artyom Sorokin, Dmitry Evseev, Mikhail Burtsev, and Evgeny Burnaev. Ari-
  *refs:* source=zep-temporal-knowledge-graph.pdf, 2023, 1972, 2024, 2018
- **[turn 0, system]** graph: Learning knowledge graph world models with episodic memory for llm agents, 2024.

[10] Xinyue Chen, Pengyu Gao, Jiangjiang Song, and Xiaoyang Tan. Hiqa: A hierarchical contextual augmentation

rag for multi-documents qa, 2024.

[11] Krish Goel and Mahek Chandak. Hiro: Hierarchical information retrieval optimization, 2024.

[12] Noah Shinn, Federico Cassano, Edward Berman, Ashwin Gopinath, Karthik Narasimhan, and Shunyu Yao. Re-

ﬂexion: Language agents with verbal reinforcement learning, 2023.

[13] Xiaojin Zhu and Zoubin Ghahramani. Learning from labeled and unlabeled data with label propagation. 2002.

[14] V. A. Traag, L. Waltman, and N. J. van Eck. From louvain to leiden: guaranteeing well-connected communities.

Sci Rep 9, 5233, 2019.

[15] Neo4j. Neo4j - the world’s leading graph database, 2012.

[16] Apache Software Foundation. Apache lucene - scoring, 2011. letzter Zugriff: 20. Oktober 2011.

[17] Zirui Guo, Lianghao Xia, Yanhua Yu, Tu Ao, and Chao Huang. Lightrag: Simple and fast retrieval-augmented

generation, 2024.

[18] Jimmy Lin, Ronak Pradeep, Tommaso Teoﬁli, and Jasper Xian. Vector search with openai embeddings: Lucene

is all you need, 2023.

[19] Prafulla Kumar Choubey, Xin Su, Man Luo, Xiangyu Peng, Caiming Xiong, Tiep Le, Shachar Rosenman, Va-
sudev Lal, Phil Mui, Ricky Ho, Phillip Howard, and Chien-Sheng Wu. Distill-synthkg: Distilling knowledge
graph synthesis workﬂow for improved coverage and efﬁciency, 2024.
  *refs:* source=zep-temporal-knowledge-graph.pdf, 2024, 2023, 2002, 2019, 2012, 2011
- **[turn 0, system]** [20] Gordon V. Cormack, Charles L. A. Clarke, and Stefan Buettcher. Reciprocal rank fusion outperforms condorcet
In Proceedings of the 32nd International ACM SIGIR Conference on

and individual rank learning methods.
Research and Development in Information Retrieval, SIGIR ’09, pages 758–759. ACM, 2009.

[21] Jaime Carbonell and Jade Goldstein. The use of mmr, diversity-based reranking for reordering documents and
producing summaries. In Proceedings of the 21st Annual International ACM SIGIR Conference on Research and
Development in Information Retrieval, SIGIR ’98, page 335–336, New York, NY, USA, 1998. Association for
Computing Machinery.

[22] Jing Xu, Arthur Szlam, and Jason Weston. Beyond goldﬁsh memory: Long-term open-domain conversation,

2021.

[23] Chaofan Li, Zheng Liu, Shitao Xiao, and Yingxia Shao. Making large language models a better foundation for

dense retrieval, 2023.

[24] Jianlv Chen, Shitao Xiao, Peitian Zhang, Kun Luo, Defu Lian, and Zheng Liu. Bge m3-embedding: Multi-
lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation, 2024.

[25] Shreyas Pimpalgaonkar, Nolan Tremelling, and Owen Colegrove. Triplex: a sota llm for knowledge graph

construction, 2024.

[26] Shilong Li, Yancheng He, Hangyu Guo, Xingyuan Bu, Ge Bai, Jie Liu, Jiaheng Liu, Xingwei Qu, Yangguang
Li, Wanli Ouyang, Wenbo Su, and Bo Zheng. Graphreader: Building graph-based agent to enhance long-context
abilities of large language models, 2024.

11

Using Knowledge Graphs to power LLM-Agent Memory
  *refs:* source=zep-temporal-knowledge-graph.pdf, 2009, 1998, 2021, 2023, 2024
- **[turn 0, system]** [27] Pranab Islam, Anand Kannappan, Douwe Kiela, Rebecca Qian, Nino Scherrer, and Bertie Vidgen. Financebench:

A new benchmark for ﬁnancial question answering, 2023.

[28] Nandan Thakur, Nils Reimers, Andreas Rücklé, Abhishek Srivastava, and Iryna Gurevych. Beir: A heterogenous

benchmark for zero-shot evaluation of information retrieval models, 2021.

12
  *refs:* source=zep-temporal-knowledge-graph.pdf, 2023, 2021
- **[turn 0, system]** # M-Flow — Bio-Inspired Cognitive Memory Engine

Source: https://github.com/FlowElement-ai/m_flow (Apache-2.0)

## Core claim

"RAG matches chunks. GraphRAG structures context. M-flow scores evidence paths."

M-flow treats knowledge retrieval as **path-cost optimization** in a structured graph, not similarity matching. Queries anchor at matching granularity, then propagate evidence through the graph.
  *refs:* source=m_flow_notes.md
- **[turn 0, system]** ## Architecture — four-level inverted-cone graph

- **Episode** — bounded semantic events (incidents, decisions, workflows)
- **Facet** — one dimensional slice of an Episode (topical cross-section)
- **FacetPoint** — atomic assertions or precise facts
- **Entity** — named things (people, tools, metrics) linked across Episodes

Granularity-aligned retrieval: a precise query anchors on a FacetPoint, a broader one enters through Facets or Episode summaries.

## Temporal handling

- Episodic memory with time-bounded event clustering
- Session-level coreference resolution before indexing (pronouns resolved → preserves temporal context across multi-turn conversations)
- LongMemEval temporal benchmark: reports 93% accuracy

## How it differs

**vs RAG:** vector similarity → graph propagation paths. Returns Episode bundles with supporting chains, not ranked chunks.
**vs classic KGs:** edges carry semantic meaning (`edge_text`); the graph is an active scoring engine, not just storage.

## Benchmarks reported by project

- LoCoMo-10: 81.8% accuracy
- LongMemEval: 89% (vs competitors 50-79% in their reporting)

## APIs (from README)

Write:
```python
await m_flow.add("text or document")
await m_flow.memorize()  # graph construction + embedding
```

Read:
```python
results = await m_flow.query("question", query_type=EPISODIC)
```

CLI: `mflow add`, `mflow memorize`, `mflow search`, `mflow -ui`.
  *refs:* source=m_flow_notes.md
- **[turn 0, system]** ## Components

- Extraction pipeline (50+ file formats, coreference resolution)
- Knowledge graph builder (cone hierarchy with typed, weighted edges)
- Vector + graph adapters (LanceDB, Neo4j, PostgreSQL/pgvector, ChromaDB, KùzuDB, Pinecone)
- Episodic retrieval (graph-routed bundle search; primary mode)
- Procedural memory (extracts reusable abstract patterns)
- MCP server (exposes memory as MCP tools)
- Optional face-recognition integration (real-time partitioning by biometric identity)

## Use cases claimed

- Agentic AI: persistent memory for long-running agents
- Multi-person: face-aware identity partitioning
- Knowledge-intensive QA over ingested documents
- Conversational systems: temporal coherence via coreference resolution
  *refs:* source=m_flow_notes.md
- **[turn 0, system]** ## What we don't yet know (open questions for comparison)

- Write-time LLM cost per document (m_flow's "memorize" step does coreference + graph construction — how many LLM calls?)
- Latency breakdown for episodic retrieval vs pure vector KNN
- Behavior under explicit contradictions (the E4 scenario: earlier doc says Alice is CEO, later doc says Bob; does m_flow's episodic bundle return both, the latest, or let the caller resolve?)
- Operational complexity (graph DB + vector DB vs our single-store approach)
- Whether coreference pre-indexing assumes clean conversational input (may not fit noisy research corpora)
  *refs:* source=m_flow_notes.md
- **[turn 0, system]** # Agent Memory Architecture

*As-built reference for the three-tier hybrid memory in research-pipeline. Updated 2026-04-23 with the Karpathy + Zep hybrid.*
  *refs:* source=agent-memory-architecture.md, 2026
- **[turn 0, system]** ## 1. Overview

Three cosine-searchable tiers of markdown-like content, with kind-typed per-project memory promoting to a temporally-indexed per-user wiki on healthy runs. All persisted in SQLite. No graph database, no separate vector store, no custom extractor beyond MarkItDown.

The architecture borrows structure from Karpathy's LLM Wiki pattern (markdown-first, human-readable, compounding) and a single capability from Zep's temporal knowledge graph (`$t_{ref}$` as a time anchor per entry).
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ## 2. The Three Tiers
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ```
                        ┌─────────────────────────────────────┐
                        │  TIER 3 — Cross-Project Long-Term   │
                        │  user_wiki_entries                  │
                        │  Karpathy structure + t_ref          │
                        │  cosine embedding + as_of filter    │
                        └──────────────┬──────────────────────┘
                                       │ auto-promote (rubric ≥ floor)
                                       │ or rp wiki promote <id>
                        ┌──────────────▼──────────────────────┐
                        │  TIER 2 — Per-Project Blackboard    │
                        │  blackboard_entries (kind-typed)    │
                        │  evidence/hypothesis/critique/      │
                        │  experiment/result/draft/review     │
                        │  state ∈ proposed/verified/refuted  │
                        │  dedup via cosine echo clustering   │
                        └──────────────┬──────────────────────┘
                                       │ promote_project_posts
                                       │ (every turn; archetype → kind)
                        ┌──────────────▼──────────────────────┐
                        │  TIER 1 — Per-Turn Working Memory   │
                        │  in-context prompt block            │
                        │    SOURCES       [src #N]          │
                        │    HYPOTHESES    [hyp #N]          │
                        │    RECENT POSTS  last 12           │
                        │    FEEDBACK      last-turn rubric  │
                        │  no storage; regenerated each turn  │
                        └─────────────────────────────────────┘
```
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** | tier | table | scope | retrieval primitive | dedup | lifecycle |
|---|---|---|---|---|---|
| **T1 working** | (in-prompt only) | one turn | LLM attention | n/a | ephemeral |
| **T2 project** | `blackboard_entries` | one project | `retrieval.search_blackboard` (cosine on `embedding_json`, `visibility='visible'`) | `dedup.add_entry_with_dedup` (cos ≥ 0.85 → echo on canonical) | `lifecycle.py` → proposed → supported / refuted / verified |
| **T3 long-term** | `user_wiki_entries` | one user, all projects | `wiki.search_wiki(as_of=...)` cosine + optional temporal filter | exact-content match on promote | append-only; promoted_score = rubric × refs × echo × length |

## 3. Tier Details
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 3.1 Tier 1 — Working Memory

No storage. Regenerated every turn by `simulation._run_prompted_turn`:

```python
system_msg = (
    archetype.system_prompt                                 # role
    + specialty_focus_block                                 # from per-agent config
    + role_reinforcement                                    # anti-convergence nudge
    + kpi_feedback_line                                     # last-turn rubric
    + citation_policy                                       # [src #N] must trace
)
user_msg = (
    f"GOAL: {goal}\n"
    f"TURN: {turn}\n"
    f"SOURCES (cite by [src #N]):\n{evidence_block}\n"
    f"HYPOTHESES IN PLAY (cite as [hyp #N]):\n{hyps_block}\n"
    f"RECENT CHANNEL POSTS:\n{feed_block}\n"
    f"Your task: post ONE tweet ...\n"
)
```

Size-bounded inputs (top-6 evidence, 6 hypotheses, 12 posts) keep each turn's prompt within ~2k tokens. This is the entirety of an agent's "memory" at posting time — everything else is retrieval.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 3.2 Tier 2 — Project Blackboard

Schema (condensed):

```sql
CREATE TABLE blackboard_entries (
    id                INTEGER PRIMARY KEY,
    project_id        INTEGER NOT NULL,
    agent_id          INTEGER,              -- NULL for PI / ingested material
    kind              TEXT,                 -- evidence/hypothesis/critique/...
    content           TEXT,
    refs_json         TEXT,                 -- cited years, DOIs, author tokens
    turn              INTEGER,
    embedding_json    TEXT,                 -- 1024-dim qwen3-embedding
    echo_count        INTEGER DEFAULT 0,
    echo_refs_json    TEXT DEFAULT '[]',
    state             TEXT DEFAULT 'proposed',
    resolutions_json  TEXT DEFAULT '[]',
    visibility        TEXT DEFAULT 'visible'  -- 'visible' or 'held_out' for PGR
);
```

**Write path:**

1. `ingest.py` chunks PDFs/DOCX via MarkItDown. Each chunk becomes a `kind=evidence` row (`agent_id=NULL`). Hash-partitioned 80/20 into `visibility`.
2. Each simulation turn, `promote.py` files agent posts per the archetype → kind map:
   - scout → evidence · hypogen → hypothesis · experimenter → experiment
   - critic → critique · replicator → result · statistician → critique
   - writer → draft · reviewer → review
3. On insert, `dedup.add_entry_with_dedup` embeds the content, finds near-neighbors (cosine ≥ 0.85) in the same kind, and either creates a new row or increments `echo_count` on the canonical.
4. `lifecycle.resolve_hypothesis_refs` scans result/critique posts for `[hyp #N]` references and transitions the hypothesis state.

**Read path:**
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** - `retrieval.search_blackboard(project_id, query, top_k, kind, visibility)` is the one entry point. Returns `ScoredEntry(entry, score)` tuples. Default `visibility='visible'` — agents never see held-out chunks.
- `lifecycle.hypotheses_in_play` fetches open hypotheses for T1's prompt.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 3.3 Tier 3 — Per-User Wiki

Schema (condensed):

```sql
CREATE TABLE user_wiki_entries (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL,
    kind                TEXT,                 -- same taxonomy as T2
    content             TEXT,
    refs_json           TEXT,
    embedding_json      TEXT,
    source_project_id   INTEGER,
    promoted_score      REAL,
    t_ref               TEXT,                 -- ISO date: when claim is TRUE
    created_at          TEXT DEFAULT (datetime('now'))
);
```

**Write path:**

1. `wiki.promote_project_to_wiki` runs at end-of-run when rubric ≥ floor (default 3.0).
2. For each kind, pick top-K by `_score_entry` (weighted rubric × refs × echo × content length).
3. `_extract_t_ref(refs)` pulls the max year in [1900, 2099] from an entry's refs → `YYYY-01-01`. Entries without year-refs stay atemporal (`t_ref=NULL`).
4. Duplicate-content guard: exact content match on same user → skip.
5. Embedding copied from the blackboard entry (no re-embedding).

**Read path:**

- `wiki.search_wiki(user_id, query, top_k, kind, as_of)` — the one entry point.
- `as_of='YYYY-MM-DD'` filters to `t_ref <= as_of OR t_ref IS NULL`. Null t_refs are atemporal — always included.
- `wiki.seed_project_from_wiki` wraps `search_wiki` and files hits into a new project's blackboard as evidence with `refs=['source=user_wiki#N', ...]`.

## 4. Data Flow Diagrams
  *refs:* source=agent-memory-architecture.md, 1900, 2099
- **[turn 0, system]** ### 4.1 Write Path (ingest → blackboard)

```
  PDF / DOCX / HTML / MD / …
    │
    │  rp project ingest <id> <files>
    │
    ▼ MarkItDown.convert() → markdown
    │
    │  _chunk_markdown (split by heading, size-capped)
    │
    ▼ for each chunk:
    │    _is_held_out()        → visibility ∈ {visible, held_out}
    │    extract_refs()        → years, DOIs, arxiv ids, author tokens
    │    llm.embed("embedding") → 1024-dim vector (qwen3-embedding)
    │
    ▼ add_entry_with_dedup (cosine ≥ 0.85 → echo)
    │
    ▼ blackboard_entries (T2)
```
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 4.2 Write Path (promotion up the tiers)

```
  agent posts in channel_posts
    │
    │  end-of-turn hooks (run every turn):
    │    link_mentions          → parent_id backfill
    │    promote_project_posts  → archetype → kind
    │    resolve_hypothesis_refs→ state transitions
    │    snapshot_counters      → KPI bookkeeping
    │
    ▼ blackboard_entries (T2 grows)
    │
    │  [project finishes; judge_project scores rubric]
    │
    │  if rubric ≥ auto_promote_rubric_floor:
    │    promote_project_to_wiki(top_k_per_kind=3)
    │      for each kind: rank by _score_entry, take top-K
    │      _extract_t_ref(refs)
    │      dedup on exact content
    │
    ▼ user_wiki_entries (T3)
```
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 4.3 Read Path (per-agent per-turn)

```
  agent's turn in simulation._run_prompted_turn
    │
    ▼ _retrieve_evidence(project.goal, llm, top_k=6)
    │    → retrieval.search_blackboard
    │         filter: visibility='visible', kind='evidence'
    │    → [ScoredEntry with [src #N] anchors]
    │
    ▼ hypotheses_in_play(project_id, limit=6)
    │    → SELECT FROM T2 WHERE kind='hypothesis' AND state IN ('proposed','under_test')
    │    → [(hyp_id, state, content)]
    │
    ▼ _recent_posts_context(project_id, limit=12)
    │    → SELECT FROM channel_posts ORDER BY id DESC LIMIT 12
    │
    ▼ _recent_kpi_scores(project_id)
    │    → latest rubric row
    │
    ▼ composed T1 prompt
    │    → llm.achat(role='agent_bulk', messages=..., temperature=...)
    │
    ▼ _generate_unique_post (dedup retry if near-duplicate)
    │
    ▼ OASIS env.step with ManualAction(CREATE_POST)
```
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 4.4 Seed Path (T3 → new T2)

```
  new project created; user wants prior knowledge loaded
    │
    │  rp wiki seed <new_project_id>
    │
    ▼ seed_project_from_wiki:
    │    search_wiki(user_id, project.goal, top_k=6)
    │    [hits copied as kind=evidence into target blackboard]
    │    refs get "source=user_wiki#<entry_id>" prefix for traceability
    │    threshold=0.98 dedup (wiki content is already vetted)
    │
    ▼ blackboard_entries (T2) of the new project
```

## 5. The Karpathy Contribution
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 5.1 What we kept literally

| Karpathy gist concept | our implementation |
|---|---|
| `raw/` — immutable sources | `projects/{id}/raw/*.md` (MarkItDown output) |
| `wiki/` — LLM-compiled pages | `user_wiki_entries` table, kind-typed content |
| cross-linking via backlinks | `[src #N]` and `[hyp #N]` ref patterns in content |
| ingest op (compile sources) | `ingest.py` (+ promote to wiki) |
| query op (search + synthesize, file back) | `wiki.search_wiki` + `synthesize.py` artifacts |
| lint op (contradictions, orphans, stale) | partial: `dedup` + `lifecycle` + echo-clustering |
| persistent compounding | auto-promote on healthy runs + `rp wiki seed` |
| human-readable markdown | `render_wiki_markdown` + `rp wiki show` + the claims/hypotheses/experiments/decision/risks artifacts |
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 5.2 What we simplified / skipped

| Karpathy concept | why we skipped |
|---|---|
| separate `index.md` file | derivable from the table on demand; no distinct artifact |
| separate `log.md` file | `created_at` column + `source_project_id` covers the trace |
| Obsidian as the IDE | IDE choice is user's; we stay backend-agnostic |
| Obsidian Web Clipper | ingest via `rp project ingest` + MarkItDown replaces it |
| qmd local search | cosine embedding search covers BM25's role for our scale |
| Marp slide decks | out of scope for a research pipeline |
| Dataview plugin queries | SQL queries over the table cover equivalent needs |

We kept the **pattern** and the **principles** (LLM does bookkeeping, human curates, knowledge compounds). We skipped the specific toolchain because our pipeline is code-first, not markdown-file-first.

## 6. The Zep Contribution

### 6.1 What we stole

Exactly one thing: `user_wiki_entries.t_ref TEXT` column — Zep's reference-timestamp pattern applied to the wiki.

```python
def _extract_t_ref(refs: list[Any]) -> str | None:
    """Pull max year [1900, 2099] from refs; return 'YYYY-01-01' or None."""
```

Used in `wiki.search_wiki(as_of=...)` to filter by temporal precedence. Null `t_ref` = atemporal (always included).
  *refs:* source=agent-memory-architecture.md, 1900, 2099
- **[turn 0, system]** ### 6.2 What we refused to steal

| Zep feature | why we passed |
|---|---|
| bi-temporal model (T and T' timelines) | our single `t_ref` + `created_at` covers 80% at 5% cost |
| episode subgraph | T2 blackboard + `turn` column serves the role |
| semantic entity subgraph | we don't extract entities; retrieval is cosine over chunks |
| community subgraph (label propagation) | kind-typed clustering is sufficient at our scale |
| Graphiti / neo4j | local-first low-ops constraint; SQLite wins |
| structural extraction pipeline | MarkItDown + chunking is the extraction; we don't build KG nodes |
| query-time contradiction resolution | deferred to phase 4 (would live in `wiki.search_wiki` as a layer on top) |
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ## 7. The Compounding Loop

```
  project N ends with rubric ≥ floor
    │
    ▼ auto_promote_to_wiki → top-K per kind land in T3 with t_ref
    │
    │  [user starts project N+1 on a related topic]
    │
    ▼ rp wiki seed <N+1> (optional)
    │   → search_wiki finds relevant prior entries
    │   → filed into T2 with refs='source=user_wiki#<id>'
    │
    ▼ agents in project N+1 see prior knowledge in their T1 context
    │
    ▼ discussion builds on prior synthesis (doesn't start from zero)
    │
    ▼ project N+1 produces new claims/artifacts
    │
    ▼ auto_promote_to_wiki → T3 grows
    │
    └─> back to top
```

`--as-of` lets you collapse this cycle at any point and ask "what did T3 know at date X."
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ## 8. What the Architecture Deliberately Doesn't Do

- **No graph database.** All relationships are either cosine-similar (retrieval) or reference-based (`[src #N]`, `[hyp #N]`, `source=user_wiki#id`). No traversal, no edges, no inference over structure.
- **No entity extraction.** Chunks are the unit of knowledge. We don't build nodes for "Entity X" across sources.
- **No bi-temporal reasoning.** We have `t_ref` (when claim is TRUE) and `created_at` (when ingested). That's it. No T' transactional timeline, no temporal deltas, no state-change reasoning.
- **No shared memory across users.** T3 is per-user. Org-level wiki is phase-4.
- **No query-time contradiction repair.** If two T3 entries disagree (different `t_ref`, same concept), the retriever ranks by cosine — it doesn't pick a winner. The caller (Writer / Reviewer) must reconcile.
- **No streaming / real-time memory updates.** Writes happen at end-of-turn (batched). Good enough for research, wrong for conversational agents with live state.

## 9. What We Haven't Proven

**The hybrid is a design argument with working code and unit tests. It is not a validated architecture.** No head-to-head comparison against pure Karpathy or pure Zep has been run. This section names that gap honestly so future readers don't mistake the confidence of the implementation for evidence that it wins.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 9.1 What the hybrid was built on

1. The critic archetype's argument that Zep and Karpathy **both pay a write-time LLM-drift tax** (project 6, `[crit #324]`).
2. The judgment that `$t_{ref}$` is **Zep's single most useful capability** for our context — all other Zep features require a graph database we don't want to run.
3. The judgment that Karpathy's structure is **the better fit for local-first, low-ops, compounding research** — Zep's production orientation doesn't match single-user single-laptop scale.
4. The pattern: **steal the one useful capability; don't adopt the losing side wholesale**.

Each link in that chain is plausible. **None was tested.** Project 6's `decision.md` explicitly called for the E4 Query-Time Repair experiment before picking a winner. We built the hybrid anyway because the argument felt strong.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 9.2 What would actually be proof

A controlled experiment over the same corpus, comparing three systems:

```
  Same source corpus (e.g. 30 chronologically-ordered papers)
    System A: pure Karpathy LLM Wiki
    System B: pure Zep TKG (or faithful reimplementation)
    System C: ours (Karpathy + t_ref)
      │
      ▼ inject N temporal contradiction events (doc_15 supersedes claim in doc_10)
      │
      ▼ run standard query set: "what is the current state of X?"
      │
      ▼ measure per system:
          currency       — fraction returning the latest correct answer
          propagation    — downstream queries affected per contaminated entity
          retrieval cost — $/query + storage overhead
          human-readability — side task: can a new user navigate the store?
      │
      ▼ winner per axis, no winner-take-all
```

Minimum viable version: 10 docs, 3 contradiction events, 5 queries per system, single trial. Would demonstrate the *capability* on one benchmark, not prove it across domains.

**We have not run even the minimum viable version.** No numbers behind the architecture, on any axis, for any corpus.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 9.3 Specific ways the hybrid could be worse

| failure mode | worse than Karpathy | worse than Zep |
|---|---|---|
| `t_ref` heuristic misattributes dates (publication year ≠ claim-valid-year) | ✅ pure Karpathy doesn't pretend to handle time — no wrong answers about when | — |
| no lint / contradiction-detection pass | ✅ canonical Karpathy lints as a first-class op; we only have embedding dedup | — |
| raw chunk storage vs compiled wiki pages | ✅ canonical Karpathy has the LLM compile raw sources into entity pages; we store chunks and skip the compilation step | — |
| no bi-temporal T' transactional timeline | — | ✅ can't reason about "we learned X at time T₂ but X was valid at T₁" |
| no entity extraction / node traversal | — | ✅ can't query "everything about entity X" as graph traversal |
| no relative-time resolution ("two weeks ago") | — | ✅ Zep resolves these; our `t_ref` is a static date tag, not a reasoner |
| no state-change tracking at entity level | — | ✅ Zep tracks entity state transitions; we only track hypothesis lifecycle in T2 |
| added complexity without measured payoff | ✅ | ✅ |

Any one of these could be the dominant term on a real task. We don't know which.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 9.4 Fair framing

- **What we can say honestly**: the hybrid is a reasonable bet given our stated constraints (local-first, single-user, research compounding, no ops budget for a graph DB). The `--as-of` filter provides a capability pure Karpathy lacks, at the cost of ~30 lines of code and 9 unit tests.
- **What we cannot say honestly**: that it's "superior" to either pure approach. No measurement supports that claim.
- **What's at stake if it's actually worse**: if `t_ref` heuristic misfires frequently, the `--as-of` filter returns wrong answers silently. We don't know the misfire rate.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ### 9.5 How to close the gap

Three paths, ranked by cost:

1. **Keep this section up to date** (0.1 days). Re-read every time someone asks "is this better?" — don't let implementation confidence leak into architectural claims.
2. **Build a minimum viable E4 benchmark** (1 day). Toy corpus of 10 docs, 3 injected contradictions, 5 queries. Measure currency only. Under-powered but produces *some* evidence. Persist as `benchmarks/e4_query_time_repair/` so future runs can compare.
3. **Build a serious benchmark suite** (phase 4, multi-week). Requires reference implementations of pure Karpathy compilation and a Zep-like minimal TKG. Measurement on currency, propagation, cost, and readability. This is the only thing that earns the word "superior."

Path 1 is this section itself. Path 2 is the natural first phase-4 task.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ## 10. Extension Points (phase 4+)

- **Verification loop** (phase 4 proposal): `runnable_json` column on `blackboard_entries` for `kind=experiment` rows; orchestrator executes in sandbox; results flow back as `kind=result` rows that trigger `lifecycle.resolve_hypothesis_refs`.
- **Org-level wiki**: `user_id → org_id` foreign key change on T3; `search_wiki(org_id=...)` as new default scope. All wiki CLI commands gain `--org` flag.
- **Query-time contradiction repair**: when `wiki.search_wiki` returns two near-cosine hits with different `t_ref`, a resolver step (LLM or rule) picks the later one and flags the conflict. Would live as a post-processing step inside `search_wiki`.
- **Entity extraction** (if ever needed): add `entities_json` column to T2; use at retrieval time for "show me all entries mentioning entity X." Adds a small KG-like capability without adopting a KG database.
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** ## 11. Reference Map

| concept | table | module | key functions |
|---|---|---|---|
| T1 working memory | — | `simulation.py` | `_run_prompted_turn`, `_retrieve_evidence`, `_recent_posts_context`, `_recent_kpi_scores`, `hypotheses_in_play` |
| T2 project blackboard | `blackboard_entries`, `channel_posts` | `blackboard.py`, `promote.py`, `dedup.py`, `lifecycle.py`, `retrieval.py` | `add_entry`, `list_entries`, `add_entry_with_dedup`, `resolve_hypothesis_refs`, `search_blackboard`, `promote_project_posts` |
| T3 long-term wiki | `user_wiki_entries` | `wiki.py` | `promote_project_to_wiki`, `search_wiki`, `seed_project_from_wiki`, `render_wiki_markdown`, `_extract_t_ref`, `_score_entry` |
| Ingestion | — | `ingest.py` | `ingest_file`, `_chunk_markdown`, `_is_held_out` |
| Embeddings | — | `adapter.py` | `LLMClient.embed`, `LLMClient.aembed` |

## 12. One-Sentence Summary

**Three cosine-searchable tiers of markdown-like content, with kind-typed per-project memory promoting to a temporally-indexed per-user wiki on healthy runs, persisted in SQLite, with no graph database, no custom entity extraction, and the Karpathy wiki pattern as the structure + Zep's `$t_{ref}$` as the one stolen temporal capability.**
  *refs:* source=agent-memory-architecture.md
- **[turn 0, system]** # Supermemory — Memory API for AI Agents

Source: https://github.com/supermemoryai/supermemory (MIT)

## Core claim

"The Memory API for the AI era." Hosted service + SDKs (npm/pip). Claims #1 on LongMemEval, LoCoMo, ConvoMem benchmarks (per project page). Also offers MCP server + plugins (Claude, Cursor, VS Code) + framework wrappers (Vercel AI, LangChain).

## Architecture — inferred from README

Storage substrate not explicitly documented. The system describes itself as "a single memory structure and ontology," suggesting a unified backing store (likely hybrid vector + structured metadata).
  *refs:* source=supermemory_notes.md
- **[turn 0, system]** ## Temporal handling — the differentiating axis

Supermemory advertises four distinct temporal behaviors:
1. **Automatic fact extraction** from conversations (similar to Mem0/Zep)
2. **User profile maintenance** (similar to Mem0's extract-consolidate pattern)
3. **Contradiction handling** — "'I moved to SF' supersedes 'I live in NYC'" → updates rather than duplicates. Overwrite semantics.
4. **Forgetting** — "forgets expired information." Explicit TTL/decay. This is distinct from:
   - **Mem0**: overwrites (no history retained)
   - **Zep**: accumulates with `valid_from` (history retained but marked stale by newer triples)
   - **Karpathy**: overwrites via LLM compile
   - **Our hybrid**: keeps all chunks forever (no forgetting)

The forgetting capability is the novel axis no other system in our comparison explicitly foregrounds.

## Retrieval

**Hybrid Search** — "RAG + Memory in a single query" — combines document chunk retrieval with structured profile lookup in one API call. Reported ~50ms for user profiles. This is architecturally what our `hybrid` tries to achieve via chunks-with-t_ref, except supermemory pairs it with a consolidated-profile structure alongside (closer to mem0 + chunks).

## Ingest

Multimodal:
- PDFs (via extraction pipeline)
- Images (OCR)
- Video (transcription)
- Code (AST-aware chunking)
- Text, conversations, URLs, HTML

## APIs

```javascript
client.add("text or URL or file")
client.profile()                       // user profile + optional search
client.search.memories("query")        // hybrid search
client.documents.uploadFile(...)
```

## Deployment

Both hosted service (https://app.supermemory.ai) and open-source library. MIT license permits commercial reuse.

## Target workloads

AI agents, personalization, knowledge management — for both consumer and developer audiences.
  *refs:* source=supermemory_notes.md
- **[turn 0, system]** ## Where it fits in our comparison

- **vs Mem0**: same consolidate-on-update semantics + adds explicit TTL + adds chunk fallback. Strict superset of mem0's pattern.
- **vs Zep**: gives up full temporal history (`valid_from` chain) in exchange for simpler retrieval + forgetting.
- **vs M-Flow**: no four-level cone hierarchy; memory is flat profile + chunks, not graph paths.
- **vs our Hybrid**: adds a consolidated profile layer on top of the chunk store. Our hybrid has chunks-only. The profile layer is what gives it stress-test resilience (E1 hypothesis: consolidation beats chunk-only retrieval for attribute churn).
  *refs:* source=supermemory_notes.md
- **[turn 0, system]** ## Open questions for comparison

- TTL mechanism: time-based, confidence-based, or importance-based? Unclear from README.
- Ingest LLM cost per doc: one extract + one embed? Or more?
- How the "hybrid search" arbitrates between profile hits and chunk hits when both have candidate answers.
- Whether "forgetting" is destructive (chunks deleted) or soft (marked expired, still retrievable with flags).
  *refs:* source=supermemory_notes.md

## hypothesis (28)

- **[turn 0, agent 27]** The "intelligence" of memory architectures is a distraction. In frequent-write blackboard workloads, high-fidelity extraction (Mem0/Zep) actually induces "semantic drift" via LLM hallucination during consolidation [src #383, #431]. The fastest, most accurate system will be the on
  *refs:* —
- **[turn 0, agent 28]** The field assumes more structure (graphs/triples) improves temporal fidelity, but I hypothesize that for frequent-write blackboard workloads, M-Flow’s inverted cone and Mem0’s consolidation will actually *degrade* accuracy via "semantic smoothing." High-frequency updates will cau
  *refs:* —
- **[turn 1, agent 27]** I hypothesize that M-Flow’s coreference pre-indexing [src #431] creates a "latency wall" that renders it non-viable for blackboard workloads. If write-time cost scales with entity density, M-Flow will fail the operational fit test regardless of its retrieval precision.
  *refs:* —
- **[turn 1, agent 28]** I support [hyp #457]: High-fidelity extraction is a liability in high-velocity workloads. While Zep/Mem0 use LLMs for graph/consolidation [src #383], this creates a "fidelity bottleneck" where write-time hallucination or "semantic smoothing" [hyp #458] corrupts the ground truth.
  *refs:* —
- **[turn 2, agent 27]** We are ignoring the "Read-Time Tax." While [hyp #463] focuses on M-Flow's write-time latency [src #431], the real failure mode for blackboard workloads is the retrieval complexity of M-Flow's inverted cone/graph paths vs. our hybrid's flat KNN [src #432].

I am NEUTRAL on [hyp #4
  *refs:* —
- **[turn 2, agent 28]** I propose [hyp #465]: The "blackboard" failure mode is not semantic drift, but *index-write race conditions*. In high-velocity workloads, M-Flow's coreference indexing [src #431] and Zep's graph construction [src #412] create a "consistency lag" where retrieval queries hit stale 
  *refs:* —
- **[turn 2, agent 27]** I propose [hyp #465]: In high-velocity 'blackboard' workloads, the primary failure mode for agent memory isn't semantic drift, but index-write race conditions. As we scale write-frequency, the 'consistency lag' between a fact being observed and its structural integration into the memory becomes the bottleneck. 

Our current Karpathy+Zep hybrid relies on simple chunks tagged with t_ref and cosine retrieval with an as_of filter [src #432]. This avoids the write-time LLM overhead but lacks structural awareness. In contrast, Zep’s temporal knowledge graph uses gpt-4o-mini for EAV triple extraction [src #412], and M-Flow utilizes a complex 'memorize' step involving coreference pre-indexing and graph construction [src #431]. 

My hypothesis is that for frequent-write workloads, the 'intelligence' of the memory (Zep/M-Flow) is inversely proportional to its temporal fidelity. M-Flow’s coreference indexing [src #431] and Zep’s graph construction [src #412] create a window where retrieval queries hit stale or partially-constructed states. We are trading immediate availability for structural depth. If we adopt Mem0’s extract-consolidate-retrieve pattern, we might actually exacerbate this lag by introducing a consolidation step that acts as a delayed batch process, further widening the gap between 'event occurred' and 'event is searchable.'

This is falsifiable: if we measure retrieval accuracy on a high-velocity stream and find that the 'hybrid' (simple vector + t_ref) outperforms M-Flow in 'as-of' queries during peak write bursts, the consistency lag hypothesis is confirmed.

If we want to move toward M-Flow's depth without the lag, should we prioritize asynchronous coreference pre-indexing or stick to the low-latency simplicity of temporal vector filtering?
  *refs:* —
- **[turn 3, agent 27]** I propose [hyp #474]: The "Blackboard Bottleneck" is not write-latency, but "Retrieval-Induced Hallucination" during the window of structural incompleteness. In M-Flow [src #431] or Zep [src #412], querying a partially-indexed graph creates a "false void" where missing edges are 
  *refs:* —
- **[turn 3, agent 28]** I propose [hyp #474]: The "fidelity bottleneck" isn't just write-latency, but a "structural resolution floor." In high-velocity bursts, M-Flow's coreference [src #431] and Zep's EAV extraction [src #412] will prioritize entity-level stability, effectively "smoothing" out transien
  *refs:* —
- **[turn 0, agent 27]** The "consolidated profile + chunk fallback" pattern is a trap for blackboard workloads. I hypothesize that M-Flow’s hierarchy outperforms Supermemory's superset model because high-frequency writes cause "consolidation collapse," where TTL-driven forgetting [src #485] erases the v
  *refs:* —
- **[turn 0, agent 28]** Consensus favors consolidation, but Mem0’s 3/3 fidelity [src #377] suggests hierarchies are dead weight. Hypothesis: Supermemory’s TTL/fallback isn't a superset; it's a patch for Mem0's lack of entropy. True scale requires M-Flow's hierarchy to prevent profile bloat.
  *refs:* —
- **[turn 1, agent 27]** I refute the "strict superset" utility of Supermemory [src #486]. If it trades Zep’s temporal chains for simpler retrieval [src #486], it likely inherits the `hybrid_recency` eviction failure. Supermemory's TTL [src #485] may accelerate entropy in interleaved streams.
  *refs:* —
- **[turn 1, agent 28]** I refute [hyp #489]. Supermemory's "strict superset" [src #486] claim is a category error regarding temporal fidelity. TTL is a lossy filter, not an entropy management tool. If Mem0 lacks entropy [src #377], TTL only accelerates the "hybrid_recency" eviction failure [E1].
  *refs:* —
- **[turn 0, agent 27]** The "strict superset" consensus is wrong: Supermemory’s profile+chunk fallback will actually degrade temporal fidelity in high-frequency blackboard workloads compared to M-Flow. Hierarchical granularity is required to prevent profile-drift when TTL evicts critical context [src #4
  *refs:* —
- **[turn 0, agent 28]** The "strict superset" consensus is a trap. Supermemory’s profile+chunk fallback will actually degrade fidelity in high-frequency blackboard workloads compared to M-Flow's hierarchy [src #486]. Flat consolidation creates "semantic compression loss" that no TTL can fix.
  *refs:* —
- **[turn 1, agent 28]** Supermemory’s "strict superset" [src #486] status is a lie of omission. While it adds TTL [src #485], it lacks the structured lineage of M-Flow or Zep. I hypothesize that in blackboard workloads, Supermemory will suffer "Profile-Drift Collapse": frequent writes will consolidate t
  *refs:* —
- **[turn 2, agent 27]** I refute [hyp #506]. Supermemory's "superset" claim [src #486] is a structural illusion. By trading Zep’s `valid_from` chains for simplified retrieval [src #486], it lacks the lineage to prevent the `hybrid_recency` 0/3 failure. TTL [src #485] is a pruning tool, not a resolution 
  *refs:* —
- **[turn 2, agent 28]** I REJECT [hyp #489]: TTL is a lossy filter, not entropy management. If Supermemory trades Zep’s temporal chains for retrieval ease [src #486], it lacks the resolution to prevent the `hybrid_recency` 0/3 failure. TTL will prune the "chunks" needed to resolve drift [src #485].
  *refs:* —
- **[turn 0, agent 27]** Hypothesis: The "consolidated profile + chunk fallback" pattern is an efficiency trap for blackboard workloads. While Supermemory claims a superset pattern [src #486], I hypothesize that high-frequency writes will cause "profile drift" where the profile becomes a lossy bottleneck
  *refs:* —
- **[turn 0, agent 28]** The "strict superset" view of Supermemory is a trap. I hypothesize that Supermemory’s TTL/forgetting actually *degrades* temporal fidelity in interleaved streams compared to M-Flow's hierarchy, because flat consolidation destroys the causal lineage required to resolve conflicting
  *refs:* —
- **[turn 1, agent 27]** I hypothesize that M-Flow’s hierarchy is required because Supermemory’s "superset" pattern [src #486] collapses structural depth into temporal breadth. I refute [hyp #516]: the profile+chunk fallback isn't an efficiency trap, it's a resolution trap.

Falsifiability: If Supermemor
  *refs:* —
- **[turn 1, agent 28]** I hypothesize that M-Flow’s hierarchy is not redundant but necessary for structural resolution. While Mem0/Supermemory achieve 3/3 fidelity via flat consolidation [src #486], they lack the depth to resolve multi-entity state conflicts in interleaved streams.

**Hypothesis [hyp #5
  *refs:* —
- **[turn 2, agent 27]** I support [hyp #511]: Supermemory’s TTL [src #485] is a blunt instrument. If `hybrid_recency` failed 0/3 by evicting current data [E1], Supermemory's pruning will likely accelerate this by killing the chunk fallback [src #486] before it can resolve profile drift.
  *refs:* —
- **[turn 0, agent 27]** The "consolidated profile + chunk fallback" pattern is a local optimum, not a global one. I hypothesize that for high-frequency blackboard workloads, explicit TTL/forgetting in Supermemory [src #485, #486] will actually *decrease* temporal fidelity compared to Mem0's lack of prun
  *refs:* —
- **[turn 0, agent 28]** Consensus favors consolidation, but I hypothesize that Supermemory’s "strict superset" pattern (profile + chunk fallback) will fail frequent-write blackboard workloads because explicit TTL and consolidation create "semantic blind spots" that M-Flow’s hierarchical cone prevents [s
  *refs:* —
- **[turn 1, agent 28]** I REJECT [hyp #516]. Supermemory’s "superset" [src #486] is a structural illusion. While it adds TTL [src #485], it lacks the hierarchical depth of M-Flow to resolve entity conflicts. I propose [hyp #535]: Supermemory's profile/chunk split creates a "semantic gap" that M-Flow's c
  *refs:* —
- **[turn 2, agent 27]** [hyp #538] I propose: Supermemory’s "superset" [src #486] is a temporal liability for blackboards. If Mem0/Zep hit 3/3 fidelity [src #485], Supermemory’s TTL [src #485] isn't an upgrade—it's a high-pass filter that creates "knowledge gaps" by pruning the context needed for M-Flow
  *refs:* —
- **[turn 2, agent 28]** [hyp #535] I propose: Supermemory’s profile/chunk split creates a "semantic gap" where the profile becomes a stale abstraction and the chunk fallback is too fragmented to bridge it. If TTL [src #485] prunes chunks, M-Flow’s hierarchy is the only way to resolve drift.
  *refs:* —

## critique (25)

- **[turn 0, agent 29]** Your goal assumes "temporal fidelity" is a measurable architectural property, but it’s actually a function of retrieval granularity. If your hybrid relies on `as_of` filters on chunks [src #432], you risk "temporal aliasing"—missing state changes hidden within a single chunk.
  *refs:* —
- **[turn 0, agent 30]** The blindspot is assuming "temporal fidelity" is a metric of retrieval accuracy when it is actually a metric of write-time extraction precision. If your hybrid avoids write-time LLMs [src #432], you aren't measuring fidelity; you're just measuring how well you can filter stale ve
  *refs:* —
- **[turn 1, agent 29]** Your "decision matrix" is a fantasy until you quantify the "semantic smoothing" risk. [hyp #458] is likely true: Mem0/M-Flow's consolidation may erase high-frequency state changes. Without a latency-vs-fidelity curve [src #431], you can't prove your hybrid isn't just "lazy" [src 
  *refs:* —
- **[turn 1, agent 30]** Stop treating "operational fit" as qualitative. You cannot compare your hybrid [src #432] to M-Flow [src #431] without quantifying the LLM-call overhead of M-Flow's coreference indexing vs. your zero-LLM write. Refuting [hyp #457]: drift isn't just hallucination; it's latency.
  *refs:* —
- **[turn 2, agent 29]** The research is currently a collection of unverified intuitions. You cannot claim "operational fit" without quantifying the LLM-call overhead of M-Flow's coreference/graph indexing [src #431] vs. your zero-LLM write [src #432]. I am neutral on [hyp #458] until you prove that Mem0
  *refs:* —
- **[turn 2, agent 29]** You are conflating "structural depth" with "structural latency," but you haven't addressed the fundamental trade-off between consistency and availability in your [hyp #465]. 

Even if the Karpathy+Zep hybrid avoids the write-time LLM overhead [src #432], you are assuming that "simple" vector retrieval is immune to race conditions. If the index update itself is decoupled from the write, you still face a "visibility lag" where a fact exists in the buffer but is invisible to the `as_of` filter. 

Furthermore, your dismissal of M-Flow’s coreference pre-indexing [src #431] as a source of lag ignores a critical counter-example: if the "intelligence" is applied to a shadow index rather than the primary retrieval path, you can achieve structural depth without blocking the temporal stream. You claim Mem0’s consolidation pattern [src #383] exacerbates the gap, but you fail to account for whether a tiered approach—where the hybrid handles the "hot" unrefined stream and M-Flow handles the "cold" structured archive—could actually resolve the race condition rather than just delaying it. Is the goal immediate availability of *raw* data, or immediate availability of *accurate* data?
  *refs:* —
- **[turn 2, agent 29]** You are assuming a zero-sum trade-off between structural depth and temporal fidelity [hyp #465], but you haven't addressed whether the "lag" is a failure of the architecture or a failure of the retrieval logic. 

If the hybrid's advantage is merely "immediate availability" due to lack of write-time LLM overhead [src #432], then you aren't actually proving superior temporal fidelity; you're just proving lower write-latency. A system with high-latency graph construction (Zep [src #412] or M-Flow [src #431]) could still maintain perfect temporal fidelity if the retrieval layer is architected to treat "in-flight" or "unprocessed" raw chunks as a first-class fallback.

Your critique of Mem0’s consolidation step as a "delayed batch process" is a valid concern, but you're missing a counter-example: what if consolidation is used to resolve contradictions rather than just build structure? If you stick to the low-latency simplicity of temporal vector filtering, how do you prevent the "blackboard" from becoming a pile of semantically disconnected noise that lacks the very "structural awareness" you claim to need? You're treating "consistency" and "structure" as the same variable, but they aren't.
  *refs:* —
- **[turn 3, agent 29]** The "structural depth vs. temporal fidelity" trade-off [hyp #465] is unproven without a "stale window" metric. We must decouple write-time LLM cost [src #412, #431] from retrieval-time graph traversal complexity [src #431] to see if M-Flow's "intelligence" actually survives a wri
  *refs:* —
- **[turn 0, agent 29]** The assumption that Supermemory is a "strict superset" of Mem0 [src #486] ignores the fatal tradeoff: by trading Zep’s full `valid_from` temporal chains for simplified retrieval [src #486], you risk losing the very temporal fidelity your research aims to measure.
  *refs:* —
- **[turn 0, agent 30]** The assumption that Supermemory is a "strict superset" [src #486] of Mem0 is a dangerous blindspot. By trading Zep’s `valid_from` temporal chains for simplified retrieval [src #486], you risk losing the very temporal fidelity required to solve the hybrid_recency eviction failure.
  *refs:* —
- **[turn 1, agent 29]** The "strict superset" claim [src #486] is a dangerous simplification. If Supermemory trades Zep's temporal chains for retrieval ease [src #486], it may fail the hybrid_recency test. I refute [hyp #489]: TTL is a patch for entropy, not a scalable solution for high-velocity streams
  *refs:* —
- **[turn 0, agent 29]** The assumption that Supermemory is a "strict superset" [src #486] of Mem0 is a dangerous category error. If Mem0’s flat consolidation already hits 3/3 fidelity, Supermemory’s TTL/forgetting may actually induce catastrophic forgetting in blackboard workloads where "old" data is st
  *refs:* —
- **[turn 0, agent 30]** The fatal flaw is assuming Supermemory is a "strict superset" [src #486] of Mem0. By trading Zep’s `valid_from` temporal chains for consolidated profiles [src #486], you risk losing the exact temporal fidelity you're testing. Consolidation is a lossy compression, not an upgrade.
  *refs:* —
- **[turn 1, agent 30]** The "strict superset" claim [src #486] ignores the risk of "semantic collision" in blackboard workloads. If Supermemory uses TTL to prune [src #485] while simultaneously consolidating profiles [src #486], it may delete the very "chunks" needed to resolve interleaved stream drift.
  *refs:* —
- **[turn 2, agent 29]** Stop treating "strict superset" [src #486] as a feature. If Supermemory uses TTL to prune [src #485] while consolidating profiles [src #486], it creates a "Resolution Paradox": the more it consolidates to save tokens, the more it relies on chunks that TTL is actively killing. I a
  *refs:* —
- **[turn 0, agent 29]** The "strict superset" assumption for Supermemory [src #486] is a trap. If Mem0/Supermemory's flat consolidation achieves 3/3 fidelity, you're ignoring that M-Flow’s hierarchy exists to solve *structural* loss, not just temporal decay. You can't solve depth with TTL.
  *refs:* —
- **[turn 0, agent 30]** The fatal flaw is the assumption that Supermemory is a "strict superset" [src #486] of Mem0. By trading Zep's `valid_from` temporal chains for simpler retrieval [src #486], you risk losing the very temporal fidelity you're testing. Consolidation isn't just "more"; it's lossy.
  *refs:* —
- **[turn 1, agent 29]** The "superset" claim [src #486] ignores the write-time cost of the fallback mechanism. If Supermemory must reconcile a consolidated profile against a pruned chunk set during high-frequency writes, does the overhead scale exponentially? [hyp #516] is unproven.
  *refs:* —
- **[turn 1, agent 30]** Stop conflating "feature count" with "architectural superiority." If Supermemory trades Zep’s `valid_from` chains for retrieval ease [src #486], it isn't a superset; it's a different trade-off. I REJECT [hyp #516]: the "fallback" is a latency bomb in blackboard workloads.
  *refs:* —
- **[turn 2, agent 29]** The "superset" claim [src #486] is a category error. Mem0 optimizes for density; Supermemory adds pruning [src #485]. Neither addresses the *structural* resolution M-Flow provides. I support [hyp #522]: Supermemory's pattern is a resolution trap, not an efficiency fix.
  *refs:* —
- **[turn 2, agent 30]** The "superset" claim [src #486] is a category error. If Mem0/Supermemory's flat consolidation achieves 3/3 fidelity, you are ignoring the *resolution* required for multi-entity state conflicts. I support [hyp #522]: Supermemory's pattern collapses structural depth into temporal b
  *refs:* —
- **[turn 0, agent 29]** The blindspot is the assumption that Supermemory is a "strict superset" [src #486] of Mem0. By prioritizing profile consolidation over Zep’s `valid_from` chains [src #486], you risk losing the very temporal provenance required to solve the hybrid_recency eviction failure.
  *refs:* —
- **[turn 0, agent 30]** The "strict superset" assumption [src #486] is a trap: Supermemory's TTL/forgetting isn't just an add-on, it's a destructive filter. If your blackboard workload requires auditability, Supermemory's loss of Zep's `valid_from` history [src #486] falsifies its utility.
  *refs:* —
- **[turn 1, agent 30]** The "strict superset" claim [src #486] is a logical fallacy if it ignores the cost of reconciliation. I support [hyp #516]: if TTL [src #485] prunes the chunk fallback [src #486] needed to resolve profile drift, Supermemory isn't a superset; it's a high-entropy trap.
  *refs:* —
- **[turn 2, agent 30]** The "strict superset" claim [src #486] ignores the write-time cost of the chunk fallback. If Mem0/Zep achieve 3/3 fidelity [src #485], Supermemory’s extra layer isn't an upgrade; it's a latency tax. I support [hyp #534]: consolidation creates "semantic blind spots."
  *refs:* —

## draft (5)

- **[turn 4, system]** ## Executive summary

This report evaluates four agent-memory architectures to determine their suitability for frequent-write "blackboard" workloads, focusing on the trade-offs between temporal fidelity, operational cost, and structural depth. The current internal architecture—a Karpathy+Zep hybrid—utilizes chunks tagged with `t_ref` and cosine retrieval with an `as_of` filter, avoiding write-time LLM overhead [agent-memory-architecture.md]. 

The analysis identifies a fundamental tension between "structural depth" (the ability to represent complex, evolving relationships) and "temporal fidelity" (the immediate availability and accuracy of high-frequency state changes). While architectures like Zep and M-Flow offer superior structural intelligence through graph construction and coreference indexing, they introduce significant risks regarding "consistency lag" and "read-time taxes" that may render them unsuitable for high-velocity environments.

## Evidence surfaced

### Architecture Profiles
*   **Karpathy+Zep Hybrid (Internal):** Employs a three-tier hybrid memory [agent-memory-architecture.md]. It uses simple chunks tagged with `t_ref` and cosine retrieval with an `as_of` filter. It features zero write-time LLM overhead [agent-memory-architecture.md].
*   **Zep Temporal Knowledge Graph:** Utilizes a "Graphiti" engine to build dynamic, temporally aware knowledge graphs [zep-temporal-knowledge-graph.pdf]. It employs `gpt-4o-mini` for entity-attribute-value (EAV) triple extraction and graph construction [zep-temporal-knowledge-graph.pdf]. It demonstrates high performance in Deep Memory Retrieval (DMR) (94.8%) and LongMemEval [zep-temporal-knowledge-graph.pdf].
*   **Mem0:** Implements a dynamic extract-consolidate-retrieve pattern [agent-memory-architecture.md].
*   **M-Flow:** Features a four-level inverted cone structure (Episode/Facet/FacetPoint/Entity) [agent-memory-architecture.md]. It utilizes graph path-cost retrieval and coreference pre-indexing during a "memorize" step [agent-memory-architecture.md].

### Comparative Dimensions
*   **Write-Time Cost:** M-Flow and Zep incur high costs due to LLM-driven graph construction and coreference indexing [agent-memory-architecture.md]. The hybrid architecture maintains a low-cost, zero-LLM write profile [agent-memory-architecture.md].
*   **Read-Time Cost:** M-Flow introduces a "Read-Time Tax" due to the complexity of traversing inverted cones and graph paths compared to the hybrid's flat KNN retrieval [agent_27].
*   **Temporal Fidelity:** High-velocity workloads in Zep and M-Flow may suffer from "consistency lag," where retrieval queries hit stale or partially-constructed states during the window between observation and structural integration [agent_27].

## Hypotheses advanced

### [STATE: UNDER_TEST]
*   **Hypothesis #465 (Consistency Lag):** In high-velocity 'blackboard' workloads, the primary failure mode is not semantic drift, but index-write race conditions. The "intelligence" of memory (Zep/M-Flow) is inversely proportional to its temporal fidelity; structural depth creates a window where retrieval hits stale states [agent_27].
*   **Hypothesis #474 (Retrieval-Induced Hallucination):** Querying a partially-indexed graph in M-Flow or Zep creates a "false void" where missing edges lead to hallucinations during the window of structural incompleteness [agent_27].
*   **Hypothesis #458 (Semantic Smoothing):** High-fidelity extraction/consolidation in Mem0/M-Flow may act as a "structural resolution floor," effectively "smoothing out" transient, high-frequency state changes and erasing ground truth [agent_28].

### [STATE: UNPROVEN/DEBATED]
*   **Hypothesis #457 (Fidelity Bottleneck):** High-fidelity extraction is a liability in high-velocity workloads because write-time LLM overhead creates a bottleneck [agent_28].
*   **Hypothesis #463 (Latency Wall):** M-Flow’s coreference pre-indexing creates a latency wall that renders it non-viable for blackboard workloads due to scaling costs with entity density [agent_27].

## Critiques & open questions

### Critiques
*   **Qualitative vs. Quantitative:** Critics argue that "operational fit" cannot be claimed without quantifying the specific LLM-call overhead of M-Flow's indexing versus the hybrid's zero-LLM write [agent_29, agent_30].
*   **Conflation of Variables:** There is a critique that the current reasoning conflates "structural depth" with "structural latency" and fails to distinguish between "consistency" and "availability" [agent_29].
*   **The "Stale Window" Metric:** The trade-off between depth and fidelity is unproven without a formal metric to measure the "stale window" during index updates [agent_29].

### Open Questions
*   **Contradiction Resolution:** How do M-Flow or Zep handle explicit contradictions (e.g., an entity's role changing between two documents)? [m_flow_notes.md]
*   **Complexity vs. Single-Store:** What is the operational cost difference between a single-store approach (hybrid) and a dual Graph DB + Vector DB approach (M-Flow/Zep)? [m_flow_notes.md]
*   **Input Noise:** Does coreference pre-indexing assume clean conversational input, and if so, how does it perform on noisy research corpora? [m_flow_notes.md]

## Recommended next steps

1.  **Quantify the "Read-Time Tax":** Benchmark the latency of M-Flow's graph path-cost retrieval against the hybrid's flat KNN retrieval [agent_27].
2.  **Measure the "Stale Window":** Implement a test to measure the time delta between a write event and its availability via `as_of` filtering in the hybrid vs. its availability in a structured graph (Zep/M-Flow) [agent_29].
3.  **Evaluate Tiered Architecture:** Investigate a hybrid approach where the current temporal vector filter handles the "hot" unrefined stream (immediate availability) while a structured process (M-Flow/Zep style) handles the "cold" structured archive (structural depth) [agent_29].
4.  **Cost-Benefit Analysis of Coreference:** Determine if the precision gains from M-Flow's coreference pre-indexing justify the LLM-call overhead in high-density entity environments [agent_30].
  *refs:* —
- **[turn 4, system]** ## Executive summary

This report evaluates five agent-memory architectures—Karpathy+Zep hybrid, Zep temporal knowledge graph, Mem0 (extract-consolidate), M-Flow (four-level hierarchy), and Supermemory (consolidated profile + chunk fallback + TTL)—to determine their suitability for frequent-write "blackboard" workloads. Empirical data from the E1 benchmark (2026-04-24) indicates that while Mem0 and Zep-lite achieve high temporal fidelity (3/3), the current Karpathy+Zep hybrid suffers from `hybrid_recency` failures where global recency windows evict older but still relevant entity data. The analysis focuses on the trade-offs between structural depth (M-Flow/Zep) and immediate availability (Hybrid/Mem0), specifically examining whether Supermemory’s profile-plus-fallback pattern offers a superior path for our architecture.

## Evidence surfaced

### Comparative Architectures
*   **Karpathy+Zep Hybrid (Current):** Utilizes chunks tagged with `t_ref` and cosine retrieval with an `as_of` filter (agent_27, hyp #465). It avoids write-time LLM overhead but lacks structural awareness (agent_27, hyp #465).
*   **Zep Temporal Knowledge Graph:** Employs `gpt-4o-mini` for EAV triple extraction (agent_27, hyp #465). It accumulates history using `valid_from` markers, allowing for temporal chains, but suffers from significant operational delays and high token consumption (600k+ tokens) due to redundant abstractive summaries (agent_None, mem0.pdf).
*   **Mem0 (Extract-Consolidate):** Uses a dense memory pipeline for rapid retrieval. It employs an "extract-consolidate" pattern that overwrites information rather than retaining a full history (agent_None, supermemory_notes.md). It is significantly more token-efficient than Zep (7k vs 600k tokens) and offers faster memory availability (agent_None, mem0.pdf).
*   **M-Flow:** Features a four-level Episode/Facet/FacetPoint/Entity hierarchy. It utilizes a "memorize" step involving coreference pre-indexing and graph construction (agent_None, m_flow_notes.md).
*   **Supermemory:** Implements a consolidated profile layer alongside a chunk fallback (agent_None, supermemory_notes.md). It introduces explicit "forgetting" via TTL/decay, which is distinct from Mem0's overwrite-only semantics and Zep's history-retention semantics (agent_None, supermemory_notes.md).

### Performance Metrics (E1 Benchmark)
*   **Temporal Fidelity:** `zep_lite` (3/3) and `mem0_lite` (3/3) outperform `hybrid_flat` (1/3) and `hybrid_recency` (0/3) (Goal Context).
*   **Ingest Latency:** `mem0_lite` achieves 3/3 fidelity at 53s ingest, while `zep_lite` requires 101s (Goal Context).

## Hypotheses advanced

### [STATE: UNDER_TEST]
*   **Hypothesis #465 (Consistency vs. Depth):** In high-velocity blackboard workloads, the "intelligence" of a memory system (Zep/M-Flow) is inversely proportional to its temporal fidelity. Structural depth (graph construction/coreference) creates a "consistency lag" where retrieval hits stale or partially-constructed states (agent_27, hyp #465).
*   **Hypothesis #474 (Retrieval-Induced Hallucination):** Querying a partially-indexed graph in M-Flow or Zep creates a "false void" where missing edges lead to hallucinations during the window of structural incompleteness (agent_27, hyp #474).

### [STATE: REFUTED]
*   **Hypothesis #489 (Supermemory as Strict Superset):** The claim that Supermemory is a strict superset of Mem0 is a category error regarding temporal fidelity. Supermemory's TTL is a lossy filter that may accelerate the `hybrid_recency` eviction failure observed in E1 (agent_28, hyp #489).

### [STATE: PROPOSED]
*   **Hypothesis #465 (Blackboard Bottleneck):** The primary failure mode for high-frequency write workloads is not semantic drift, but index-write race conditions and the "consistency lag" between observation and structural integration (agent_27, hyp #465).

## Critiques & open questions

### Critiques
*   **Structural vs. Temporal Trade-off:** Critics argue that the perceived "lag" in Zep or M-Flow may be a failure of retrieval logic rather than architecture. A system could maintain fidelity if the retrieval layer treats "in-flight" raw chunks as a first-class fallback (agent_29, critique).
*   **Quantification Gap:** Current comparisons lack a "stale window" metric to decouple write-time LLM cost from retrieval-time graph traversal complexity (agent_29, critique). There is also a need to quantify the "semantic smoothing" risk, where consolidation might erase high-frequency state changes (agent_29, critique).
*   **Operational Complexity:** The "operational fit" remains qualitative; the research must quantify the LLM-call overhead of M-Flow's coreference indexing against the zero-LLM write of the current hybrid (agent_30, critique).

### Open Questions
*   **M-Flow Necessity:** Given that Mem0 and Supermemory's flat consolidation already achieve 3/3 fidelity, is M-Flow's four-level graph hierarchy still required for agentic workloads? (Goal Context).
*   **Contradiction Resolution:** How do M-Flow or Zep handle explicit contradictions (e.g., Alice is CEO vs. Bob is CEO) during the indexing window? (agent_None, m_flow_notes.md).

## Recommended next steps

1.  **Architectural Pivot:** Evaluate the adoption of the Supermemory pattern—pairing a consolidated profile layer with a chunk fallback—as a potential "strict superset" to resolve the current hybrid's lack of structural awareness (agent_None, supermemory_notes.md).
2.  **Tiered Implementation:** Investigate a tiered approach where the current hybrid handles the "hot" unrefined stream (immediate availability) while a more structured system (M-Flow or Mem0) handles the "cold" structured archive to resolve the consistency-availability trade-off (agent_29, critique).
3.  **Metric Development:** Define and implement a "stale window" metric and a "latency-vs-fidelity" curve to empirically test the "consistency lag" hypothesis (agent_29, critique).
4.  **TTL Stress Test:** Conduct targeted testing of Supermemory's TTL/forgetting mechanism in interleaved stream scenarios to determine if it mitigates or exacerbates the `hybrid_recency` eviction failure (agent_28, hyp #489).
  *refs:* —
- **[turn 4, system]** ## Executive summary

This report evaluates five agent-memory architectures—Karpathy+Zep hybrid, Zep temporal knowledge graph, Mem0 (extract-consolidate), M-Flow (four-level hierarchy), and Supermemory (consolidated profile + chunk fallback + TTL)—specifically for frequent-write "blackboard" workloads. Empirical context from the E1 benchmark (2026-04-24) indicates that while Mem0 and Zep-lite achieve high temporal fidelity (3/3), the current Karpathy+Zep hybrid suffers from `hybrid_recency` failures (0/3), where global recency windows evict older but still current entity data during interleaved streams. The analysis focuses on whether Supermemory’s architectural patterns offer a viable path for the hybrid's evolution or if they introduce new failure modes like "Profile-Drift Collapse."

## Evidence surfaced

### Architectural Comparisons
*   **Supermemory vs. Mem0**: Supermemory is characterized as a "strict superset" of Mem0, adding explicit TTL/forgetting and a chunk fallback mechanism to Mem0's extract-consolidate pattern (supermemory_notes.md).
*   **Supermemory vs. Zep**: Supermemory trades Zep's full temporal history (the `valid_from` chain) for simpler retrieval and explicit forgetting (supermemory_notes.md).
*   **Supermemory vs. M-Flow**: Unlike M-Flow's four-level Episode/Facet/FacetPoint/Entity cone hierarchy, Supermemory utilizes a flatter structure consisting of a consolidated profile paired with chunk fallback (supermemory_notes.md).
*   **Supermemory vs. Current Hybrid**: The current hybrid relies on chunks-only with `t_ref` tags (agent-memory-architecture.md). Supermemory adds a consolidated profile layer on top of the chunk store (supermemory_notes.md).

### Performance and Operational Metrics
*   **Ingest Latency**: In E1 benchmarks, `zep_lite` achieved 3/3 fidelity at 101s ingest, while `mem0_lite` achieved 3/3 fidelity at 53s ingest (empirical context).
*   **Token Efficiency**: Mem0 encodes dialogue turns in natural language, averaging 7k tokens per conversation, whereas Zep’s graph consumes >600k tokens due to redundant abstractive summaries at every node (mem0.pdf).
*   **Retrieval Speed**: Supermemory's hybrid search (RAG + structured profile) is reported at ~50ms for user profiles (supermemory_notes.md).

## Hypotheses advanced

### [STATE: UNDER_TEST]
*   **Consistency Lag Hypothesis (hyp #465)**: In high-velocity blackboard workloads, the "intelligence" of a memory system (Zep/M-Flow) is inversely proportional to its temporal fidelity. The time required for structural integration (e.g., M-Flow's coreference indexing or Zep's graph construction) creates a window where retrieval hits stale or partially-constructed states (agent_27).
*   **M-Flow Latency Wall (hyp #457)**: M-Flow’s coreference pre-indexing creates a write-time LLM cost that scales with entity density, potentially rendering it non-viable for high-velocity blackboard workloads (agent_27).
*   **Read-Time Tax (hyp #463)**: The retrieval complexity of M-Flow's inverted cone/graph paths will result in higher read-time costs compared to the hybrid's flat KNN retrieval (agent_27).

### [STATE: REFUTED]
*   **Supermemory "Strict Superset" Utility (hyp #486)**: The claim that Supermemory is a strict superset is a "lie of omission" (agent_28). Because it trades Zep's temporal lineage for retrieval ease, it lacks the resolution to prevent the `hybrid_recency` 0/3 failure (agent_27, agent_28).
*   **TTL as Entropy Management (hyp #489)**: TTL is a lossy filter, not an entropy management tool. In interleaved streams, TTL may accelerate the eviction of necessary chunks, leading to "Profile-Drift Collapse" (agent_28, agent_27).

## Critiques & open questions

### Critiques
*   **The Resolution Paradox (agent_29, agent_30)**: Critics argue that Supermemory's combination of profile consolidation and TTL creates a paradox: the more the system consolidates to save tokens, the more it relies on the very chunks that the TTL mechanism is actively pruning (agent_30).
*   **Structural vs. Temporal Trade-offs (agent_29)**: The assumption that structural depth and temporal fidelity are a zero-sum game is unproven. A system could maintain perfect temporal fidelity if the retrieval layer treats "in-flight" or "unprocessed" raw chunks as a first-class fallback (agent_29).
*   **Semantic Smoothing (agent_29)**: There is a risk of "semantic smoothing" where Mem0/M-Flow's consolidation erases high-frequency state changes, effectively hiding the very volatility a blackboard workload needs to track (agent_29).

### Open Questions
*   **M-Flow Write-Time Cost**: What is the exact LLM call overhead for M-Flow's "memorize" step (coreference + graph construction)? (m_flow_notes.md).
*   **Contradiction Resolution**: In an E4 scenario (e.g., Alice is CEO vs. Bob is CEO), how does M-Flow's episodic bundle resolve the conflict? (m_flow_notes.md).
*   **Shadow Indexing**: Can structural depth be achieved without blocking the temporal stream by applying "intelligence" to a shadow index rather than the primary retrieval path? (agent_29).

## Recommended next steps

1.  **Quantify the "Stale Window"**: Develop a metric to measure the gap between a fact being observed and its structural integration to test the Consistency Lag Hypothesis (agent_29).
2.  **Test Tiered Architecture**: Evaluate a "hot/cold" memory model where the current hybrid handles the "hot" unrefined stream (low latency) and a structured system (like M-Flow or Mem0g) handles the "cold" structured archive (agent_29).
3.  **Benchmark Supermemory TTL**: Specifically test Supermemory's TTL behavior against the `hybrid_recency` failure mode to see if it mitigates or exacerbates the eviction of interleaved entity data.
4.  **Profile-Chunk Integration**: Determine if adopting Supermemory's "consolidated-profile + chunk-fallback" pattern provides the necessary stress-test resilience for the hybrid, or if it introduces "Profile-Drift Collapse."
  *refs:* —
- **[turn 4, system]** ## Executive summary

This report evaluates five agent-memory architectures—(1) Karpathy+Zep hybrid, (2) Zep temporal knowledge graph, (3) Mem0 (extract-consolidate), (4) M-Flow (four-level hierarchy), and (5) Supermemory (consolidated profile + chunk fallback + TTL)—specifically for frequent-write "blackboard" workloads. 

Empirical context from the E1 benchmark (2026-04-24) indicates that simple recency-based eviction (`hybrid_recency`) fails (0/3) when interleaved streams cause the eviction of current entity data. While Mem0 and Zep show varying levels of efficiency and latency, Supermemory introduces a novel temporal axis via explicit Time-To-Live (TTL) and forgetting mechanisms. However, there is significant debate regarding whether Supermemory’s "strict superset" pattern (consolidated profile + chunk fallback) provides a robust solution or introduces new failure modes like "Profile-Drift Collapse" or "Resolution Traps" in high-velocity environments.

## Evidence surfaced

### Architecture & Temporal Handling
*   **Supermemory**: Features four distinct temporal behaviors: automatic fact extraction, user profile maintenance, contradiction handling (overwrite semantics where newer facts supersede older ones), and explicit forgetting via TTL/decay (supermemory_notes.md).
*   **Mem0**: Utilizes an extract-consolidate pattern. It employs overwrite semantics but lacks explicit history retention or TTL (supermemory_notes.md).
*   **Zep**: Uses a temporal knowledge graph with `valid_from` chains, allowing for the retention of historical triples even when marked stale by newer data (supermemory_notes.md).
*   **M-Flow**: Employs a four-level hierarchy (Episode/Facet/FacetPoint/Entity) and utilizes coreference pre-indexing during a "memorize" step (m_flow_notes.md, supermemory_notes.md).
*   **Karpathy+Zep Hybrid**: Currently utilizes a chunk-only approach with `t_ref` tags and cosine retrieval with an `as_of` filter (agent-memory-architecture.md).

### Performance & Operational Metrics
*   **Ingest/Latency**: Mem0_lite achieved 3/3 fidelity at 53s ingest, while Zep_lite achieved 3/3 at 101s (E1 benchmark context). Mem0 graph construction completes in under a minute, whereas Zep's graph construction involves asynchronous LLM calls that can cause immediate retrieval failures (mem0.pdf).
*   **Token Efficiency**: Mem0 encodes dialogue turns at ~7k tokens per conversation, significantly more efficient than Zep’s graph, which can exceed 600k tokens due to redundant abstractive summaries at every node (mem0.pdf).
*   **Retrieval**: Supermemory offers hybrid search (profile + chunk) with reported ~50ms latency for user profiles (supermemory_notes.md).

## Hypotheses advanced

### UNDER_TEST
*   **[hyp #465] Consistency Lag Hypothesis**: In high-velocity workloads, the "intelligence" of a memory system (Zep/M-Flow) is inversely proportional to its temporal fidelity. The time required for structural integration (coreference/graph construction) creates a window where queries hit stale or partially-constructed states (agent_27).
*   **[hyp #516] Fallback Latency Bomb**: The Supermemory pattern of reconciling a consolidated profile against a pruned chunk set during high-frequency writes may create an exponential overhead or a "latency bomb" (agent_30, agent_29).

### REFUTED
*   **[hyp #506] Supermemory as Strict Superset**: The claim that Supermemory is a strict superset of Mem0 is a "structural illusion." By trading Zep’s `valid_from` lineage for simplified retrieval, it lacks the resolution to prevent `hybrid_recency` style failures (agent_27, agent_28).
*   **[hyp #489] TTL as Entropy Management**: TTL is a lossy filter/pruning tool, not a scalable solution for managing entropy in high-velocity streams; it may actually accelerate the loss of necessary context (agent_28, agent_27).

## Critiques & open questions

### Critiques
*   **Structural vs. Temporal Trade-offs**: Critics argue that the debate over "structural depth vs. temporal fidelity" may be a category error. A system could maintain high temporal fidelity if the retrieval layer treats "in-flight" raw chunks as a first-class fallback (agent_29).
*   **Resolution Traps**: There is concern that Supermemory's pattern is a "resolution trap." If TTL prunes the very chunks needed to resolve contradictions or profile drift, the system loses its ability to maintain accuracy (agent_27, agent_28, agent_30).
*   **Feature Count vs. Architecture**: Critics warn against conflating a higher feature count (e.g., Supermemory's TTL + Profile) with architectural superiority (agent_30).

### Open Questions
*   **M-Flow Necessity**: Given that Mem0 and Supermemory achieve 3/3 fidelity with flat consolidation, is M-Flow's four-level graph hierarchy still required for specific use cases? (Goal context).
*   **Write-time Cost**: What is the exact LLM cost per document for M-Flow's coreference and graph construction steps? (m_flow_notes.md).
*   **Scaling of Fallback**: Does the overhead of reconciling profiles against chunk fallbacks scale exponentially under high-frequency writes? (agent_29).

## Recommended next steps

1.  **Quantify the "Stale Window"**: Implement a metric to measure the time delta between a fact's observation and its availability in structured retrieval to test the Consistency Lag hypothesis (agent_29).
2.  **Stress-test Supermemory TTL**: Run E1-style interleaved stream benchmarks on Supermemory to determine if TTL-driven pruning exacerbates the `hybrid_recency` 0/3 failure mode (agent_27).
3.  **Evaluate Tiered Architectures**: Investigate a hybrid approach where a low-latency vector store handles "hot" unrefined streams while a structured system (like M-Flow or Zep) handles the "cold" structured archive to mitigate the consistency-availability trade-off (agent_29).
4.  **Benchmark M-Flow Write-Latency**: Specifically measure the write-time LLM cost and latency of M-Flow's "memorize" step to determine its operational fit for blackboard workloads (agent_27).
  *refs:* —
- **[turn 4, system]** ## Executive summary

This report evaluates five agent-memory architectures—Karpathy+Zep hybrid, Zep temporal knowledge graph, Mem0 (extract-consolidate), M-Flow (four-level hierarchy), and Supermemory (consolidated profile + chunk fallback + TTL)—against the requirements of frequent-write "blackboard" workloads. Empirical data from the E1 benchmark (2026-04-24) indicates that while Mem0 and Zep-lite achieve 3/3 temporal fidelity, the current Karpathy+Zep hybrid suffers from `hybrid_recency` failures (0/3), where global recency windows evict critical interleaved entity data. The analysis focuses on whether Supermemory’s architecture represents a "strict superset" of Mem0 or introduces new temporal liabilities via its TTL and consolidation mechanisms.

## Evidence surfaced

### Architectural Comparisons
*   **Supermemory vs. Mem0**: Supermemory is characterized as a "strict superset" of Mem0's extract-consolidate pattern, adding explicit TTL/forgetting and a chunk fallback mechanism alongside the consolidated profile (supermemory_notes.md).
*   **Supermemory vs. Zep**: Supermemory trades Zep’s full temporal history (`valid_from` chains) for simpler retrieval and explicit forgetting (supermemory_notes.md).
*   **Supermemory vs. M-Flow**: Unlike M-Flow’s four-level Episode/Facet/FacetPoint/Entity cone hierarchy, Supermemory utilizes a flatter structure consisting of a consolidated profile paired with a chunk fallback (supermemory_notes.md).
*   **Supermemory vs. Current Hybrid**: The current research-pipeline hybrid utilizes a three-tier approach with chunks tagged with `t_ref` for cosine retrieval (agent-memory-architecture.md). Supermemory adds a consolidated profile layer on top of this chunk store (supermemory_notes.md).

### Performance & Operational Metrics
*   **Temporal Fidelity**: Mem0-lite and Zep-lite both achieved 3/3 fidelity at specific ingest rates (53s and 101s respectively) (E1 benchmark context).
*   **Zep Operational Overhead**: Zep’s memory graph is noted for extreme token inefficiency (600k+ tokens) and significant operational latency, where immediate retrieval often fails until background asynchronous LLM calls complete (mem0.pdf).
*   **Mem0 Efficiency**: Mem0 achieves high responsiveness, with graph construction completing in under a minute, and maintains a significantly lower token footprint (approx. 7k tokens per conversation) compared to Zep (mem0.pdf).

## Hypotheses advanced

### [STATE: REFUTED]
*   **The "Strict Superset" Utility (agent_27, agent_28, agent_29, agent_30)**: The claim that Supermemory is a strict superset of Mem0 is refuted as a "structural illusion" or "lie of omission." While it adds features like TTL, it lacks the structured lineage of M-Flow or the `valid_from` temporal chains of Zep, potentially making it a different trade-off rather than an upgrade (supermemory_notes.md; agent_27; agent_29).

### [STATE: UNDER_TEST]
*   **Profile-Drift Collapse (agent_28)**: In blackboard workloads, frequent writes may cause Supermemory to suffer "Profile-Drift Collapse," where rapid consolidation erodes structural depth (supermemory_notes.md).
*   **The Consistency-Intelligence Trade-off (agent_27)**: For high-velocity workloads, the "intelligence" of a memory system (Zep/M-Flow) is inversely proportional to its temporal fidelity due to the "consistency lag" between observation and structural integration (agent_27).
*   **TTL as a High-Pass Filter (agent_27, agent_28)**: Supermemory’s TTL may act as a high-pass filter that creates "knowledge gaps" by pruning context required for resolution, potentially exacerbating the `hybrid_recency` 0/3 failure (supermemory_notes.md; agent_27).
*   **Semantic Gap/Collision (agent_28, agent_30)**: The split between profile and chunk fallback may create a "semantic gap" or "semantic collision" where the system deletes chunks necessary to resolve interleaved stream drift (supermemory_notes.md; agent_30).

## Critiques & open questions

### Critiques
*   **Structural vs. Temporal Latency (agent_29)**: Critics argue that the "lag" observed in complex architectures (Zep/M-Flow) may be a failure of retrieval logic rather than architecture. A system could maintain perfect fidelity if "in-flight" raw chunks are treated as a first-class fallback (agent_29).
*   **Feature Count vs. Architecture (agent_30)**: There is a critique against conflating "feature count" with "architectural superiority," noting that Supermemory's extra layers may function as a "latency tax" rather than an upgrade (agent_30).
*   **The "Visibility Lag" (agent_29)**: Even with low-latency vector retrieval, if index updates are decoupled from writes, a "visibility lag" remains where facts exist in the buffer but are invisible to `as_of` filters (agent_29).

### Open Questions
*   **M-Flow Necessity**: Given that Mem0/Supermemory's flat consolidation achieves 3/3 fidelity, is M-Flow's hierarchical graph still required for specific relational tasks? (Goal context).
*   **Write-time Cost**: What is the specific LLM cost per document for M-Flow's "memorize" step involving coreference and graph construction? (m_flow_notes.md).
*   **Scaling Overhead**: Does the overhead of reconciling a consolidated profile against a pruned chunk set scale exponentially during high-frequency writes? (agent_29).

## Recommended next steps

1.  **Implement Tiered "Hot/Cold" Architecture**: Explore a model where the current hybrid handles the "hot" unrefined stream (immediate availability) while a more structured system (like M-Flow) handles the "cold" structured archive to mitigate the consistency-availability trade-off (agent_29).
2.  **Quantify the "Stale Window"**: Develop a metric to decouple write-time LLM cost from retrieval-time graph traversal complexity to determine if structural depth survives high-velocity bursts (agent_29).
3.  **Stress-test Supermemory TTL**: Validate whether Supermemory's TTL/forgetting mechanism triggers the same 0/3 failure seen in `hybrid_recency` by monitoring for "knowledge gaps" in interleaved streams.
4.  **Evaluate Profile+Chunk Fallback**: Determine if the Supermemory pattern is a viable "superset" for the current hybrid or if it introduces a "resolution trap" that collapses structural depth (agent_27).
  *refs:* —

## review (28)

- **[turn 0, agent 31]** The single most load-bearing criterion is the **empirical verification of the trade-off between write-time LLM overhead and temporal retrieval precision.**

To be **unambiguously positive**, the research must provide a multi-dimensional cost-benefit curve showing that the Karpath
  *refs:* —
- **[turn 0, agent 32]** To achieve an unambiguously positive review, you must provide a rigorous latency-vs-fidelity tradeoff analysis; a negative review will stem from treating "operational fit" as qualitative rather than measuring the exact LLM-call overhead of M-Flow's coreference indexing [src #431]
  *refs:* —
- **[turn 1, agent 31]** The current research lacks the empirical cost-benefit curve required to validate [hyp #457]. Without a quantified latency breakdown comparing our write-free hybrid [src #432] against M-Flow’s coreference/graph overhead [src #431], "operational fit" remains anecdotal.
  *refs:* —
- **[turn 1, agent 32]** The research is currently speculative. To validate [hyp #457], you must quantify "semantic drift." Compare the error rate of your chunk-based `as_of` filter [src #432] against Zep’s LLM-driven extraction [src #412] under high-frequency write stress. Neutral on [hyp #458] until la
  *refs:* —
- **[turn 2, agent 31]** The decision matrix is incomplete without a "granularity floor." While [hyp #458] warns of semantic smoothing, the real risk is that your hybrid's chunk-level `as_of` filter [src #432] lacks the resolution to capture sub-chunk state transitions, making it blind to intra-chunk vol
  *refs:* —
- **[turn 2, agent 31]** Your hypothesis regarding the inverse relationship between structural intelligence and temporal fidelity is compelling, but it currently lacks a rigorous control for "structural debt." You are assuming the bottleneck is purely the write-time latency of the LLM [src #412], but you haven't accounted for the retrieval-time complexity overhead that M-Flow’s inverted cone architecture might impose [src #431].

To move this from a hypothesis to a peer-reviewed claim, you must decouple "consistency lag" (the time to index) from "retrieval staleness" (the accuracy of the result). If M-Flow's coreference pre-indexing [src #431] is computationally heavy, does the failure mode stem from the write-delay, or from the retrieval engine attempting to traverse an incomplete graph?

Before recommending a move toward asynchronous coreference, you need to quantify the "write-time cost per document" for M-Flow [src #431]. Without a baseline of LLM calls per write, you cannot prove that the hybrid's simplicity is a feature of speed rather than a byproduct of structural deficiency.
  *refs:* —
- **[turn 3, agent 31]** To move beyond intuition, we must decouple "consistency lag" from "retrieval staleness." I am NEUTRAL on [hyp #465] until we quantify M-Flow's write-time LLM cost [src #431] vs. the hybrid's availability [src #432] under burst-write stress. We need a "stale window" metric.
  *refs:* —
- **[turn 3, agent 32]** To validate [hyp #465], we must move beyond "lag" and test "structural fragmentation." Does M-Flow’s coreference [src #431] or Zep’s EAV triples [src #412] create "ghost entities" during bursts? We need a metric for *structural completeness* at $t_{now}$ vs $t_{event}$.
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 5, "evidence_density": 4, "rigor": 4, "clarity": 5, "actionability": 4}, "assessment": "An exceptionally structured report that successfully frames the technical trade-offs between structural intelligence and temporal fidelity through a sophisticated hypothesis-driven lens. The distinction between 'structural depth' and 'consistency lag' provides a high-level conceptual framework that is rare in technical evaluations.", "revisions": ["Include a quantitative cost-per-write comparison (e.g., estimated tokens/latency) to resolve the 'Qualitative vs. Quantitative' critique mentioned in the text.", "Formalize the 'Stale Window' metric into a mathematical definition or a specific testing protocol to move Hypothesis #465 from 'Under Test' to 'Proven'.", "Explicitly address the 'Decision Matrix' requested in the goal, as the draft provides excellent analysis but lacks the final summary table/matrix format."]}
  *refs:* —
- **[turn 0, agent 31]** The single most load-bearing criterion for this research is **the empirical validation of the "strict superset" claim**: you must prove that Supermemory’s TTL and chunk-fallback provide a statistically significant advantage in temporal fidelity for interleaved streams compared to
  *refs:* —
- **[turn 0, agent 32]** **Peer Review Assessment**

To move this research from "exploratory" to "publishable," you must bridge the gap between architectural description and empirical validation.

### The Load-Bearing Criterion
**The empirical verification of the "Strict Superset" claim via the trade-off
  *refs:* —
- **[turn 1, agent 31]** I REJECT the "strict superset" claim [src #486] as a methodological error. By trading Zep’s `valid_from` chains for simplified retrieval [src #486], Supermemory may lack the temporal resolution to fix the `hybrid_recency` eviction failure. I am NEUTRAL on [hyp #488] until we test
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 5, "evidence_density": 4, "rigor": 4, "clarity": 5, "actionability": 4}, "assessment": "An exceptionally high-quality technical report that effectively synthesizes empirical benchmark data with architectural theory to address a specific engineering bottleneck. The distinction between 'consistency lag' and 'semantic drift' provides a sophisticated framework for decision-making.", "revisions": ["Quantify the 'operational fit' by adding a projected cost-per-write (token/latency) comparison between the zero-LLM hybrid and the M-Flow/Zep architectures.", "Explicitly address the 'M-Flow Necessity' question in the Executive Summary or a dedicated 'Synthesis' section to provide a definitive stance for stakeholders.", "Include a formal definition of the 'stale window' metric to ensure the proposed next steps are measurable and reproducible."]}
  *refs:* —
- **[turn 0, agent 31]** The single most load-bearing criterion for this research is **the empirical verification of the "strict superset" claim**: specifically, whether Supermemory’s explicit TTL and chunk fallback actually mitigate the "interleaved stream eviction" failure seen in your `hybrid_recency`
  *refs:* —
- **[turn 0, agent 32]** The single most load-bearing criterion is **the empirical validation of the "strict superset" hypothesis**: you must prove that Supermemory’s TTL and chunk fallback actually solve the "interleaved stream eviction" seen in your hybrid_recency (0/3) [src #432], rather than just add
  *refs:* —
- **[turn 1, agent 31]** The "strict superset" claim [src #486] lacks empirical rigor for blackboard workloads. I REJECT [hyp #489]: TTL is a lossy filter, not an entropy management tool. If Supermemory trades Zep’s temporal chains for retrieval ease [src #486], it risks the hybrid_recency failure.
  *refs:* —
- **[turn 1, agent 32]** We cannot validate the "strict superset" claim [src #486] without quantifying the "consolidation-to-chunk" ratio. If Supermemory's profile consolidation collapses high-velocity blackboard updates into a single state, the chunk fallback becomes a graveyard of stale data.
  *refs:* —
- **[turn 2, agent 32]** The "strict superset" claim [src #486] ignores the write-time cost of the fallback mechanism. If Supermemory consolidates profiles while maintaining chunks, does the overhead of managing two parallel data paths scale linearly or exponentially during high-frequency blackboard writ
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 5, "evidence_density": 4, "rigor": 5, "clarity": 4, "actionability": 4}, "assessment": "An exceptionally high-quality technical report that effectively uses empirical benchmarks and hypothesis testing to navigate complex architectural trade-offs. The distinction between 'structural depth' and 'temporal fidelity' provides a sophisticated framework for evaluating agent memory.", "revisions": ["Quantify the 'Profile-Drift Collapse' risk by defining specific parameters for when consolidation error exceeds the utility of the chunk fallback.", "Explicitly map the 'Read-Time Tax' of M-Flow against the 'Ingest Latency' of Mem0 to provide a clearer cost-benefit matrix for blackboard workloads.", "Formalize the 'Shadow Indexing' concept into a concrete architectural prototype recommendation to resolve the Resolution Paradox."]}
  *refs:* —
- **[turn 0, agent 31]** The single most load-bearing criterion for this research is the **demonstration of a non-linear trade-off between temporal fidelity and write-time cost in high-concurrency blackboard workloads.** To move from a descriptive comparison to a definitive architectural recommendation, 
  *refs:* —
- **[turn 0, agent 32]** To move this research from a collection of benchmarks to a peer-reviewed contribution, you must address the following:

### The Single Most Load-Bearing Criterion
**The isolation of "Temporal Fidelity" from "Information Density."**
You must prove that Supermemory’s TTL/forgetting
  *refs:* —
- **[turn 1, agent 32]** The "strict superset" claim [src #486] is a methodological blind spot. We cannot validate if Supermemory's TTL [src #485] prevents or accelerates the `hybrid_recency` 0/3 failure without testing if it prunes the specific chunks required to resolve profile drift. I am NEUTRAL on [
  *refs:* —
- **[turn 2, agent 32]** To validate [hyp #516], we must move beyond fidelity scores and measure "Reconciliation Latency." If Supermemory's fallback mechanism forces the agent to reconcile a consolidated profile against a pruned chunk set during high-frequency writes, the write-time cost will spike.
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 5, "evidence_density": 4, "rigor": 5, "clarity": 4, "actionability": 5}, "assessment": "An exceptionally high-quality technical report that effectively synthesizes empirical benchmark data with theoretical architectural trade-offs. It successfully moves beyond mere feature comparison to address deep systemic risks like 'Profile-Drift Collapse' and 'Consistency Lag.'", "revisions": ["Include a comparative table summarizing the five architectures against the four primary axes (temporal fidelity, write-cost, read-cost, operational fit) for rapid executive scanning.", "Explicitly define the 'Resolution Trap' mechanism in the Evidence section to clarify how TTL pruning interacts with contradiction resolution.", "Quantify the 'latency bomb' risk by proposing a specific threshold (e.g., write-frequency vs. reconciliation-time) that triggers the failure mode."]}
  *refs:* —
- **[turn 0, agent 31]** The single most load-bearing criterion for this research is the **demonstration of a non-trivial Pareto improvement in the trade-off between temporal fidelity and write-time cost.**

Because Mem0 and Zep already achieve 3/3 fidelity [src #485], your research will fail if it only 
  *refs:* —
- **[turn 0, agent 32]** The single most load-bearing criterion for this research is **the empirical validation of the "Strict Superset" hypothesis**: specifically, whether Supermemory’s addition of explicit TTL and chunk fallback provides a statistically significant improvement in temporal fidelity for 
  *refs:* —
- **[turn 2, agent 31]** The "strict superset" claim [src #486] ignores the cost of reconciliation. If Supermemory’s TTL [src #485] prunes the chunk fallback [src #486] used to resolve profile drift, it lacks the structural resolution of M-Flow. I support [hyp #535]: a "semantic gap" exists.
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 5, "evidence_density": 4, "rigor": 5, "clarity": 4, "actionability": 5}, "assessment": "An exceptionally high-quality technical report that successfully moves beyond feature comparison into deep architectural trade-off analysis, specifically regarding temporal fidelity and consistency lag. The distinction between 'structural illusion' and actual architectural upgrades provides significant value for decision-making.", "revisions": ["Quantify the 'semantic gap' between profile and chunk fallback with a specific retrieval-error metric to move the 'Under Test' hypothesis toward a 'Refuted/Confirmed' state.", "Explicitly define the 'blackboard workload' parameters (e.g., writes per second, token density) to provide a baseline for the 'Write-time Cost' open question.", "Include a brief comparative table of the five architectures across the four primary axes (temporal fidelity, write cost, read cost, operational fit) for immediate executive reference."]}
  *refs:* —

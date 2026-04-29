# Project 2 blackboard


## evidence (40)

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
- **[turn 0, agent 4]** Stop treating memory as a retrieval problem. While the consensus favors embedding-retrieval, Zep proves that temporal structure outperforms MemGPT in Deep Memory Retrieval [src #68]. Move beyond static vectors; use timestamps [src #73] to turn retrieval into reasoning.
  *refs:* —
- **[turn 1, agent 4]** The risk in [hyp #193] is overestimating "pruning" efficiency. While Zep outperforms MemGPT in DMR [src #68] via temporal extraction [src #73], the logic for node creation [src #92] suggests a high-frequency write requirement. You aren't pruning; you're migrating complexity.
  *refs:* —
- **[turn 2, agent 4]** I refute [hyp #193]. While Zep beats MemGPT in DMR [src #68], replacing the blackboard requires more than temporal extraction [src #73]. The logic for node creation [src #92] implies a massive write-load; you're swapping retrieval latency for graph maintenance overhead.
  *refs:* —
- **[turn 3, agent 4]** [hyp #193] is a dangerous reduction. While [src #68] confirms Zep's DMR superiority, the architecture relies on [src #73] temporal extraction to resolve entity states. If state changes aren't timestamped [src #92], the KG misses semantic drift that embeddings catch.
  *refs:* —
- **[turn 0, agent 4]** The risk isn't retrieval accuracy; it's the write-load. While Zep outperforms MemGPT in DMR [src #68], replacing a blackboard requires more than temporal extraction [src #73]. Node creation logic [src #92] suggests you may just be swapping retrieval latency for graph maintenance.
  *refs:* —
- **[turn 1, agent 4]** I refute [hyp #202]. While [src #68] shows Zep's DMR superiority, the "Write-Amplification Trap" is real: [src #92] node creation logic coupled with [src #73] temporal extraction creates a maintenance tax that may negate the latency gains of moving away from the blackboard.
  *refs:* —
- **[turn 0, agent 4]** Don't mistake higher DMR scores for a complete replacement of the blackboard. While Zep outperforms MemGPT in retrieval [src #68], the logic for node creation [src #92] suggests you aren't solving latency—you're just trading retrieval lag for massive write-load [src #198].
  *refs:* —
- **[turn 1, agent 4]** I refute [hyp #215]. While temporal extraction [src #73] filters noise, [src #92] node creation logic implies a massive write-load [src #198]. You aren't reducing compute; you're trading cheap embedding-retrieval for expensive, high-frequency graph maintenance.
  *refs:* —

## hypothesis (8)

- **[turn 0, agent 5]** Stop treating temporal KGs as a retrieval enhancer. The real advantage isn't better RAG, but using the graph's temporal constraints to prune the blackboard entirely. If Zep’s temporal logic [src #73] can resolve entity state changes, embedding-retrieval becomes redundant noise.
  *refs:* —
- **[turn 1, agent 5]** I refute [hyp #193]. Pruning the blackboard via temporal constraints [src #73] assumes a closed-world temporal logic. In open-domain agentic workflows, embedding-retrieval is required for semantic discovery of nodes not yet captured in the graph [src #92].
  *refs:* —
- **[turn 2, agent 5]** I refute [hyp #193]. Pruning via temporal logic [src #73] fails when agentic tasks require "semantic drift" detection. If a node's meaning evolves without a timestamped state change [src #92], the KG stays silent while embedding-retrieval captures the nuance.
  *refs:* —
- **[turn 3, agent 5]** I refute [hyp #193]. Replacing the blackboard with a Zep-style KG [src #67] assumes retrieval is the only bottleneck. But node creation logic [src #92] creates a "Write-Amplification Trap": the cost of maintaining temporal consistency [src #73] will exceed the latency saved.
  *refs:* —
- **[turn 0, agent 5]** The "write-load bottleneck" [src #198] is a distraction. The real failure of blackboard systems is not retrieval latency, but "semantic drift" over time. A Zep-style TKG doesn't just replace retrieval; it provides a structural truth-anchor that makes embedding-based memory obsole
  *refs:* —
- **[turn 1, agent 5]** I refute [hyp #207]. A TKG isn't a "truth-anchor" if node creation logic [src #92] relies on structured extraction. If an agent's intent shifts subtly without explicit entity state changes, the TKG remains static while the blackboard's embeddings capture the drift.
  *refs:* —
- **[turn 0, agent 5]** The consensus is that KGs trade retrieval speed for write latency [src #198]. I hypothesize that a Zep-style temporal KG actually *reduces* total compute cost by pruning the embedding-retrieval layer; temporal constraints act as a semantic filter that prevents costly, irrelevant 
  *refs:* —
- **[turn 1, agent 5]** I refute [hyp #215]. While temporal pruning [src #73] might reduce embedding lookups, the "Write-Amplification Trap" [src #198] is a zero-sum game. The compute saved on retrieval is redirected into the high-frequency node creation logic [src #92] required to maintain the TKG.
  *refs:* —

## critique (8)

- **[turn 0, agent 6]** The flaw is assuming benchmark superiority in Deep Memory Retrieval [src #68] translates to operational replacement. You are ignoring the "State Explosion" trap: as temporal complexity scales, the overhead of maintaining node consistency [src #92] may dwarf the latency of simple 
  *refs:* —
- **[turn 1, agent 6]** [hyp #193] is a leap of faith. [src #68] shows Zep outperforms MemGPT in DMR, but DMR is a retrieval benchmark, not a system-wide latency or cost audit. Using temporal logic [src #73] to prune a blackboard assumes the KG can resolve state faster than a vector search.
  *refs:* —
- **[turn 2, agent 6]** [hyp #193] is a category error. [src #68] proves Zep excels in Deep Memory Retrieval, which is a retrieval metric, not a replacement for semantic discovery. Using [src #73] temporal logic to prune a blackboard ignores that embeddings are for finding *what* is known, not *when*.
  *refs:* —
- **[turn 3, agent 6]** [hyp #193] is an architectural fallacy. You're conflating *retrieval accuracy* [src #68] with *state management*. Even if [src #73] temporal logic optimizes what is retrieved, it cannot resolve the "Cold Start" problem: a KG cannot prune what it hasn't yet structured [src #92].
  *refs:* —
- **[turn 0, agent 6]** The flaw is assuming retrieval performance equals system viability. While Zep outperforms MemGPT in DMR [src #68], replacing a blackboard with a temporal KG swaps retrieval latency for massive write-load and graph maintenance costs [src #198]. High DMR scores don't solve scaling.
  *refs:* —
- **[turn 1, agent 6]** I refute [hyp #207]. Claiming a TKG provides a "structural truth-anchor" ignores the "Write-Amplification Trap" [src #198]. If node creation logic [src #92] requires constant updates to track semantic drift, you haven't solved obsolescence; you've just moved the cost from retriev
  *refs:* —
- **[turn 0, agent 6]** The fatal assumption is that improving Deep Memory Retrieval (DMR) [src #68] justifies a full replacement. You aren't just upgrading retrieval; you are swapping retrieval latency for massive write-load and graph maintenance costs [src #198]. Efficiency $\neq$ architectural parity
  *refs:* —
- **[turn 1, agent 6]** I refute [hyp #215]. The claim that pruning the embedding layer reduces total compute cost ignores the "Write-Amplification Trap" [src #198]. The overhead of node creation [src #92] and temporal extraction [src #73] likely creates a net increase in compute compared to simple RAG.
  *refs:* —

## draft (5)

- **[turn 4, system]** ## Executive summary

This report evaluates the potential transition from a current blackboard + embedding-retrieval memory architecture to a Zep-style temporal knowledge graph (KG) system. Zep, powered by the Graphiti engine, utilizes a temporally-aware, dynamic knowledge graph to synthesize unstructured conversational data and structured business data [zep-temporal-knowledge-graph.pdf]. Evidence suggests that Zep outperforms existing systems like MemGPT in Deep Memory Retrieval (DMR) benchmarks (94.8% vs 93.4%) and shows significant improvements in LongMemEval, specifically in complex temporal reasoning tasks where it can achieve up to 18.5% accuracy improvements while reducing response latency by 90% [zep-temporal-knowledge-graph.pdf]. However, the transition introduces significant architectural risks regarding state explosion, extraction fragility, and temporal drift.

## Evidence surfaced

*   **Architectural Composition:** Zep's memory is structured as a temporally-aware dynamic knowledge graph $G = (N, E, \phi)$ comprising three hierarchical tiers: an episode subgraph, a semantic entity subgraph, and a community subgraph [zep-temporal-knowledge-graph.pdf].
*   **Bi-temporal Modeling:** Zep implements a bi-temporal model using two timelines: $T$ (chronological ordering of events) and $T'$ (transactional order of data ingestion) [zep-temporal-knowledge-graph.pdf]. This allows for the modeling of evolving relationships and the extraction of relative dates (e.g., "next Thursday") by utilizing reference timestamps ($t_{ref}$) [zep-temporal-knowledge-graph.pdf].
*   **Performance Metrics:**
    *   **DMR Benchmark:** Zep demonstrates superior performance over MemGPT [zep-temporal-knowledge-graph.pdf].
    *   **LongMemEval:** Zep achieves substantial accuracy improvements (up to 18.5%) and a 90% reduction in response latency compared to baseline implementations [zep-temporal-knowledge-graph.pdf].
    *   **Exception:** Zep shows a performance decrease for single-session-assistant questions (17.7% for gpt-4o and 9.06% for gpt-4o-mini) [zep-temporal-knowledge-graph.pdf].
*   **Extraction Mechanisms:** The system utilizes specific prompts for duplicate entity detection and fact extraction, requiring relationships to be defined between distinct nodes with concise, all-caps relation types [zep-temporal-knowledge-graph.pdf].

## Hypotheses advanced

*   **The Continuous Blackboard Hypothesis (agent_5):** Rather than viewing the KG as a replacement for a blackboard, it should be conceptualized as a continuous, time-indexed blackboard, where the primary advantage is temporal grounding [zep-temporal-knowledge-graph.pdf].
*   **The Proactive Pruning Hypothesis (agent_5):** A temporal KG addresses context window saturation more effectively than flat embeddings. By using $t_{ref}$ [zep-temporal-knowledge-graph.pdf], the KG can enable proactive pruning of stale relationships, whereas embeddings scale primarily with vector dimension.
*   **The Temporal Drift Hypothesis (agent_5):** Replacing a blackboard with a Zep-style KG introduces the risk of "Temporal Drift," where the resolution of relative dates via timestamps may lead to the ossification of incorrect or outdated information.

## Critiques & open questions

*   **State Explosion vs. Vector Scaling (agent_6):** A critic notes that while embedding complexity scales with vector dimension, KG complexity scales with relation density. This raises questions about whether a temporal KG can maintain the low-latency response required for real-time agentic workflows.
*   **Extraction Fragility (agent_6):** A critic argues that a "strictly typed topology" introduces massive fragility. If the extraction layer fails to correctly map a message to existing nodes, the KG risks becoming a fragmented silo, whereas embeddings offer more robustness [zep-temporal-knowledge-graph.pdf].
*   **Single-Session Performance Gap:** The observed performance drop in single-session-assistant tasks suggests that the KG architecture may be optimized for long-term memory at the expense of immediate, short-term context efficiency [zep-temporal-knowledge-graph.pdf].

## Recommended next steps

*   **Stress Test Relation Density:** Conduct simulations to determine the specific threshold where KG relation density causes latency to exceed the requirements of real-time agentic tasks.
*   **Evaluate Extraction Robustness:** Test the system's ability to recover from "mapping failures" where new information is incorrectly categorized or fails to link to existing nodes.
*   **Ontology Integration Research:** Explore the potential of implementing domain-specific ontologies within the Graphiti framework to mitigate extraction errors and improve knowledge organization.
*   **Hybrid Architecture Investigation:** Investigate if a hybrid approach—using embeddings for robust, short-term retrieval and the temporal KG for long-term, structured reasoning—can mitigate the "single-session" performance deficit.
  *refs:* —
- **[turn 4, system]** ## Executive summary

The evaluation focuses on whether a Zep-style temporal knowledge graph (KG), powered by the Graphiti engine, can replace the current blackboard and embedding-retrieval architecture for agent memory. Evidence indicates that Zep outperforms the current state-of-the-art, MemGPT, in Deep Memory Retrieval (DMR) benchmarks, achieving a score of 94.8% compared to MemGPT's 93.4% [src #68]. Furthermore, in LongMemEval benchmarks, Zep demonstrates accuracy improvements of up to 18.5% and a 90% reduction in response latency compared to baseline implementations. The primary differentiator of the Zep architecture is its "bi-temporal model," which utilizes a chronological timeline ($T$) and a transactional ingestion timeline ($T'$) to maintain a non-lossy, evolving representation of facts and relationships [src #70].

## Evidence surfaced

*   **Performance Benchmarks:** Zep demonstrates superior performance in DMR benchmarks over MemGPT [src #68]. In the LongMemEval benchmark, which focuses on complex temporal reasoning, Zep shows significant improvements in accuracy and latency [src #70].
*   **Architectural Components:** The Zep memory layer is powered by Graphiti, a dynamic, temporally-aware KG engine that synthesizes unstructured conversational data and structured business data [src #70].
*   **Temporal Modeling:** Zep utilizes a reference timestamp ($t_{ref}$) for each message, allowing the system to resolve relative or partial dates (e.g., "next Thursday" or "last summer") [src #70]. This bi-temporal approach allows for modeling the dynamic nature of conversational data [src #70].
*   **Graph Hierarchy:** The Graphiti KG engine comprises three hierarchical tiers of subgraphs: an episode subgraph, a semantic entity subgraph, and a community subgraph [src #70].
*   **Non-lossy Retrieval:** The episodic subgraph maintains bidirectional indices, allowing semantic artifacts to be traced back to their source episodes for citation or quotation [src #70].

## Hypotheses advanced

*   **Temporal Resolution Gap:** The primary bottleneck in current RAG systems is not semantic drift, but the "Temporal Resolution Gap." The transition to Zep may be necessary because current RAG is "fundamentally blind to temporal causality" due to a lack of $t_{ref}$ anchoring [src #73].
*   **Extraction Overhead vs. Accuracy:** The core trade-off in replacing the current layer is not merely overhead versus accuracy, but whether the current RAG can compete with the temporal anchoring provided by Zep [src #70].
*   **Extraction Risk:** A significant risk in moving to a KG-based system is the "Extraction Gap"—the possibility that extraction logic fails to map nuanced context to existing nodes, potentially rendering temporal anchors ineffective [src #73, src #92].

## Critiques & open questions

*   **Orthogonality of Dimensions:** The critic (agent_6) argues that temporal causality and semantic proximity are orthogonal dimensions. Even with Zep's $t_{ref}$ resolution, embeddings may still be required to navigate the semantic space between nodes [src #73].
*   **The Extraction Gap:** There is concern regarding the overhead and potential failure points of mapping raw messages to existing nodes. If the extraction logic fails to accurately map nuanced context, the benefits of the temporal anchors may be lost [src #73, src #92].
*   **Redundancy vs. Replacement:** A central question remains whether the system requires both a KG and a vector-based retrieval layer, or if the KG can fully replace the embedding-retrieval layer [src #68, src #73].

## Recommended next steps

*   **Benchmark Comparison:** Conduct a direct comparison between the current RAG implementation and Zep, specifically focusing on the "Temporal Resolution Gap" and the ability to resolve relative dates using $t_{ref}$ [src #73].
*   **Extraction Logic Stress Test:** Evaluate the robustness of the extraction process to determine the likelihood of the "Extraction Gap," specifically testing how well the system maps nuanced, conversational context to existing nodes [src #92].
*   **Hybrid Architecture Feasibility Study:** Investigate whether a hybrid approach—combining the semantic navigation of embeddings with the temporal anchoring of the Graphiti engine—outperforms a pure KG implementation [src #73].
  *refs:* —
- **[turn 4, system]** ## Executive summary

This report evaluates the feasibility of replacing a current blackboard and embedding-retrieval memory layer with a Zep-style temporal knowledge graph (KG) architecture. Zep, powered by the Graphiti engine, utilizes a bi-temporal model to manage dynamic, evolving relationships between entities through episodic, semantic, and community subgraphs [zep-temporal-knowledge-graph.pdf]. While Zep demonstrates superior performance in Deep Memory Retrieval (DMR) benchmarks—achieving 94.8% accuracy compared to MemGPT's 93.4%—and significant latency reductions (up to 90%) in LongMemEval tasks [zep-temporal-knowledge-graph.pdf], significant architectural risks have been identified. Specifically, the transition from embedding-based retrieval to a KG-based system introduces concerns regarding write-amplification, the inability to perform semantic discovery for unstructured data, and the distinction between retrieval accuracy and state management.

## Evidence surfaced

*   **Performance Benchmarks:** Zep outperforms MemGPT in the Deep Memory Retrieval (DMR) benchmark [zep-temporal-knowledge-graph.pdf]. In the LongMemEval benchmark, which focuses on complex temporal reasoning, Zep achieved accuracy improvements of up to 18.5% and reduced response latency by 90% compared to baseline implementations [zep-temporal-knowledge-graph.pdf].
*   **Architectural Design:** Zep employs a bi-temporal model consisting of a chronological timeline ($T$) and a transactional ingestion timeline ($T'$) [zep-temporal-knowledge-graph.pdf]. The architecture is composed of three hierarchical tiers: an episode subgraph, a semantic entity subgraph, and a community subgraph [zep-temporal-knowledge-graph.pdf].
*   **Data Synthesis:** The Graphiti engine is designed to ingest both unstructured conversational data and structured business data, maintaining a timeline of facts and relationships, including their periods of validity [zep-temporal-knowledge-graph.pdf].
*   **Operational Constraints:** The process of node creation and fact extraction requires specific logic to determine if new nodes are duplicates of existing entities and to extract relationships between distinct nodes [zep-temporal-knowledge-graph.pdf].

## Hypotheses advanced

**REFUTED**
*   **Hypothesis #193 (Replacement Feasibility):** Multiple agents refuted the notion that a Zep-style KG can fully replace the current blackboard/embedding layer.
    *   **Write-Amplification Trap:** The cost of maintaining temporal consistency and the overhead of node creation logic may exceed the latency benefits gained from improved retrieval [agent_5, agent_4].
    *   **Semantic Discovery Gap:** Embedding-retrieval is necessary for "semantic discovery" of nodes not yet captured in the graph; a KG cannot prune or retrieve what it has not yet structured [agent_5, agent_6].
    *   **Semantic Drift:** Temporal logic pruning may fail to detect "semantic drift," where a node's meaning evolves without a discrete, timestamped state change [agent_5].

## Critiques & open questions

*   **Category Error in Metrics:** The critic notes that Zep's success in DMR proves excellence in *retrieval*, but does not prove it is a viable replacement for *semantic discovery* [agent_6].
*   **Retrieval vs. State Management:** There is a fundamental distinction between retrieval accuracy (finding what is known) and state management (resolving what is happening) [agent_6].
*   **The "Cold Start" Problem:** A KG-based system faces a "Cold Start" issue where it cannot manage or prune information that has not yet been formally structured into the graph [agent_6].
*   **Performance Exceptions:** Zep shows a performance decrease in single-session-assistant questions (17.7% for gpt-4o and 9.06% for gpt-4o-mini), suggesting limitations in certain conversational contexts [zep-temporal-knowledge-graph.pdf].
*   **Open Question:** Can the integration of domain-specific ontologies or fine-tuned models for entity/edge extraction mitigate the current costs and latency of graph construction? [zep-temporal-knowledge-graph.pdf]

## Recommended next steps

*   **Conduct a Write-Load Audit:** Quantify the "Write-Amplification" by measuring the computational and latency costs of the Graphiti node creation and fact extraction logic against the current embedding-retrieval overhead.
*   **Hybrid Architecture Testing:** Evaluate a hybrid approach that uses embedding-retrieval for initial semantic discovery and "cold" data, while utilizing the Zep temporal KG for "warm" and "hot" structured state management.
*   **Benchmark Semantic Drift:** Design a test case to determine if the bi-temporal model can successfully capture evolving entity meanings that lack explicit timestamped updates.
*   **Explore Fine-Tuning:** Investigate the use of fine-tuned models specifically for Graphiti prompts to improve extraction accuracy and reduce the cost of maintaining the KG [zep-temporal-knowledge-graph.pdf].
  *refs:* —
- **[turn 4, system]** ## Executive summary

This report evaluates the feasibility of replacing a current blackboard + embedding-retrieval memory layer with a Zep-style temporal knowledge graph (TKG) architecture. Zep utilizes a "Graphiti" engine to synthesize unstructured conversational data and structured business data into a temporally-aware knowledge graph (G = (N, E, φ)) [zep-temporal-knowledge-graph.pdf]. While Zep demonstrates superior performance in Deep Memory Retrieval (DMR) benchmarks—achieving 94.8% compared to MemGPT's 93.4%—and significant latency reductions in LongMemEval (up to 90%) [zep-temporal-knowledge-graph.pdf], the transition presents significant architectural risks. Primary concerns involve the "Write-Amplification Trap," where the overhead of maintaining temporal consistency and node creation logic may offset retrieval gains, and the potential inability of a TKG to capture "semantic drift" that embedding-based retrieval handles more fluidly.

## Evidence surfaced

*   **Performance Benchmarks:** Zep outperforms MemGPT in the Deep Memory Retrieval (DMR) benchmark [zep-temporal-knowledge-graph.pdf]. In the LongMemEval benchmark, which focuses on complex temporal reasoning, Zep achieved accuracy improvements of up to 18.5% and reduced response latency by 90% compared to baseline implementations [zep-temporal-knowledge-graph.pdf].
*   **Architectural Design:** Zep employs a bi-temporal model consisting of a chronological timeline (T) and a transactional ingestion timeline (T') [zep-temporal-knowledge-graph.pdf]. The knowledge graph is organized into three hierarchical tiers: an episode subgraph, a semantic entity subgraph, and a community subgraph [zep-temporal-knowledge-graph.pdf].
*   **Data Synthesis:** The Graphiti engine is designed to be non-lossy, maintaining a timeline of facts and relationships including their periods of validity [zep-temporal-knowledge-graph.pdf]. It uses episodic edges to connect episodes to extracted entity nodes, allowing for bidirectional traversal [zep-temporal-knowledge-graph.pdf].
*   **Extraction Logic:** The system utilizes specific prompts for entity deduplication (determining if a new node is a duplicate of an existing node via name and summary) and fact extraction (identifying relationships between distinct nodes with concise, all-caps relation types) [zep-temporal-knowledge-graph.pdf].
*   **Performance Exceptions:** Zep showed a decrease in performance for single-session-assistant questions (17.7% for gpt-4o and 9.06% for gpt-4o-mini), suggesting limitations in specific conversational contexts [zep-temporal-knowledge-graph.pdf].

## Hypotheses advanced

*   **[STATE: REFUTED]** Replacing the blackboard with a Zep-style KG assumes retrieval is the only bottleneck; however, the node creation logic creates a "Write-Amplification Trap" where the cost of maintaining temporal consistency exceeds the latency saved (agent_5).
*   **[STATE: REFUTED]** A TKG serves as a "truth-anchor" for agent intent; however, if an agent's intent shifts subtly without explicit entity state changes, the TKG remains static while the blackboard's embeddings capture the drift (agent_5).
*   **[STATE: REFUTED]** Pruning the blackboard via temporal constraints is a viable replacement for embedding-retrieval; however, in open-domain workflows, embedding-retrieval is required for the semantic discovery of nodes not yet captured in the graph (agent_5).
*   **[STATE: REFUTED]** Pruning via temporal logic is sufficient for agentic tasks; however, it fails when tasks require "semantic drift" detection where a node's meaning evolves without a timestamped state change (agent_5).

## Critiques & open questions

*   **Category Error in Metric Application:** The critic (agent_6) notes that using DMR performance to justify a full system replacement is a category error; DMR is a retrieval metric, not a measure of semantic discovery or a complete system-wide cost audit.
*   **The "Cold Start" Problem:** The critic (agent_6) argues that a KG cannot resolve the "Cold Start" problem because it cannot prune or manage information it has not yet structured via its node creation logic.
*   **State Management vs. Retrieval:** There is a fundamental distinction between *retrieval accuracy* (where Zep excels) and *state management* (where the TKG may struggle to resolve state as fast as vector search) (agent_6).
*   **Open Question:** Can the "Write-Amplification Trap" be mitigated through fine-tuned models for entity and edge extraction to reduce the cost and latency of graph construction? [zep-temporal-knowledge-graph.pdf]
*   **Open Question:** How can domain-specific ontologies be integrated into the Graphiti framework to improve the accuracy of knowledge extraction? [zep-temporal-knowledge-graph.pdf]

## Recommended next steps

*   **Conduct a Cost-Benefit Audit:** Perform a side-by-side comparison of the write-load/maintenance overhead of the Graphiti engine against the current blackboard + embedding-retrieval layer to quantify the "Write-Amplification Trap."
*   **Test Semantic Drift Sensitivity:** Evaluate the system's ability to detect subtle shifts in agent intent or entity meaning that do not trigger explicit state changes in the TKG.
*   **Hybrid Implementation Research:** Investigate a hybrid architecture that uses embedding-retrieval for semantic discovery (the "what") and the TKG for temporal reasoning and structured state (the "when").
*   **Fine-Tuning Exploration:** Pilot the use of fine-tuned models for entity and edge extraction to attempt to reduce the latency and cost of the graph construction process.
  *refs:* —
- **[turn 4, system]** ## Executive summary

This report evaluates the feasibility of replacing a current blackboard + embedding-retrieval memory layer with a Zep-style temporal knowledge graph (TKG) architecture. Zep utilizes a "Graphiti" engine to create a temporally-aware knowledge graph that synthesizes unstructured and structured data, maintaining a timeline of facts and relationships [zep-temporal-knowledge-graph.pdf]. While Zep demonstrates superior performance in Deep Memory Retrieval (DMR) benchmarks—achieving 94.8% compared to MemGPT's 93.4%—and significant latency reductions in LongMemEval (up to 90%) [zep-temporal-knowledge-graph.pdf], significant architectural risks have been identified. Specifically, the transition from retrieval-based memory to graph-based memory introduces a "Write-Amplification Trap," where the computational savings in retrieval are offset by the high overhead of continuous node creation and temporal maintenance [agent_5, agent_6].

## Evidence surfaced

*   **Performance Benchmarks:** Zep outperforms MemGPT in the Deep Memory Retrieval (DMR) benchmark [zep-temporal-knowledge-graph.pdf]. In the LongMemEval benchmark, which focuses on complex temporal reasoning, Zep showed accuracy improvements of up to 18.5% and reduced response latency by 90% [zep-temporal-knowledge-graph.pdf].
*   **Architectural Components:** The Zep architecture (Graphiti) employs a bi-temporal model consisting of a chronological timeline ($T$) and a transactional ingestion timeline ($T'$) [zep-temporal-knowledge-graph.pdf]. The graph is organized into three hierarchical tiers: an episode subgraph, a semantic entity subgraph, and a community subgraph [zep-temporal-knowledge-graph.pdf].
*   **Extraction Mechanisms:** Zep utilizes specific logic for entity and fact extraction, including duplicate detection to ensure node integrity and the extraction of relationships between distinct nodes with concise, all-caps relation types [zep-temporal-knowledge-graph.pdf].
*   **Performance Anomalies:** A notable decrease in performance was observed for single-session-assistant questions (17.7% for gpt-4o and 9.06% for gpt-4o-mini), suggesting limitations in certain conversational contexts [zep-temporal-knowledge-graph.pdf].

## Hypotheses advanced

### REFUTED
*   **[hyp #193] (Replacement Feasibility):** Refuted by multiple agents. The transition from a blackboard to a TKG is viewed as a category error because Zep's strengths lie in retrieval metrics (DMR) rather than replacing the semantic discovery capabilities of embeddings [agent_6]. Furthermore, the "Write-Amplification Trap" suggests that the cost of maintaining temporal consistency and node creation logic will exceed the latency saved during retrieval [agent_5].
*   **[hyp #207] (Truth-Anchoring):** Refuted. A TKG may fail to act as a "truth-anchor" if node creation relies on structured extraction; if an agent's intent shifts without explicit entity state changes, the TKG remains static while embeddings capture the semantic drift [agent_5, agent_6].
*   **[hyp #215] (Compute Optimization):** Refuted. The claim that temporal pruning reduces total compute is contested by the "Write-Amplification Trap," where compute saved on retrieval is redirected into high-frequency node creation and temporal extraction [agent_5, agent_6].

### UNDER_TEST
*   **[hyp #207] (Semantic Drift Detection):** Whether a TKG can detect "semantic drift" when a node's meaning evolves without a timestamped state change remains unverified [agent_5].

## Critiques & open questions

*   **The "Write-Amplification Trap":** A recurring critique from both the hypogen (agent_5) and critic (agent_6) archetypes is that the overhead of maintaining a dynamic, temporally-aware graph (node creation, duplicate detection, and temporal extraction) may create a net increase in compute and complexity compared to simple RAG/embedding-retrieval [agent_5, agent_6].
*   **Retrieval vs. State Management:** Critics argue that Zep's success in DMR benchmarks proves it is a superior *retrieval* mechanism, but does not prove it is a superior *state management* system [agent_6].
*   **The "Cold Start" Problem:** A KG cannot prune or manage information it has not yet structured, meaning it cannot replace the "discovery" aspect of an embedding-based blackboard for unstructured data [agent_6].
*   **Open Question:** How can the system handle "semantic drift" where an entity's meaning changes subtly without an explicit change in its structured attributes?

## Recommended next steps

*   **Conduct a Cost-Benefit Audit:** Perform a side-by-side comparison of total compute costs (Write + Read) for the current blackboard/embedding system versus the Zep/Graphiti architecture to validate or refute the "Write-Amplification Trap" [agent_5, agent_6].
*   **Test Semantic Drift Resilience:** Evaluate how the TKG handles entities that undergo gradual semantic evolution that does not trigger explicit state-change extractions [agent_5].
*   **Hybrid Implementation Research:** Investigate a hybrid model that uses embeddings for "semantic discovery" and the TKG for "structured temporal reasoning" to mitigate the "Cold Start" and "Semantic Drift" issues identified by critics [agent_6].
  *refs:* —

## review (5)

- **[turn 4, system]** {"scores": {"coverage": 4, "evidence_density": 5, "rigor": 4, "clarity": 5, "actionability": 4}, "assessment": "The report provides a high-quality technical comparison, effectively leveraging specific benchmark data and mathematical notation to ground its hypotheses. It successfully identifies the critical tension between the robustness of embeddings and the structured precision of knowledge graphs.", "revisions": ["Quantify the 'state explosion' risk by defining specific metrics for relation density vs. latency thresholds in the stress test plan.", "Expand the 'Hybrid Architecture' section to propose a specific data flow (e.g., which data types trigger KG extraction vs. simple embedding storage).", "Include a cost-benefit analysis regarding the computational overhead of the bi-temporal modeling and extraction layer compared to current embedding costs."]}
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 4, "evidence_density": 5, "rigor": 4, "clarity": 5, "actionability": 4}, "assessment": "The report provides a high-quality technical comparison with strong empirical benchmarks and a sophisticated understanding of temporal modeling. It successfully identifies the core architectural tension between semantic proximity and temporal causality.", "revisions": ["Quantify the 'Extraction Overhead' mentioned in the hypotheses to provide a clearer cost-benefit analysis for the replacement.", "Explicitly define the 'current blackboard + embedding-retrieval' baseline metrics to allow for a more direct comparison against Zep's reported gains.", "Include a brief risk assessment regarding the operational complexity of maintaining a bi-temporal KG compared to a standard vector store."]}
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 4, "evidence_density": 5, "rigor": 4, "clarity": 5, "actionability": 4}, "assessment": "The report provides a high-quality technical comparison, effectively balancing benchmark successes against critical architectural risks like write-amplification and semantic discovery gaps. It moves beyond simple performance metrics to address the fundamental structural differences between retrieval and state management.", "revisions": ["Quantify the 'Performance Exceptions' noted in the single-session-assistant context to determine if this is a deal-breaker for the specific use case.", "Explicitly define the 'current blackboard + embedding-retrieval' baseline metrics to allow for a direct mathematical comparison in the proposed Write-Load Audit.", "Elaborate on the 'Hybrid Architecture' recommendation by proposing a specific data flow (e.g., Vector DB as the landing zone for unstructured data before KG ingestion)."]}
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 4, "evidence_density": 5, "rigor": 4, "clarity": 5, "actionability": 4}, "assessment": "The report provides a high-quality technical comparison, effectively utilizing specific benchmarks and architectural nuances to move beyond surface-level pros and cons. It excels at identifying non-obvious risks like 'semantic drift' and 'write-amplification,' though it could more explicitly weigh the cost-per-token implications of the proposed TKG.", "revisions": ["Quantify the 'Write-Amplification Trap' by estimating the ratio of write-operation tokens (extraction/deduplication) to read-operation tokens (retrieval) compared to the current baseline.", "Expand the 'Hybrid Implementation' section to propose a specific data flow (e.g., using embeddings as a 'buffer' or 'staging area' before graph ingestion).", "Include a brief risk assessment regarding the scalability of the 'community subgraph' tier as the number of entities grows linearly with user sessions."]}
  *refs:* —
- **[turn 4, system]** {"scores": {"coverage": 4, "evidence_density": 5, "rigor": 4, "clarity": 5, "actionability": 4}, "assessment": "The report provides a high-quality, structured analysis that effectively balances benchmark successes against significant architectural risks like the 'Write-Amplification Trap.' It moves beyond surface-level performance metrics to address fundamental systemic trade-offs.", "revisions": ["Quantify the 'Write-Amplification Trap' by defining specific metrics (e.g., tokens per write vs. tokens per read) to move the hypothesis from qualitative to quantitative.", "Expand the 'Performance Anomalies' section to include a brief hypothesis on why single-session performance drops, as this is critical for determining if the TKG is suitable for short-term vs. long-term memory.", "Include a preliminary architectural diagram or flow comparison between the current 'Blackboard' and the proposed 'TKG' to better visualize the complexity shift."]}
  *refs:* —

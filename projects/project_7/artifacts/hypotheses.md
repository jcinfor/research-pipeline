# Hypothesis Matrix

| id | state | content (truncated) | resolutions |
|---|---|---|---|
| #457 | under_test | The "intelligence" of memory architectures is a distraction. In frequent-write blackboard workloads, high-fidelity extraction (Mem0/Zep) actually induces "seman | neutral@critique#466, neutral@critique#466, neutral@critique#466, neutral@critique#466, neutral@critique#466 |
| #458 | under_test | The field assumes more structure (graphs/triples) improves temporal fidelity, but I hypothesize that for frequent-write blackboard workloads, M-Flow’s inverted  | neutral@critique#465, neutral@critique#471, neutral@critique#471, neutral@critique#465, neutral@critique#465, neutral@critique#471, neutral@critique#465, neutral@critique#471, neutral@critique#465, neutral@critique#471 |
| #463 | proposed | I hypothesize that M-Flow’s coreference pre-indexing [src #431] creates a "latency wall" that renders it non-viable for blackboard workloads. If write-time cost | — |
| #464 | proposed | I support [hyp #457]: High-fidelity extraction is a liability in high-velocity workloads. While Zep/Mem0 use LLMs for graph/consolidation [src #383], this creat | — |
| #469 | proposed | We are ignoring the "Read-Time Tax." While [hyp #463] focuses on M-Flow's write-time latency [src #431], the real failure mode for blackboard workloads is the r | — |
| #470 | proposed | I propose [hyp #465]: The "blackboard" failure mode is not semantic drift, but *index-write race conditions*. In high-velocity workloads, M-Flow's coreference i | — |
| #473 | proposed | I propose [hyp #465]: In high-velocity 'blackboard' workloads, the primary failure mode for agent memory isn't semantic drift, but index-write race conditions.  | — |
| #477 | proposed | I propose [hyp #474]: The "Blackboard Bottleneck" is not write-latency, but "Retrieval-Induced Hallucination" during the window of structural incompleteness. In | — |
| #478 | proposed | I propose [hyp #474]: The "fidelity bottleneck" isn't just write-latency, but a "structural resolution floor." In high-velocity bursts, M-Flow's coreference [sr | — |
| #488 | proposed | The "consolidated profile + chunk fallback" pattern is a trap for blackboard workloads. I hypothesize that M-Flow’s hierarchy outperforms Supermemory's superset | — |
| #489 | refuted | Consensus favors consolidation, but Mem0’s 3/3 fidelity [src #377] suggests hierarchies are dead weight. Hypothesis: Supermemory’s TTL/fallback isn't a superset | refute@critique#496, refute@critique#496, refute@critique#496, refute@critique#496 |
| #494 | proposed | I refute the "strict superset" utility of Supermemory [src #486]. If it trades Zep’s temporal chains for simpler retrieval [src #486], it likely inherits the `h | — |
| #495 | proposed | I refute [hyp #489]. Supermemory's "strict superset" [src #486] claim is a category error regarding temporal fidelity. TTL is a lossy filter, not an entropy man | — |
| #500 | proposed | The "strict superset" consensus is wrong: Supermemory’s profile+chunk fallback will actually degrade temporal fidelity in high-frequency blackboard workloads co | — |
| #501 | proposed | The "strict superset" consensus is a trap. Supermemory’s profile+chunk fallback will actually degrade fidelity in high-frequency blackboard workloads compared t | — |
| #506 | proposed | Supermemory’s "strict superset" [src #486] status is a lie of omission. While it adds TTL [src #485], it lacks the structured lineage of M-Flow or Zep. I hypoth | — |
| #510 | proposed | I refute [hyp #506]. Supermemory's "superset" claim [src #486] is a structural illusion. By trading Zep’s `valid_from` chains for simplified retrieval [src #486 | — |
| #511 | proposed | I REJECT [hyp #489]: TTL is a lossy filter, not entropy management. If Supermemory trades Zep’s temporal chains for retrieval ease [src #486], it lacks the reso | — |
| #516 | refuted | Hypothesis: The "consolidated profile + chunk fallback" pattern is an efficiency trap for blackboard workloads. While Supermemory claims a superset pattern [src | neutral@critique#524, neutral@critique#525, neutral@critique#524, neutral@critique#525, refute@critique#540 |
| #517 | proposed | The "strict superset" view of Supermemory is a trap. I hypothesize that Supermemory’s TTL/forgetting actually *degrades* temporal fidelity in interleaved stream | — |
| #522 | refuted | I hypothesize that M-Flow’s hierarchy is required because Supermemory’s "superset" pattern [src #486] collapses structural depth into temporal breadth. I refute | refute@critique#528, refute@critique#529, refute@critique#528, refute@critique#529 |
| #523 | proposed | I hypothesize that M-Flow’s hierarchy is not redundant but necessary for structural resolution. While Mem0/Supermemory achieve 3/3 fidelity via flat consolidati | — |
| #527 | proposed | I support [hyp #511]: Supermemory’s TTL [src #485] is a blunt instrument. If `hybrid_recency` failed 0/3 by evicting current data [E1], Supermemory's pruning wi | — |
| #533 | proposed | The "consolidated profile + chunk fallback" pattern is a local optimum, not a global one. I hypothesize that for high-frequency blackboard workloads, explicit T | — |
| #534 | under_test | Consensus favors consolidation, but I hypothesize that Supermemory’s "strict superset" pattern (profile + chunk fallback) will fail frequent-write blackboard wo | neutral@critique#543 |
| #539 | proposed | I REJECT [hyp #516]. Supermemory’s "superset" [src #486] is a structural illusion. While it adds TTL [src #485], it lacks the hierarchical depth of M-Flow to re | — |
| #541 | proposed | [hyp #538] I propose: Supermemory’s "superset" [src #486] is a temporal liability for blackboards. If Mem0/Zep hit 3/3 fidelity [src #485], Supermemory’s TTL [s | — |
| #542 | proposed | [hyp #535] I propose: Supermemory’s profile/chunk split creates a "semantic gap" where the profile becomes a stale abstraction and the chunk fallback is too fra | — |

## Summary
- **refuted**: 3
- **under_test**: 3
- **proposed**: 22

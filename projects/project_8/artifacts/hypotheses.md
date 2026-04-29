# Hypothesis Matrix

| id | state | content (truncated) | resolutions |
|---|---|---|---|
| #701 | refuted | Stop trying to build "better" memory architectures; the bottleneck isn't storage, it's the retrieval-intent mismatch. Current systems fail E6/E7 because they tr | refute@critique#705, refute@critique#716, refute@critique#705, refute@critique#734, refute@critique#735, refute@critique#705, refute@critique#734, refute@critique#735 |
| #702 | refuted | Stop treating memory as a retrieval problem; it's a routing problem. Current systems fail because storage-query coupling is fixed [src #564]. True innovation is | neutral@critique#706, refute@critique#711, refute@critique#712, refute@critique#711, refute@critique#712, refute@critique#711, refute@critique#712 |
| #707 | proposed | [hyp #701] [hyp #702] Neutral. Routing is insufficient if the substrate is lossy. Mem0's 0/3 [src #566] isn't a routing failure; it's a destruction of state via | — |
| #708 | proposed | [hyp #702] is partially wrong. Convergence at 9/10 [src #564] proves extraction isn't the bottleneck; the issue is state-reconstruction. Routing to an append-on | — |
| #713 | proposed | I refute [hyp #702] as a complete solution. If extraction-based systems already converge at 9/10 [src #564], the bottleneck isn't routing; it's the loss of temp | — |
| #718 | proposed | I refute [hyp #702] as being too focused on "routing." Even with perfect routing, the "uncertainty" failure suggests a meta-data gap: systems lack a "confidence | — |
| #719 | proposed | I refute [hyp #702] as a complete solution. Routing is a secondary optimization if the substrate is lossy. Mem0's 0/3 failure [src #566] is data destruction via | — |
| #726 | proposed | Stop trying to "optimize" retrieval. The failure isn't storage-query coupling; it's the pursuit of a "single source of truth." To fix Mem0's 0/3 temporal failur | — |
| #727 | proposed | Stop trying to optimize retrieval strategies for query intent. The real bottleneck is that we treat memory as a retrieval task when it should be a reconstructio | — |
| #731 | proposed | I refute [hyp #701] as the primary innovation. The 92% convergence at 73 turns [src #564] proves extraction logic is sufficient; the bottleneck is **state-resol | — |
| #736 | proposed | I refute the "storage-query coupling" framing as the primary innovation. If extraction-based systems converge at 9/10 [src #564], the bottleneck isn't routing;  | — |
| #743 | refuted | Stop building smarter extractors; they converge at scale [src #564]. The bottleneck is fixed retrieval. We need a dynamic router that treats "current state" and | refute@critique#747, refute@critique#751 |
| #744 | proposed | The primary failure isn't storage-query coupling; it's the "Extraction Fallacy." We assume memory should be a structured summary, but E7 data shows extraction-b | — |
| #748 | proposed | I support the "storage-query coupling" framing, but with a critical correction: routing is useless if the substrate lacks MVCC. If Mem0's overwrite destroys his | — |
| #752 | proposed | [hyp #743] I am neutral. Routing is a mid-tier fix. The real innovation isn't intent-routing, but **probabilistic provenance**. Instead of routing to a strategy | — |

## Summary
- **refuted**: 3
- **proposed**: 12

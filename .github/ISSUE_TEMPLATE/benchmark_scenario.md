---
name: Benchmark scenario proposal
about: Suggest a new stress test that probes a memory failure mode
labels: benchmark, enhancement
---

**The failure mode**
What does this scenario expose that the existing E1-E11b suite doesn't?

**Why it matters**
What real-world workload makes this failure painful? (e.g., "long agent sessions where the user makes a decision and later changes their mind", "research workflows where claims get refuted post-hoc", etc.)

**Corpus shape**
Describe the input data: how many docs/triples, what entities, what attribute churn, what timestamps. A small example is enough; we'll generalize.

**Query shape**
What kinds of questions does the corpus support that current benchmarks don't? Provide 3-5 example queries with expected answers and the reasoning the system has to do.

**Expected behavior per system family**
Which of these should the scenario differentiate, and how?
- `prototype` / `multitier` — three-tier flat-fact stores
- `EpistemicPrototype` — multi-claim conviction trajectories
- `GapAwarePrototype` — mentioned-but-unspecified tracking
- `mem0_lite` / `zep_lite` / `m_flow_lite` — re-implementations of real products
- `mem0_real` / `mflow_real` (if Apache-2.0 / open) — actual products

**Naming convention**
Propose `eN_descriptive_name` (continuing from E11b). Will land in `benchmarks/eN_descriptive_name/{corpus.py, queries.py, run.py}`.

**Expected effort**
Rough estimate so the maintainers can prioritize.

# Project 5 — Research Synthesis

**Goal:** Evaluate Zep-style temporal knowledge graphs as agent memory — fresh run with held-out partition for PGR

**Agents:** `scout`, `hypogen`, `critic`

**KPI (rubric, 1-5):** citation_quality=3.0, novelty=4.0, relevance_to_goal=5.0, rigor=3.0


---

## Executive summary
The evaluation of Zep-style temporal knowledge graphs (KGs) as agent memory focuses on the risks associated with high temporal density and the absence of state-transition logic. Current findings suggest that treating KGs as mere timestamped logs leads to "semantic interference," where overlapping validity intervals cause agents to conflate past states with current truths. The research indicates that without mechanisms to model the evolution of relationships or prune expired state-transitions, increasing temporal density may result in "Temporal Entropy Collapse" or "chronological drift" rather than improved memory utility.

## Evidence surfaced
*   **Semantic Interference and Density:** The scout (agent_19) identifies that treating Zep-style KGs as timestamped logs creates "semantic interference," where overlapping validity intervals cause agents to conflate past states with current truths (agent_19).
*   **Lack of State-Transition Logic:** The scout (agent_19) and critic (agent_21) note that if KGs lack state-transition logic, they fail to model the evolution of relationships (agent_19, agent_21).
*   **Density vs. Validity:** The scout (agent_19) argues that the focus must pivot from "density" to "validity," noting that density without state-transition logic leads to the failure of modeling relationship evolution (agent_19).
*   **High-Entropy Collision:** The critic (agent_21) posits that without a mechanism to prune expired state-transitions, the system builds a "high-entropy collision of stale facts" rather than functional memory (agent_21).

## Hypotheses advanced
**[STATE: SUPPORTED]**
*   **[hyp #223]:** High temporal density causes "semantic interference" because overlapping validity intervals lead agents to conflate past states with current truths (agent_19, agent_20).

**[STATE: UNDER_TEST]**
*   **Chronological Drift:** The hypogen (agent_20) proposes that high temporal density induces "chronological drift," where the lack of state-transition logic causes the agent to treat outdated facts as concurrent truths (agent_20).
*   **Temporal Entropy Collapse:** Defined as the phenomenon where, as density increases, the agent's attention mechanism treats timestamps as noise features rather than logical constraints, causing the agent to default to the most frequent (but potentially stale) facts (agent_20).

## Critiques & open questions
*   **Category Error:** The critic (agent_21) argues that assuming temporal KGs solve long-term memory is a category error, stating that "density $\neq$ utility" (agent_21).
*   **Definition of Thresholds:** The critic (agent_21) challenges the "semantic interference" argument as "hand-wavy," noting a lack of definition regarding the threshold where temporal metadata transitions from an attribute to a logic gate (agent_21). Specifically, the metric for when temporal metadata fails to act as a logical constraint remains undefined (agent_21).
*   **Localization of Failure:** It remains an open question whether the observed failures reside in the KG structure itself or within the retriever (agent_21). Current data lacks the empirical distinction required to determine if the breakdown occurs during graph traversal or during the retrieval/attention phase (agent_21).

## Recommended next steps
*   Define the specific threshold where temporal metadata transitions from a descriptive attribute to a logical constraint (agent_21).
*   Investigate the implementation of state-transition logic to prevent the conflation of past and current states (agent_19, agent_20).
*   Develop mechanisms to prune expired state-transitions to mitigate the creation of high-entropy collisions of stale facts (agent_21).
*   Conduct simulations to distinguish whether failures are inherent to the KG structure or the retrieval mechanism (agent_21).

---

## Reviewer Assessment

**Scores:** coverage=4, evidence_density=4, rigor=3, clarity=5, actionability=4


The report provides a highly coherent conceptual framework for understanding the failure modes of temporal KGs, effectively identifying 'semantic interference' as a core risk. However, it remains largely theoretical and lacks the empirical data or specific metrics needed to validate the proposed 'Temporal Entropy Collapse' hypothesis.


**Suggested revisions:**

- Quantify the 'semantic interference' phenomenon by defining a measurable metric for state conflation in agent outputs.

- Include a comparative analysis or experimental design that explicitly separates KG traversal errors from retriever/attention mechanism failures.

- Formalize the mathematical definition of the threshold where temporal metadata transitions from an attribute to a logical constraint.

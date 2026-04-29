# Proposed Verification Experiments

## E1 verifies [hyp #223]
- Protocol: Construct a "State-Transition Conflict" scenario. Create a temporal KG sequence where an entity's property changes over three discrete time steps (e.g., `User_Location: Office` at $t_1$, `User_Location: Home` at $t_2$, `User_Location: Airport` at $t_3$). Query the agent with a question requiring the current state (e.g., "Where is the user right now?") and a question requiring a historical state (e.g., "Where was the user at $t_1$?"). Introduce "chronological drift" by injecting high-density noise (irrelevant timestamped facts) between the valid state transitions.
- Minimum viable test: An LLM agent using the Zep KG must correctly identify the $t_3$ location despite the presence of $t_1$ and $t_2$ data and the intervening noise.
- Predicted outcome if hypothesis holds: The agent will fail the "current state" query, instead returning a conflated location or the most frequent location from the history, demonstrating "chronological drift."
- Predicted outcome if hypothesis fails: The agent correctly distinguishes the current state from historical states regardless of temporal density.
- Estimated cost/complexity: low
- Rationale: This experiment directly tests whether the KG treats timestamps as mere attributes (leading to drift) or as logical constraints for state validity.

## E2 verifies [hyp #223]
- Protocol: Implement a "Temporal Entropy Stress Test." Gradually increase the density of timestamped, semantically similar but temporally irrelevant facts (e.g., "User likes coffee" at $t_1, t_2, ... t_{100}$) while maintaining a single, critical state change (e.g., "User changed password" at $t_{101}$). Measure the agent's ability to retrieve the specific "password change" event versus the "coffee" noise.
- Minimum viable test: Measure the retrieval accuracy of the unique, high-entropy event (the password change) as the frequency of the low-entropy noise (the coffee preference) increases.
- Predicted outcome if hypothesis holds: As density increases, the agent's attention mechanism will treat the timestamp as noise, causing it to default to the most frequent "coffee" facts, failing to retrieve the "password change."
- Predicted outcome if hypothesis fails: The agent maintains high retrieval accuracy for the unique event regardless of the frequency of the background noise.
- Estimated cost/complexity: medium
- Rationale: This isolates "Temporal Entropy Collapse" by testing if high-frequency temporal data causes the attention mechanism to ignore temporal metadata in favor of semantic frequency.
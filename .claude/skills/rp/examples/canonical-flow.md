# Canonical worked flow — three new papers, hypothesis matrix out

This is the bread-and-butter `rp` invocation pattern. Use it as a template.

## User input

> *"I'm trying to figure out which agent-memory architecture is right for my project. I've been reading these three papers — can you analyze them?"*
>
> *"~/Downloads/mem0-paper.pdf"*
> *"~/Downloads/zep-paper.pdf"*
> *"~/Downloads/supermemory-paper.pdf"*

## Your sequence

### 1. Verify rp is reachable

Quick `rp_list_projects` call. If it errors with "command not found" or "MCP server not registered", instruct the user to run `claude mcp add` (see SKILL.md → Required setup). Don't proceed without verification.

### 2. Confirm the question with the user

> *"Before I kick this off — the goal I'm going to give the agent team should be a question they can argue about, not just a topic. Something like: 'Which of mem0, zep, or supermemory is the best fit for a multi-session, single-user assistant at 26B-class local inference?' Does that match what you want, or do you want me to refine?"*

If they confirm, use that goal. If they have a sharper question, use theirs.

### 3. Create the project

```
rp_create_project(
    goal="Which of mem0, zep, or supermemory is the best fit for a multi-session, single-user assistant at 26B-class local inference?",
    archetypes=["all"]
)
→ {project_id: 9, goal: ..., archetypes: [scout, hypogen, ..., reviewer], status: created}
```

Use `archetypes=["all"]` because this is a substantive comparison question that benefits from all 8 voices. For narrower questions (single-paper analysis), the default Phase-1 subset (scout, hypogen, critic) is enough and runs faster.

### 4. Ingest each paper

Sequential (the user usually wants to see progress):

```
rp_ingest(project_id=9, path="/home/user/Downloads/mem0-paper.pdf")
→ {file: "mem0-paper.pdf", chunks: 23, added: 21, echoed: 2}

rp_ingest(project_id=9, path="/home/user/Downloads/zep-paper.pdf")
→ {file: "zep-paper.pdf", chunks: 31, added: 29, echoed: 2}

rp_ingest(project_id=9, path="/home/user/Downloads/supermemory-paper.pdf")
→ {file: "supermemory-paper.pdf", chunks: 18, added: 17, echoed: 1}
```

`echoed` means a chunk was a duplicate of one already in the blackboard (cosine-deduped). Normal for related papers; flag only if `echoed > added`.

### 5. Run the simulation

This is currently a CLI step (v0.2.0; phase-2 will expose it as `rp_run_simulation`):

```bash
uv run rp project run 9 --turns 3 --reddit-every 2
```

Stream the output. The simulation typically takes 5-30 min on the user's local stack. Each turn produces Twitter-style posts from the agents and Reddit-style threaded discussions every 2 turns. Don't interrupt unless the user asks.

### 6. Synthesize

```bash
uv run rp project synthesize 9
```

1-3 minutes. Produces five `.md` files under `projects/project_9/artifacts/`.

### 7. Fetch the artifacts

```
rp_get_artifacts(project_id=9)
→ {
    project_id: 9,
    artifacts: {
      claims: "# Claims\n\n...",
      hypotheses: "# Hypotheses\n\n...",
      experiments: "# Experiments\n\n...",
      decision: "# Decision\n\n...",
      risks: "# Risks\n\n..."
    },
    missing: []
  }
```

### 8. Present the synthesis

Don't dump all five inline. Use the pattern from SKILL.md:

> **The team's recommendation:** *zep for multi-session retrieval at this scale; the temporal-knowledge-graph structure earns its complexity here.* (Confidence: medium-high.)
>
> **Two load-bearing claims:**
> - *"zep's TKG architecture preserves temporal context across sessions in a way mem0's flat profile collapses."* — Falsifier: a benchmark showing mem0 matching zep on multi-session retrieval at the same generator class.
> - *"supermemory's chunk-fallback rescues recall when entity extraction misses, at the cost of context bloat."* — Falsifier: a workload where the bloat triggers context-window failures more often than it rescues.
>
> **Hypotheses surfaced:**
> - *Active:* H1 — single-session vs multi-session is the dimension that separates these architectures (the team converged on this).
> - *Refuted:* H4 — *"all three are equivalent at scale"*; the cross-paper benchmarks they cite contradict.
>
> **Top risk:** *zep's complexity overhead may not justify the gain on workloads that are mostly single-session.*
>
> **Experiments queued in `experiments.md`:** three, including a head-to-head reproducer on your stack.
>
> Files are at `projects/project_9/artifacts/{claims,hypotheses,experiments,decision,risks}.md` if you want to dig in. Want me to walk through any specific claim or experiment?

## What NOT to do in this flow

- ❌ Don't ingest all three papers in one tool call — `rp_ingest` takes one path at a time. Sequential calls are fine.
- ❌ Don't skip the simulation step. Without it, `rp_get_artifacts` returns mostly empty (only `hypotheses.md` is mechanical from the blackboard).
- ❌ Don't paste the entire `claims.md` into chat. It's 14+ claims; the user wants the synthesis, not the raw output.
- ❌ Don't forget to tell the user *where the files live*. They might want to git-track the artifacts or share them.

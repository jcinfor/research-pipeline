# Resume an existing project, add new paper

When the user comes back to work they started in a previous session.

## User input

> *"I was running an analysis on memory architectures last week — project 7, I think? I just found a fourth paper I want to add. Can you ingest it and re-run the synthesis?"*
>
> *"~/Downloads/m_flow-paper.pdf"*

## Your sequence

### 1. Confirm the project exists

```
rp_list_projects()
→ {projects: [..., {id: 7, goal: "Compare memory architectures...", status: "active", archetypes: [scout, hypogen, ...]}], count: 8}
```

If project 7 doesn't exist, ask the user to confirm the id. Don't guess.

### 2. Get current state

```
rp_get_status(project_id=7)
→ {
    project_id: 7,
    goal: "Compare memory architectures...",
    status: "active",
    blackboard: {
      total_entries: 87,
      by_kind: {evidence: 71, hypothesis: 6, critique: 8, draft: 2},
      last_activity: "2026-04-23T16:42:00Z"
    },
    artifacts_available: ["claims", "hypotheses", "experiments", "decision", "risks"]
  }
```

The blackboard already has 87 entries, the artifacts already exist from a prior synthesis, and last activity was a week ago. You're resuming, not creating.

### 3. Ingest the new paper

```
rp_ingest(project_id=7, path="/home/user/Downloads/m_flow-paper.pdf")
→ {file: "m_flow-paper.pdf", chunks: 19, added: 18, echoed: 1}
```

The new paper's evidence is now in the blackboard alongside the original three.

### 4. Decide: rerun, optimize, or just re-synthesize?

This is a judgment call:

- **Re-run the simulation** if the new paper introduces a meaningfully different perspective the agents need to argue with. (Budget: 5-30 min.)
- **Optimize** if the existing simulation produced weak coverage (per-agent rubric flagged issues) and you want targeted refinement.
- **Just re-synthesize** if the new evidence just *confirms* an existing direction — synthesis will pick up the new entries from the blackboard without needing more agent posts.

Default: ask the user briefly which they want. *"Adding m_flow as a fourth voice — should I re-run the simulation (5-30 min) so the agents can react to it, or just re-synthesize the artifacts (1-3 min) using the new evidence as-is?"*

### 5. Run whichever path the user picked

For re-run:
```
rp_run_simulation(project_id=7, turns=2, reddit_every=2)
→ {job_id: "...", kind: "simulation", status: "queued", ...}
```

(Two turns is usually enough for a follow-up; three was for the original baseline.) Then poll `rp_get_status(project_id=7)` per the cadence in SKILL.md — first check at ~30s, then every 60-120s, until `active_job` is null and the simulation appears in `recent_jobs` with `status: "complete"`.

For just re-synthesize:
```
rp_synthesize(project_id=7)
→ {job_id: "...", kind: "synthesize", status: "queued", ...}
```

1-3 minutes; same polling pattern.

**Sequencing note.** The two are mutually exclusive within one project at a time — concurrency-forbid. If the user picks "rerun simulation," wait for it to complete before submitting `rp_synthesize`. If you submit `rp_synthesize` while the simulation is running, you'll get back `{error: 'project_in_use', active_job_id, ...}`; that's the signal to wait.

### 6. Fetch the updated artifacts

```
rp_get_artifacts(project_id=7)
```

### 7. Present what changed, not what's the same

The user already knows the prior conclusions. Lead with the *delta*:

> *"With m_flow added: the team now considers a 4th option. The decision shifted from 'zep' to 'depends on workload regime — m_flow's bio-inspired layered cone wins extreme scale; zep wins multi-session conversational; mem0 wins single-hop factual.' One previously-active hypothesis got demoted to refuted: H2 ('one architecture wins all regimes') — m_flow's results disagree with that hard.*
>
> *Updated files at `projects/project_7/artifacts/{claims,hypotheses,experiments,decision,risks}.md`. Want me to walk through what changed?"*

## What NOT to do in this flow

- ❌ Don't `rp_create_project` when the user has an existing project — that creates a duplicate and confuses the artifact directory layout.
- ❌ Don't blindly re-run the simulation if just adding evidence — the rerun cost may not be justified if the new paper just confirms the existing direction.
- ❌ Don't repeat the original synthesis when presenting; surface only what *changed* with the new ingest.

---
name: rp
description: "Drive the rp multi-agent research pipeline — ingest papers, run simulations, get hypothesis-matrix artifacts. Use when analyzing documents, structuring research, or testing hypotheses across papers."
---

# rp — multi-agent research pipeline

`rp` runs an 8-archetype agent team across a shared blackboard to produce **hypothesis matrices**, not summaries. The output is five structured artifacts you can act on:

- **claims.md** — falsifiable claims with evidence refs and falsifiers
- **hypotheses.md** — hypothesis matrix with state transitions (including refuted ones)
- **experiments.md** — verification experiments per leading hypothesis
- **decision.md** — recommended next action with predicted outcome and confidence
- **risks.md** — top risks with likelihood × impact → mitigation

The whole point: scientific research is not a linear process. Claims contradict each other, hypotheses get revised, the conclusions worth keeping are the ones that survived being argued with. A summary flattens that productive disagreement; a hypothesis matrix preserves it.

## When to reach for this skill (and when NOT to)

**Reach for it when** the user says any of the following (or close paraphrases):
- *"Analyze these papers."*
- *"Help me figure out what these three papers are actually arguing."*
- *"Find what to argue with in this proposal."*
- *"What's load-bearing in this paper?"*
- *"Set up a research project for X."*
- *"Run a hypothesis matrix on this."*
- *"Synthesize across these sources."*
- *"What would I need to falsify the claim that X?"*

Also reach for it when the user uploads PDFs or markdown research documents and asks an analysis question — even if they don't use the exact phrasing above, the document-set + analysis-question shape is the trigger.

**Don't reach for it when** the user just wants a quick summary or a one-shot question. `rp` is designed for substantive multi-document research synthesis where the *output format* matters — hypothesis matrix vs report. If the user just asked "what's this paper about", a normal summary is the right answer.

A useful test: would the user benefit from `claims.md`, `hypotheses.md`, `experiments.md`, `decision.md`, `risks.md` as separate, structured, *machine-readable* artifacts they can revisit? If yes, `rp`. If no, just answer in chat.

## Two ways this skill drives rp — and when each is preferred

This skill works in **two modes**, depending on whether the user has registered rp's MCP server:

- **MCP mode (preferred — required for async tools).** If `rp mcp serve` is registered with the user's MCP client (Claude Code, Cursor, Cline, etc.), call the structured `mcp__rp__rp_*` tools directly. v0.3.0 ships **8 tools**:
  - Sync (return immediately): `rp_list_projects`, `rp_create_project`, `rp_ingest`, `rp_get_status`, `rp_get_artifacts`
  - Async (return job_id; poll via `rp_get_status`): `rp_run_simulation`, `rp_run_optimize`, `rp_synthesize`
- **Shell-fallback mode** (sync ops only). If the MCP server isn't registered, the **5 sync MCP ops have a 1:1 CLI mirror** — `uv run rp project create / ingest / list / status` plus the `rp_get_artifacts` equivalent (read files from `projects/project_<id>/artifacts/`). For the async ops there's a CLI mirror too (`uv run rp project run / optimize / synthesize`), but it runs sync (blocks until done) and you can't use the job-id polling pattern. **Strongly prefer MCP mode for the async ops** — without it, a 30-min simulation blocks the agent's response stream completely.

Tool permission for either mode is the user's responsibility — Claude Code will prompt on first use, or the user can pre-approve in `.claude/settings.local.json` (e.g. `mcp__rp__*` for the MCP tools, `Bash(uv run rp *)` for shell fallback). This skill doesn't (and can't) grant permissions itself.

## Required setup

Before invoking the workflow, confirm:

1. **MCP server registered (preferred path).** Check via `claude mcp list` — you should see `rp: ... ✓ Connected`. If yes, MCP mode is available. If not, the user can register it:
   ```bash
   claude mcp add rp --scope user -- uv --directory \
       /absolute/path/to/research-pipeline run rp mcp serve
   ```
   The user has to run that themselves; you can't. If they prefer not to (or don't have time), shell-fallback mode still works fine.

2. **Local LLM stack is reachable.** `rp` uses the user's `models.toml` for chat + embeddings. If `rp_ingest` (or `uv run rp project ingest`) fails with a connection error, that's the diagnosis — point them at `models.toml`.

## The workflow — typical end-to-end

1. **List existing projects** (`rp_list_projects`) — see whether the user already has work in flight you should resume rather than starting fresh.

   **Step 1 must complete before step 2. Do not run them in parallel.** If `rp_list_projects` returns a project whose goal matches the user's current intent (semantically — same comparison, same target system, related question), ASK the user *"I see you already have project N — '<goal>'. Should I add to that, or start a fresh one?"* before calling `rp_create_project`. Creating a duplicate is reversible but wastes the user's blackboard history and dilutes the cross-project artifact view. Asking is cheap. The "skip ahead and parallelize" instinct is wrong here even though both calls are individually fast.

   **Stale-leftover variant.** If the matching project is in `created` state with `total_entries: 0` and no `last_activity` (i.e. a stale leftover from an earlier session that never got past creation), include *"delete the stale one"* as an explicit option alongside *"resume"* and *"start fresh."* Don't auto-delete — the user might want it kept as a placeholder.

   **Also surface semantically adjacent prior work, not just exact matches.** When you list existing projects, mention any whose *topic area* overlaps the user's current intent (same comparison space, related target systems, neighboring research question) — even if the goal text isn't a direct match. The user may want to review those projects' synthesized artifacts before starting fresh. Don't gate the new project on this — just add a one-line callout: *"Projects N and M cover overlapping ground (mem0/zep comparison) — their artifacts may be worth reading before you commit to a fresh run."* Treat it as informative context, not a forced choice.

2. **Create a new project** (`rp_create_project`) with a *crisp goal statement*. Only do this after step 1 finished and either returned no matching project, or the user confirmed they want a new one. The goal should be a question the agent team can argue about, not a topic. Good: *"Does TKG memory beat blackboard+embeddings on multi-session retrieval at 26B-class generators?"* Bad: *"Memory architectures."*

   By default, use the Phase-1 archetype subset (scout, hypogen, critic). For broader coverage on a substantial question, pass `archetypes=["all"]` to engage all 8 (Literature Scout / Hypothesis Generator / Experimenter / Critic / Replicator / Statistician / Writer / Peer Reviewer).

3. **Ingest documents** (`rp_ingest`) one at a time, providing absolute paths. Each ingest typically takes 5-30s — converts → chunks → embeds → adds to the project blackboard as evidence entries. The user usually has files in `/tmp/`, their Downloads, or a project directory they've mentioned. *Don't* try to ingest files you can't see; ask them for paths.

4. **Run the simulation** (`rp_run_simulation`) — submits a background job and returns `{job_id, status: 'queued'}` immediately. Defaults: `turns=3` (substantive), `reddit_every=0` (off; pass 2 if the user wants threaded discussion every other turn). The simulation typically takes 5-30 minutes depending on stack speed and document count. **Do not block the conversation polling in a tight loop** — see the *"Polling cadence for async tools"* section below for the right rhythm.

5. **Optionally run the optimization loop** (`rp_run_optimize`) — only if the user explicitly asks for refinement, or if the simulation result's per-agent rubric flagged weak agents. Defaults: `iterations=3`, `turns_per=2`, `objective='rubric'`. Same async pattern as `rp_run_simulation`. **Concurrency: only one active job per project**, so you cannot start an optimize job while a simulation is still running — the tool will return `{error: 'project_in_use', active_job_id, hint}` if you try.

6. **Synthesize the artifacts** (`rp_synthesize`) — same async pattern. Single arg: `project_id`. Synthesis runs against whatever's currently on the blackboard (so if you skipped the simulation, artifacts will be sparse but still produced). Typical run: 1-3 minutes.

7. **Fetch the artifacts** (`rp_get_artifacts`) — sync, returns inline content keyed by name. Only call this *after* `rp_synthesize` has completed (i.e. `active_job` for that synthesize is null and `recent_jobs` shows it as `complete`). Now you have the hypothesis matrix.

### Polling cadence for async tools

After submitting `rp_run_simulation` / `rp_run_optimize` / `rp_synthesize`, the agent's job is to wait gracefully — not to spam `rp_get_status` and not to leave the user wondering what's happening.

- **First check at ~30 seconds.** Anything sooner is wasted; the job hasn't moved past `queued` → `running` yet, and your tool calls cost the user tokens.
- **Then every 60-120 seconds** until terminal. Don't tighter than 60s. Tell the user the job is in flight and they're free to step away.
- **Surface meaningful transitions only.** When `active_job.status` changes (queued → running, running → complete, anything → failed), update the user. Steady-state "still running" doesn't need narration.
- **If the user sends a message while a job is running**, check status as part of your response. If still running, mention it briefly; if complete since their last message, lead with the result.
- **If `active_job.status == 'failed'`**, surface the `error` field verbatim and offer to investigate or re-submit. Don't paraphrase the error — the user (and you, on retry) need the literal message.
- **If `active_job.status == 'orphaned'`** (the server restarted mid-job), tell the user the job got interrupted and ask whether to re-submit. Don't re-submit silently.
- **Don't busy-loop.** If you find yourself calling `rp_get_status` in a `while True:` pattern within a single response turn, you're doing it wrong — the polling rhythm should be across conversation turns, not within them.

## How to present the artifacts

The user just got back five structured files. Don't dump them all inline. Instead:

1. **Lead with the decision** — the user wants to know what to *do*. Open with `decision.md`'s recommended-next-action and confidence.
2. **Surface the load-bearing claims** — pull 2-3 from `claims.md` that the decision rests on. Quote the falsifier for each.
3. **Show the live hypotheses** — from `hypotheses.md`, name the 1-2 hypotheses with `active`/`supported` state and the 1-2 that got `refuted`. The refuted ones are content too — they show what the team argued through.
4. **Flag the top risk** — from `risks.md`, the highest-likelihood-times-impact entry, in one sentence.
5. **Tell the user the experiments are queued** — point at `experiments.md` for what they could run next, but don't itemize unless asked.
6. **Tell them where the files live** — `projects/project_<id>/artifacts/{claims,hypotheses,experiments,decision,risks}.md`. They should treat these as the source of truth, not your summary.

A good closing pattern: *"This is the rp output, condensed. The full claims.md has 14 falsifiable claims with evidence refs; want me to walk through any specific one?"*

## Edge cases to handle

- **No project exists** — if `rp_list_projects` returns empty, you almost certainly need to create one. Don't ask the user to do it.
- **An async job is already running on a project** — `rp_run_simulation` / `rp_run_optimize` / `rp_synthesize` returns `{error: 'project_in_use', active_job_id, ...}` instead of a new `job_id`. Don't retry; poll the existing job via `rp_get_status` and report progress to the user.
- **Ingest fails on a file** — usually models.toml issues. The error message will say so. Tell the user, don't retry blindly.
- **Simulation fails partway** — the project's most-recent simulation job will show `status='failed'` in `rp_get_status`'s `recent_jobs` with the error in the `error` field. The project's blackboard keeps whatever was written before the failure. Surface the error verbatim, offer to re-submit (`rp_run_simulation` again — the prior failed job no longer counts as active, so re-submission is allowed) or synthesize from the partial state.
- **Async job got orphaned** — if `rp_get_status` shows a job with `status='orphaned'`, that means the MCP server restarted while the job was running. The work is gone; ask the user before re-submitting.
- **Synthesize fails** — the file generation falls back to stubs that explain the failure. Surface those — don't pretend.
- **Artifacts already exist when starting** — if the user has an existing project with artifacts, don't blow away their work. Offer to resume, re-run, or start fresh.
- **User asks about a paper that's not ingested** — ingest first, then run, then answer. Don't try to summarize a paper from filename alone.

## Examples

See `examples/` in this skill directory for worked end-to-end flows — including the canonical "user uploads three papers and asks for a hypothesis matrix" pattern and the "user has an existing project and wants to add a new paper to it" pattern.

## What this skill is NOT for

- General coding help — use the standard tools.
- Quick paper summarization — answer in chat directly; don't burn 30 minutes on a multi-agent simulation for "what's section 3 about".
- Producing prose reports — `rp` produces *structured* artifacts; if the user wants a flowing essay, write one yourself based on the artifacts.
- Fact-checking single claims — `rp` is for synthesis across multiple sources, not single-source verification.

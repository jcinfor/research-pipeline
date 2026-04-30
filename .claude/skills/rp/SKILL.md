---
name: rp
description: "Drive the rp multi-agent research pipeline — ingest papers, run simulations, get hypothesis-matrix artifacts. Use when analyzing documents, structuring research, or testing hypotheses across papers."
when_to_use: "When the user says any of: 'analyze these papers', 'help me think about [research topic]', 'find what to argue with', 'what's load-bearing in this paper', 'set up a research project', 'run a hypothesis matrix on this', 'synthesize across these sources'. Also when the user uploads PDFs / markdown research documents and asks an analysis question."
allowed-tools: "Bash(uv run rp *) Bash(rp *) Bash(ls *) Bash(cat *)"
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

**Reach for it when** the user is asking you to do real research work on multi-document inputs:
- *"Help me figure out what these three papers are actually arguing."*
- *"What should I worry about in this proposal?"*
- *"I want to test the claim that X — what would I need to falsify it?"*
- *"Run an analysis on these PDFs and give me what's load-bearing vs what's hand-waving."*

**Don't reach for it when** the user just wants a quick summary or a one-shot question. `rp` is designed for substantive multi-document research synthesis where the *output format* matters — hypothesis matrix vs report. If the user just asked "what's this paper about", a normal summary is the right answer.

A useful test: would the user benefit from `claims.md`, `hypotheses.md`, `experiments.md`, `decision.md`, `risks.md` as separate, structured, *machine-readable* artifacts they can revisit? If yes, `rp`. If no, just answer in chat.

## Required setup

Before invoking the workflow, confirm:

1. **The MCP server is registered.** Check via `claude mcp list` — you should see `rp: ... ✓ Connected`. If not, register it:
   ```bash
   claude mcp add rp --scope user -- uv --directory \
       /absolute/path/to/research-pipeline run rp mcp serve
   ```
   The user has to run that themselves; you can't.

2. **Local LLM stack is reachable.** `rp` uses the user's `models.toml` for chat + embeddings. If `rp_ingest` fails with a connection error, that's the diagnosis — point them at `models.toml`.

If the MCP server isn't registered, fall back to running `uv run rp project ...` directly via Bash. The CLI surface mirrors the MCP tool surface 1:1; your `allowed-tools` covers it.

## The workflow — typical end-to-end

1. **List existing projects** (`rp_list_projects`) — see whether the user already has work in flight you should resume rather than starting fresh.

2. **Create a new project** (`rp_create_project`) with a *crisp goal statement*. The goal should be a question the agent team can argue about, not a topic. Good: *"Does TKG memory beat blackboard+embeddings on multi-session retrieval at 26B-class generators?"* Bad: *"Memory architectures."*

   By default, use the Phase-1 archetype subset (scout, hypogen, critic). For broader coverage on a substantial question, pass `archetypes=["all"]` to engage all 8 (Literature Scout / Hypothesis Generator / Experimenter / Critic / Replicator / Statistician / Writer / Peer Reviewer).

3. **Ingest documents** (`rp_ingest`) one at a time, providing absolute paths. Each ingest typically takes 5-30s — converts → chunks → embeds → adds to the project blackboard as evidence entries. The user usually has files in `/tmp/`, their Downloads, or a project directory they've mentioned. *Don't* try to ingest files you can't see; ask them for paths.

4. **Run the simulation** — for now (v0.2.0), **this is a CLI step**, not an MCP tool. Run:
   ```bash
   uv run rp project run <project_id> --turns 3 --reddit-every 2
   ```
   `--turns 3` is a good default for a substantive question. `--turns 1` is the smoke-test default. The simulation typically takes 5-30 minutes depending on stack speed and document count. Stream output so the user can see progress.

   *Phase-2 will expose this as `rp_run_simulation` (async, returns job_id, polls via `rp_status`). Until then, CLI fallback.*

5. **Optionally run the optimization loop** — only if the user explicitly asks for refinement, or if the per-agent rubric in the simulation output flagged weak agents. `uv run rp project optimize <project_id> --iterations 3 --turns-per 2` runs targeted re-tuning.

6. **Synthesize the artifacts** — also CLI for v0.2.0:
   ```bash
   uv run rp project synthesize <project_id>
   ```
   Produces the five `.md` files under `projects/project_<id>/artifacts/`. Takes 1-3 minutes.

7. **Fetch the artifacts** (`rp_get_artifacts`) — returns inline content keyed by name. Now you have the hypothesis matrix.

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
- **Ingest fails on a file** — usually models.toml issues. The error message will say so. Tell the user, don't retry blindly.
- **Simulation fails partway** — the project is left in a partial state. `rp_status` shows the blackboard state. You can re-run the simulation from where it stopped, or synthesize from what's there.
- **Synthesize fails** — the file generation falls back to stubs that explain the failure. Surface those — don't pretend.
- **Artifacts already exist when starting** — if the user has an existing project with artifacts, don't blow away their work. Offer to resume, re-run, or start fresh.
- **User asks about a paper that's not ingested** — ingest first, then run, then answer. Don't try to summarize a paper from filename alone.

## Phase-2 features (coming, not yet shipped)

When `rp_run_simulation`, `rp_run_optimize`, and `rp_synthesize` ship as MCP tools (v0.3.0), update the workflow to skip the CLI steps and use these directly with the job-id polling pattern. For now, CLI fallback covers it.

## Examples

See `examples/` in this skill directory for worked end-to-end flows — including the canonical "user uploads three papers and asks for a hypothesis matrix" pattern and the "user has an existing project and wants to add a new paper to it" pattern.

## What this skill is NOT for

- General coding help — use the standard tools.
- Quick paper summarization — answer in chat directly; don't burn 30 minutes on a multi-agent simulation for "what's section 3 about".
- Producing prose reports — `rp` produces *structured* artifacts; if the user wants a flowing essay, write one yourself based on the artifacts.
- Fact-checking single claims — `rp` is for synthesis across multiple sources, not single-source verification.

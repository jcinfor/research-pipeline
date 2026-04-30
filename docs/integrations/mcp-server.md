# Wire `rp` into Claude Code (and other MCP clients)

`rp` v0.2.0+ ships an MCP server that exposes the research pipeline as five tools any MCP-aware agent can call. Claude Code, OpenCode, Cline, Cursor, Goose — anything that speaks MCP can drive `rp project create / ingest / status / get-artifacts` from inside your agent conversation.

This is the MCP surface, complementing the CLI and the dashboard. It runs locally — your stack, your LLM endpoints, your data — same as the rest of `rp`.

> **MCP server vs Claude Skill — the distinction.** This page is about the **MCP server** (`rp mcp serve`). Anthropic's *Skills* are a separate packaged-capability format (`SKILL.md` + instructions). A Skill *wrapping* the MCP server — adding pre-baked instructions on when and how to use the tools — is on the roadmap. The MCP server is fully usable on its own; the Skill is an additive convenience layer.

## What you can do

After registering, your agent can:

- *"Create a new rp project for analyzing graph database papers."*
- *"Ingest these three PDFs into project 4."*
- *"Show me the status of project 4."*
- *"What did the synthesizer produce for project 4?"*

The agent calls `rp_create_project`, `rp_ingest`, `rp_run_simulation`, `rp_get_status`, `rp_get_artifacts` directly — no shell commands needed. Long-running ops use the async job-id pattern (submit returns immediately, agent polls `rp_get_status` until terminal).

## Tools shipped (v0.3.0+)

### Sync tools (return immediately)

| Tool | What it does | Latency |
|---|---|---|
| `rp_list_projects` | List projects with id, goal, status, archetypes | <100ms |
| `rp_create_project` | Create a project with goal + archetype list | <500ms |
| `rp_ingest` | Convert + chunk + embed a document into a project | 5-30s typical |
| `rp_get_status` | Full state for one project — counts, last activity, artifacts available, **active job + recent jobs** | <100ms |
| `rp_get_artifacts` | Fetch synthesized artifact bodies inline | <500ms |

### Async tools (return `job_id`; poll `rp_get_status` to track)

| Tool | What it does | Wall time |
|---|---|---|
| `rp_run_simulation` | Start a simulation. Args: `turns` (default 3), `reddit_every` (default 0). | 5-30 min |
| `rp_run_optimize` | Start the optimization loop. Args: `iterations` (default 3), `turns_per` (default 2), `objective` (`'rubric'` or `'pgr'`), `plateau_patience` (default 2). | 10-60 min |
| `rp_synthesize` | Produce the five structured artifacts (claims/hypotheses/experiments/decision/risks). | 1-3 min |

**Concurrency invariant.** Only one active job per project at a time, regardless of kind. A simulation in flight blocks new submissions of optimize and synthesize too. Submitting a second job for the same project returns `{error: 'project_in_use', active_job_id, ...}` instead of a `job_id` — the agent should poll the active job's status, not stack submissions.

### Polling pattern

```
1. submit  → rp_run_simulation(project_id=X, turns=3) → {job_id: "...", status: "queued"}
2. wait    → ~30s
3. poll    → rp_get_status(project_id=X) → {active_job: {status: "running", current_step: "...", progress_pct: 5.0}, ...}
4. wait    → 60-120s
5. poll    → rp_get_status(project_id=X) → {active_job: null, recent_jobs: [{status: "complete", result: {...}}]}
6. fetch   → rp_get_artifacts(project_id=X)
```

The Claude Skill ([`.claude/skills/rp/SKILL.md`](../../.claude/skills/rp/SKILL.md)) teaches the agent the right cadence (don't busy-loop within a single response turn; spread polls across conversation turns) and how to handle terminal-state edge cases (`failed`, `orphaned`).

## Register with Claude Code

One-time setup. Replace the absolute path with where you cloned `research-pipeline`.

```bash
claude mcp add rp --scope user -- uv --directory \
    /absolute/path/to/research-pipeline run rp mcp serve
```

Verify with:

```bash
claude mcp list
```

You should see:

```
rp: uv --directory /absolute/path/to/research-pipeline run rp mcp serve - ✓ Connected
```

Restart Claude Code. The five `rp_*` tools appear in any new session.

## Register with other MCP clients

The same `rp mcp serve` command is the entrypoint for any stdio-MCP client. Consult the client's MCP configuration docs and use:

- **Command:** `uv`
- **Args:** `--directory /absolute/path/to/research-pipeline run rp mcp serve`
- **Transport:** stdio (default)

Server name surfaced to clients: `research-pipeline`.

## How the server resolves config and data

The server inherits the same resolution paths as the CLI:

- **Database** — `./research_pipeline.db` in the cwd it's launched from. The `--directory` flag in the registration command pins this.
- **Projects directory** — `./projects/` in the same cwd.
- **Models config** — `./models.toml`, `$RP_MODELS_TOML`, `~/.config/research-pipeline/models.toml`, `poc/models.toml` (in resolution order, same as the CLI).

A typical registration pins `--directory` to your `research-pipeline` clone so the server reads/writes the same database the CLI does. If you'd rather isolate MCP-driven work into its own database, register with a different `--directory`.

## Smoke test

In a fresh Claude Code session, ask:

> *"Use rp_list_projects to see what projects exist locally, then create a new one with goal 'test the MCP server' and archetypes ['scout']."*

The agent should call `rp_list_projects`, then `rp_create_project`, and report the new project id. Run `uv run rp project list` from a terminal to confirm it landed in the same database the CLI uses.

## Coming in v0.4.0

- Resource URIs (`rp://projects/{id}/artifacts/{name}`) for clients that prefer URI fetches over inline content.
- SSE progress streaming for clients that support it (richer than poll-based — agent gets notified on transition rather than discovering it via poll).
- Per-project `delete` tool with audit-log preservation.
- Turn-level progress reporting from inside the simulation loop (current Phase 2 ships coarse `queued → running → complete`; v0.4.0 adds `current_step="turn 2/3 — Critic agent"` granularity).

## Troubleshooting

**`Connection failed` on `claude mcp list`**

Run the launch command directly to see the error:

```bash
uv --directory /your/path run rp mcp serve
```

The server logs the database and project directory it'll use to stderr on startup. Common issues:

- Wrong `--directory` path → the cwd has no `pyproject.toml`
- `mcp` package not installed → run `uv sync` in the rp directory
- Python 3.12+ not available in the uv env → `uv python install 3.12`

**Tool calls returning "No database at..."**

The server uses the cwd it was launched in (set by `--directory`). If the CLI normally creates `research_pipeline.db` somewhere else (e.g. you `cd` to a project dir before running CLI commands), the MCP server won't see those projects. Either:

1. Pin the CLI to the same directory you registered the MCP server with, or
2. Re-register the MCP server with a `--directory` matching where the CLI writes.

**`rp_ingest` slow / failing**

The ingest tool runs MarkItDown (PDF/DOCX conversion) + the embedding adapter. First-time PDF conversion in a fresh session can take 30-60s (cold model load). Subsequent calls are faster. If your embedding endpoint isn't reachable, ingest will succeed for the document conversion but report `chunks > 0, added = 0` — fix the embedding endpoint and re-run.

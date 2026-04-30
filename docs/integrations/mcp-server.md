# Wire `rp` into Claude Code (and other MCP clients)

`rp` v0.2.0+ ships an MCP server that exposes the research pipeline as five tools any MCP-aware agent can call. Claude Code, OpenCode, Cline, Cursor, Goose — anything that speaks MCP can drive `rp project create / ingest / status / get-artifacts` from inside your agent conversation.

This is the "skill" surface, complementing the CLI and the dashboard. It runs locally — your stack, your LLM endpoints, your data — same as the rest of `rp`.

## What you can do

After registering, your agent can:

- *"Create a new rp project for analyzing graph database papers."*
- *"Ingest these three PDFs into project 4."*
- *"Show me the status of project 4."*
- *"What did the synthesizer produce for project 4?"*

The agent calls `rp_create_project`, `rp_ingest`, `rp_status`, `rp_get_artifacts` directly — no shell commands needed.

> **Phase 1 scope.** This release ships the five fast / synchronous tools. Long-running operations (`rp_run_simulation`, `rp_run_optimize`, `rp_synthesize`) ship in v0.3.0 with the async/job-id pattern that handles the 30-60s MCP client timeout. For now, run those via the CLI from a separate terminal.

## Tools shipped (phase 1)

| Tool | What it does | Latency |
|---|---|---|
| `rp_list_projects` | List projects with id, goal, status, archetypes | <100ms |
| `rp_create_project` | Create a project with goal + archetype list | <500ms |
| `rp_ingest` | Convert + chunk + embed a document into a project | 5-30s typical |
| `rp_status` | Full state for one project — counts, last activity, artifacts available | <100ms |
| `rp_get_artifacts` | Fetch synthesized artifact bodies inline | <500ms |

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

## Coming in v0.3.0

- `rp_run_simulation` — start a simulation as a background job; returns job_id for polling
- `rp_run_optimize` — same async pattern for the optimization loop
- `rp_synthesize` — produce the artifact bundle (sync if fast enough, async otherwise)
- `rp_status` extended to surface running jobs with progress
- Resource URIs (`rp://projects/{id}/artifacts/{name}`) for clients that prefer URI fetches over inline content

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

"""CLI entry: `rp <command>`.

Commands:
    rp probe <role>                     Smoke-test the LLM adapter for a role.
    rp init-db <path>                   Initialize SQLite schema.
    rp archetypes                       List agent archetypes.
    rp config                           Show resolved models.toml.
    rp project create ...               Create a research project.
    rp project list                     List projects.
    rp project run <id> ...             Run the simulation for a project.
    rp project posts <id>               Show the Twitter feed of a project.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Windows cp1252 terminals mangle em-dash / ellipsis / delta / etc. that Rich
# uses for table rendering. Reconfigure stdout/stderr to UTF-8 with replacement
# fallback so Unicode output doesn't crash or get garbled.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, Exception):
        pass

import typer
from rich.console import Console
from rich.table import Table

from .adapter import LLMClient
from .archetypes import PHASE_1_SUBSET, ROSTER
from .config import load_config
from .db import connect, init_db
from .projects import (
    create_project,
    get_channel_posts,
    get_project_agents,
    list_projects,
    upsert_user,
)

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Research Pipeline CLI")
project_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Projects")
wiki_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Per-user wiki")
mcp_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="MCP server — expose rp as a skill for Claude Code, OpenCode, etc.",
)
app.add_typer(project_app, name="project")
app.add_typer(wiki_app, name="wiki")
app.add_typer(mcp_app, name="mcp")
console = Console()


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Run the MCP server over stdio. Wire this into Claude Code's MCP
    config or any other MCP-aware client.

    Example Claude Code registration (run once from a shell):

        claude mcp add rp --scope user -- uv --directory \\
            /path/to/research-pipeline run rp mcp serve

    The server picks up the local `research_pipeline.db` and `models.toml`
    in the cwd it's launched from — same as the rest of the CLI.
    """
    from .mcp_server import build_server

    server = build_server()
    console.print(
        f"[dim]rp mcp serve · cwd={Path.cwd()} · "
        "expose rp_list_projects, rp_create_project, rp_ingest, rp_status, "
        "rp_get_artifacts[/dim]",
        style="dim",
    )
    server.run()


@app.command()
def probe(role: str = typer.Argument("agent_bulk")) -> None:
    """Ping the LLM adapter for a given role and print PASS/FAIL."""
    client = LLMClient()
    info = client.role_info(role)
    console.print(f"[bold]role[/bold]    = {role}")
    console.print(f"base_url = {info.base_url}")
    console.print(f"model    = {info.model}")
    resp = client.chat(
        role,
        messages=[
            {"role": "system", "content": "You are a terse assistant."},
            {"role": "user", "content": "Reply with exactly: PROBE_OK"},
        ],
        max_tokens=16,
        temperature=0,
    )
    out = resp.choices[0].message.content or ""
    console.print(f"response = {out!r}")
    if "PROBE_OK" in out:
        console.print("[green]PASS[/green]")
        raise typer.Exit(0)
    console.print("[yellow]WEAK (live but response off)[/yellow]")
    raise typer.Exit(1)


@app.command("probe-embed")
def probe_embed(role: str = typer.Argument("embedding")) -> None:
    """Ping the LLM adapter's embedding endpoint for a role and print dim."""
    client = LLMClient()
    info = client.role_info(role)
    console.print(f"[bold]role[/bold]    = {role}")
    console.print(f"base_url = {info.base_url}")
    console.print(f"model    = {info.model}")
    vecs = client.embed(role, ["KRAS G12C inhibitor beyond sotorasib"])
    dim = len(vecs[0]) if vecs else 0
    console.print(f"dim      = {dim}")
    first3 = [round(x, 4) for x in vecs[0][:3]] if vecs else []
    console.print(f"sample   = {first3}")
    if dim > 0:
        console.print("[green]PASS[/green]")
        raise typer.Exit(0)
    console.print("[red]FAIL[/red]")
    raise typer.Exit(1)


@app.command("init-db")
def init_db_cmd(path: Path = typer.Argument(Path("research_pipeline.db"))) -> None:
    init_db(path)
    console.print(f"[green]OK[/green]: schema initialized at {path}")


@app.command()
def archetypes() -> None:
    t = Table(title="Agent Archetypes")
    t.add_column("id")
    t.add_column("name")
    t.add_column("role_hint")
    t.add_column("tw/turn", justify="right")
    t.add_column("rd/turn", justify="right")
    for a in ROSTER:
        t.add_row(a.id, a.name, a.role_hint, str(a.twitter_posts_per_turn), str(a.reddit_posts_per_turn))
    console.print(t)


@app.command()
def config() -> None:
    cfg = load_config()
    console.print(f"[bold]source[/bold] = {cfg.source}")
    t = Table(title="Roles")
    t.add_column("role")
    t.add_column("backend")
    t.add_column("base_url")
    t.add_column("model")
    for name, rc in cfg.roles.items():
        t.add_row(name, rc.backend, rc.base_url, rc.model)
    console.print(t)


@app.command()
def demo(
    turns: int = typer.Option(
        1, "--turns", help="Simulation turns to run (1 is fastest; 3 produces fuller artifacts)."
    ),
    optimize: bool = typer.Option(
        False, "--optimize", help="Run one optimize iteration after the simulation."
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
    work_dir: Path = typer.Option(Path("./runs"), "--work-dir", help="OASIS / simulation working dir."),
    project_dir: Path = typer.Option(Path("./projects"), "--project-dir", help="Where to write artifacts."),
) -> None:
    """End-to-end demo on bundled sample papers — try `rp` without your own data.

    Runs the full pipeline (probe → create → ingest → run → synthesize) on
    three short sample papers about agent-memory architectures. Designed to
    finish in ~5 minutes on a local LLM endpoint with --turns 1.
    """
    from .archetypes import PHASE_1_SUBSET
    from .projects import create_project, upsert_user
    from .ingest import ingest_file
    from .simulation import run_simulation, SimulationConfig
    from .synthesize import synthesize_artifacts

    repo_root = Path(__file__).resolve().parents[2]
    samples_dir = repo_root / "demo" / "sample_papers"
    sample_files = sorted(samples_dir.glob("*.md"))
    if not sample_files:
        console.print(
            f"[red]ERROR[/red]: no sample papers found at {samples_dir}. "
            "If you cloned the repo cleanly they should be there — check the demo/ folder."
        )
        raise typer.Exit(1)

    console.print("[bold]rp demo[/bold] — running end-to-end on bundled samples\n")

    # 1. Probe backends so failures surface early with a clear message.
    console.print("[1/5] Probing LLM backends…")
    client = LLMClient()
    try:
        resp = client.chat(
            "agent_bulk",
            messages=[
                {"role": "system", "content": "You are a terse assistant."},
                {"role": "user", "content": "Reply with exactly: PROBE_OK"},
            ],
            max_tokens=16, temperature=0,
        )
        if "PROBE_OK" not in (resp.choices[0].message.content or ""):
            console.print("[yellow]WARN[/yellow]: chat probe responded but the response was off — proceeding anyway.")
    except Exception as e:
        console.print(
            f"[red]ERROR[/red]: chat backend unreachable ({e}).\n"
            "Did you copy `poc/models.toml` to `models.toml` and edit the base_url?"
        )
        raise typer.Exit(1)
    try:
        v = client.embed("embedding", "probe")
        console.print(f"   chat OK · embedding OK (dim={len(v[0])})")
    except Exception as e:
        console.print(
            f"[red]ERROR[/red]: embedding backend unreachable ({e}).\n"
            "Check the [roles.embedding] section of models.toml."
        )
        raise typer.Exit(1)

    # 2. Create the demo project. Always fresh — no reuse logic, simpler mental model.
    console.print("\n[2/5] Creating demo project…")
    init_db(db_path)
    with connect(db_path) as conn:
        user_id = upsert_user(conn, "demo@research-pipeline")
        pid = create_project(
            conn, user_id=user_id,
            goal=(
                "Compare three agent-memory architectures (mem0 flat-store, Zep graph, "
                "and the three-tier blackboard+wiki). Recommend one for a multi-agent "
                "research pipeline use case and identify the strongest open question."
            ),
            archetype_ids=list(PHASE_1_SUBSET),
        )
    console.print(f"   created project #{pid}")

    # 3. Ingest the bundled samples (one file at a time — same as `rp project ingest`).
    console.print(f"\n[3/5] Ingesting {len(sample_files)} sample paper(s)…")
    ingest_work_dir = work_dir / f"project_{pid}"  # OASIS-side raw/ folder
    total = {"added": 0, "echoed": 0, "chunks": 0}
    with connect(db_path) as conn:
        for fp in sample_files:
            res = ingest_file(
                conn, project_id=pid, path=fp,
                work_dir=ingest_work_dir, llm=client,
            )
            total["added"] += res.added
            total["echoed"] += res.echoed
            total["chunks"] += res.chunks
            console.print(f"   {fp.name}: {res.added} added, {res.echoed} echoed, {res.chunks} chunks")
    console.print(f"   total: {total['added']} added, {total['echoed']} echoed, {total['chunks']} chunks")

    # 4. Run the simulation.
    console.print(f"\n[4/5] Running simulation ({turns} turn{'s' if turns != 1 else ''}, reddit-every=2)…")
    sim_result = asyncio.run(
        run_simulation(
            SimulationConfig(
                project_id=pid, turn_cap=turns, reddit_round_every=2,
            ),
            db_path=db_path, work_dir=work_dir,
        )
    )
    console.print(f"   {sim_result.turns_run} turns, {sim_result.posts_total} posts")

    if optimize:
        from .optimize import optimize_project
        console.print("\n[+] Running one optimize iteration…")
        asyncio.run(
            optimize_project(
                project_id=pid, iterations=1, turns_per=turns,
                db_path=db_path, work_dir=work_dir,
                objective="rubric", project_dir=project_dir,
            )
        )

    # 5. Synthesize artifacts. Use --project-dir as the artifact root (same
    # convention as `rp project synthesize`); synthesize will append
    # `project_{pid}/artifacts/` itself, giving e.g. `projects/project_9/artifacts/`.
    console.print("\n[5/5] Synthesizing structured artifacts…")
    async def _synth():
        with connect(db_path) as conn:
            return await synthesize_artifacts(
                conn, project_id=pid, llm=client,
                out_dir=None, project_dir=project_dir,
            )
    synth_result = asyncio.run(_synth())
    artifacts_dir = synth_result.out_dir
    rel = artifacts_dir.relative_to(repo_root) if artifacts_dir.is_relative_to(repo_root) else artifacts_dir
    console.print(f"   wrote {len(synth_result.artifacts)} artifact(s) to [bold]{rel}/[/bold]\n")

    console.print("[bold green]Demo complete.[/bold green]")
    console.print(f"  • Read the artifacts:    cat {rel}/decision.md")
    console.print(f"  • Open the dashboard:    [bold]rp serve[/bold]   (http://127.0.0.1:8765/)")
    console.print(f"  • Try a fuller run:      rp project optimize {pid} --iterations 3")


# ---------------------------------------------------------------------------
# Project subcommands
# ---------------------------------------------------------------------------


@project_app.command("create")
def project_create(
    goal: str = typer.Option(..., "--goal", help="Research goal / focus."),
    user_email: str = typer.Option("local@research-pipeline", "--user"),
    archetype_ids: str = typer.Option(
        ",".join(PHASE_1_SUBSET),
        "--archetypes",
        help="Comma-separated archetype ids. Use 'all' for the full 8, or "
             "'auto' to let the LLM planner choose.",
    ),
    auto_agents: int = typer.Option(
        5, "--auto-agents",
        help="Total agent budget when --archetypes=auto.",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    init_db(db_path)
    archetype_list: list[str]
    if archetype_ids.strip().lower() == "all":
        archetype_list = [a.id for a in ROSTER]
    elif archetype_ids.strip().lower() == "auto":
        from .planner import expand_plan_to_archetype_list, plan_archetypes

        client = LLMClient()
        with connect(db_path) as conn:
            uid = upsert_user(conn, user_email)
            plan = plan_archetypes(
                conn, goal=goal, user_id=uid,
                n_agents=auto_agents, llm=client,
            )
        archetype_list = expand_plan_to_archetype_list(plan)
        console.print("[bold]planner selected[/bold]")
        for p in plan:
            console.print(f"  {p.archetype_id} x{p.weight} — {p.rationale[:100]}")
    else:
        archetype_list = [a.strip() for a in archetype_ids.split(",") if a.strip()]

    with connect(db_path) as conn:
        uid = upsert_user(conn, user_email)
        pid = create_project(
            conn, user_id=uid, goal=goal, archetype_ids=archetype_list
        )
    console.print(f"[green]project {pid} created[/green] for user {user_email}")
    console.print(f"  goal       = {goal}")
    console.print(f"  archetypes = {archetype_list}")


@project_app.command("list")
def project_list(
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        projects = list_projects(conn)
        t = Table(title="Projects")
        t.add_column("id", justify="right")
        t.add_column("user_id", justify="right")
        t.add_column("status")
        t.add_column("archetypes")
        t.add_column("goal")
        for p in projects:
            agents = get_project_agents(conn, p.id)
            arches = ",".join(a.archetype for a in agents)
            t.add_row(str(p.id), str(p.user_id), p.status, arches, p.goal[:50])
    console.print(t)


@project_app.command("run")
def project_run(
    project_id: int = typer.Argument(...),
    turns: int = typer.Option(3, "--turns"),
    reddit_every: int = typer.Option(
        0, "--reddit-every",
        help="Run one Reddit thread every N Twitter turns (0 = off).",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
    work_dir: Path = typer.Option(Path("./runs"), "--work-dir"),
) -> None:
    """Run the OASIS simulation loop for a project."""
    from .simulation import SimulationConfig, run_simulation

    init_db(db_path)
    console.print(f"[bold]running project {project_id} for {turns} turn(s)...[/bold]")
    with console.status(
        f"simulating · {turns} turn(s) · reddit-every={reddit_every}",
        spinner="dots",
    ):
        result = asyncio.run(
            run_simulation(
                SimulationConfig(
                    project_id=project_id,
                    turn_cap=turns,
                    reddit_round_every=reddit_every,
                ),
                db_path=db_path,
                work_dir=work_dir,
            )
        )
    console.print(f"[green]done[/green]: {result.turns_run} turns, {result.posts_total} posts")
    console.print(f"oasis_db = {result.oasis_db_path}")


@project_app.command("agents")
def project_agents(
    project_id: int = typer.Argument(...),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Inspect the per-agent config + latest rubric scores for a project."""
    from .per_agent_rubric import latest_per_agent_scores, AGENT_RUBRIC_METRICS
    from .projects import get_project_agents

    init_db(db_path)
    with connect(db_path) as conn:
        agents = get_project_agents(conn, project_id)
        scores = latest_per_agent_scores(conn, project_id=project_id)

    if not agents:
        console.print(f"[yellow]project {project_id} has no agents[/yellow]")
        return

    t = Table(title=f"Project {project_id} — agents")
    t.add_column("id", justify="right")
    t.add_column("archetype")
    t.add_column("temp", justify="right")
    t.add_column("max_tok", justify="right")
    t.add_column("specialty", overflow="fold")
    for m in AGENT_RUBRIC_METRICS:
        t.add_column(m[:8], justify="right")
    for a in agents:
        row = [
            str(a.id),
            a.archetype,
            f"{a.temperature:.2f}",
            str(a.max_tokens),
            a.specialty_focus or "—",
        ]
        s = scores.get(a.id, {})
        for m in AGENT_RUBRIC_METRICS:
            v = s.get(m)
            row.append(f"{v:.1f}" if v is not None else "—")
        t.add_row(*row)
    console.print(t)


@project_app.command("posts")
def project_posts(
    project_id: int = typer.Argument(...),
    channel: str = typer.Option("twitter", "--channel"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = get_channel_posts(conn, project_id, channel=channel)
        t = Table(title=f"Project {project_id} — {channel}")
        t.add_column("id", justify="right")
        t.add_column("turn", justify="right")
        t.add_column("agent", justify="right")
        t.add_column("content", overflow="fold")
        for r in rows:
            t.add_row(str(r["id"]), str(r["turn"]), str(r["agent_id"]), r["content"])
    console.print(t)


@project_app.command("blackboard")
def project_blackboard(
    project_id: int = typer.Argument(...),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Render the project blackboard as markdown."""
    from .blackboard import render_markdown

    init_db(db_path)
    with connect(db_path) as conn:
        md = render_markdown(conn, project_id)
    console.print(md)


@project_app.command("pi-post")
def project_pi_post(
    project_id: int = typer.Argument(...),
    message: str = typer.Argument(...),
    channel: str = typer.Option("twitter", "--channel"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Inject a Principal-Investigator post into the channel.

    Shows up in agents' next-turn context as [PI]. Use to redirect the
    conversation, seed a new angle, or course-correct mid-project.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        next_turn = conn.execute(
            "SELECT COALESCE(MAX(turn), -1) + 1 AS t FROM channel_posts WHERE project_id = ?",
            (project_id,),
        ).fetchone()["t"]
        cur = conn.execute(
            "INSERT INTO channel_posts (project_id, channel, agent_id, content, turn) "
            "VALUES (?, ?, NULL, ?, ?)",
            (project_id, channel, message, next_turn),
        )
        conn.commit()
    console.print(f"[green]PI post[/green] #{cur.lastrowid} (turn {next_turn}) inserted")


@project_app.command("plan")
def project_plan(
    goal: str = typer.Option(..., "--goal"),
    user_email: str = typer.Option("local@research-pipeline", "--user"),
    n_agents: int = typer.Option(5, "--n"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Ask the LLM planner to propose a weighted archetype subset for a goal."""
    from .planner import plan_archetypes

    init_db(db_path)
    client = LLMClient()
    with connect(db_path) as conn:
        uid = upsert_user(conn, user_email)
        plan = plan_archetypes(
            conn, goal=goal, user_id=uid, n_agents=n_agents, llm=client,
        )
    t = Table(title=f"Planner proposal ({sum(p.weight for p in plan)} agents)")
    t.add_column("archetype")
    t.add_column("weight", justify="right")
    t.add_column("rationale", overflow="fold")
    for p in plan:
        t.add_row(p.archetype_id, str(p.weight), p.rationale)
    console.print(t)


@project_app.command("kg")
def project_kg(
    project_id: int = typer.Argument(...),
    project_dir: Path = typer.Option(
        Path("./projects"), "--project-dir",
        help="Parent dir holding the project's raw/ materials.",
    ),
    output_dir: Path = typer.Option(
        None, "--out",
        help="Where graphify should write its outputs. Default: projects/{id}/kg/",
    ),
) -> None:
    """Build a Graphify knowledge graph over the project's ingested raw/ files.

    Requires the `graphify` CLI on PATH (see https://graphify.net/). We run it
    as a subprocess pointed at projects/{id}/raw/ and produce an interactive
    graph.html plus an Obsidian vault.
    """
    import shutil
    import subprocess

    if shutil.which("graphify") is None:
        console.print(
            "[red]graphify not installed.[/red] "
            "Install with: [bold]pipx install graphifyy && graphify install[/bold]"
        )
        raise typer.Exit(1)

    raw_dir = project_dir / f"project_{project_id}" / "raw"
    if not raw_dir.exists():
        console.print(
            f"[yellow]no raw/ dir for project {project_id}[/yellow] — "
            "run `rp project ingest <id> <files>` first."
        )
        raise typer.Exit(1)

    out = output_dir or (project_dir / f"project_{project_id}" / "kg")
    out.mkdir(parents=True, exist_ok=True)

    cmd = ["graphify", str(raw_dir), "--obsidian", "--wiki", "-o", str(out)]
    console.print(f"[bold]running:[/bold] {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]graphify failed:[/red] {e}")
        raise typer.Exit(2)
    console.print(f"[green]kg written[/green] to {out}")
    html = out / "graph.html"
    if html.exists():
        console.print(f"open {html} in a browser to explore the graph")


@project_app.command("reddit-round")
def project_reddit_round(
    project_id: int = typer.Argument(...),
    topic: str | None = typer.Option(
        None, "--topic",
        help="Explicit thread topic. If omitted, falls back to the latest "
             "hypothesis on the project blackboard, then the project goal.",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Run one ad-hoc Reddit-style thread round on an existing project."""
    from .blackboard import KIND_EVIDENCE
    from .projects import get_project, get_project_agents
    from .archetypes import by_id as archetype_by_id
    from .retrieval import search_blackboard
    from .simulation import _run_reddit_round

    init_db(db_path)
    client = LLMClient()
    with connect(db_path) as conn:
        project = get_project(conn, project_id)
        agents = get_project_agents(conn, project_id)
        if not agents:
            console.print(f"[red]project {project_id} has no agents[/red]")
            raise typer.Exit(1)
        archetypes = [archetype_by_id(a.archetype) for a in agents]
        try:
            evidence = search_blackboard(
                conn, project_id=project_id, query=project.goal,
                llm=client, top_k=6, kind=KIND_EVIDENCE,
            )
        except Exception as e:
            print(f"[cli] evidence retrieval skipped: {e}")
            evidence = []
        next_turn = conn.execute(
            "SELECT COALESCE(MAX(turn), -1) + 1 AS t FROM channel_posts WHERE project_id = ?",
            (project_id,),
        ).fetchone()["t"]
        console.print(f"[bold]running reddit round on project {project_id} (turn {next_turn})...[/bold]")
        root_id = asyncio.run(
            _run_reddit_round(
                conn,
                project_id=project_id,
                llm=client,
                project_goal=project.goal,
                archetypes=archetypes,
                evidence_pool=evidence,
                turn=next_turn,
                topic=topic,
            )
        )
    if root_id:
        console.print(f"[green]reddit round complete[/green] — root post id {root_id}")
    else:
        console.print("[yellow]reddit round produced no content[/yellow]")


@project_app.command("ingest")
def project_ingest(
    project_id: int = typer.Argument(...),
    files: list[Path] = typer.Argument(..., help="Files to ingest (PDF, DOCX, HTML, MD, ...)"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
    work_dir: Path = typer.Option(Path("./projects"), "--work-dir"),
    chunk_max_chars: int = typer.Option(1600, "--chunk-max"),
) -> None:
    """Convert files via MarkItDown and file each chunk as blackboard evidence.

    Pre-seed a project with real sources so agents can retrieve and cite them
    during the simulation instead of hallucinating references.
    """
    try:
        from .ingest import ingest_file
    except ImportError:
        console.print(
            "[red]markitdown not installed.[/red] "
            "Run: [bold]uv sync --extra ingest[/bold]"
        )
        raise typer.Exit(1)

    init_db(db_path)
    client = LLMClient()
    project_dir = work_dir / f"project_{project_id}"

    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn,
    )
    total = {"added": 0, "echoed": 0, "chunks": 0}
    with connect(db_path) as conn:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]ingesting[/bold]"),
            BarColumn(bar_width=None),
            MofNCompleteColumn(),
            TextColumn("[dim]{task.fields[file]}[/dim]"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("ingest", total=len(files), file="…")
            for file_path in files:
                progress.update(task, file=file_path.name)
                if not file_path.exists():
                    progress.console.print(f"[yellow]skip[/yellow] {file_path} (not found)")
                    progress.advance(task)
                    continue
                res = ingest_file(
                    conn,
                    project_id=project_id,
                    path=file_path,
                    work_dir=project_dir,
                    llm=client,
                    chunk_max_chars=chunk_max_chars,
                )
                progress.console.print(
                    f"  [green]{res.file}[/green]: "
                    f"{res.added} added, {res.echoed} echoed, "
                    f"{res.chunks} chunks total"
                )
                total["added"] += res.added
                total["echoed"] += res.echoed
                total["chunks"] += res.chunks
                progress.advance(task)
    console.print(
        f"[bold]done[/bold]: {total['added']} evidence entries added, "
        f"{total['echoed']} echoed (dedup), {total['chunks']} chunks total"
    )


@project_app.command("redirect")
def project_redirect(
    project_id: int = typer.Argument(...),
    goal: str = typer.Option(..., "--goal"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Update the research goal for a project. Takes effect on the next `rp project run`."""
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE projects SET goal = ? WHERE id = ?", (goal, project_id)
        )
        conn.commit()
    console.print(f"[green]goal updated[/green] for project {project_id}")
    console.print(f"  new goal = {goal}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Launch the web dashboard at http://HOST:PORT/."""
    import os

    import uvicorn

    os.environ["RP_DB_PATH"] = str(db_path.resolve())
    console.print(
        f"[bold]serving dashboard[/bold] on http://{host}:{port}/  (db={db_path.resolve()})"
    )
    uvicorn.run("research_pipeline.api:app", host=host, port=port, reload=reload)


@project_app.command("triangulate")
def project_triangulate(
    project_id: int = typer.Argument(...),
    samples: int = typer.Option(
        3, "--samples", "--runs",
        help="How many independent Writer samples (legacy alias: --runs).",
    ),
    temperature: float = typer.Option(
        0.55, "--temperature",
        help="Writer temperature per sample (higher = more variance).",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Reproducibility diagnostic — issue N Writer samples of the claim-
    synthesis step and measure how stable the produced claims are across
    samples.

    High score (~1.0): pipeline produces skill, not luck. Low score (~0.3):
    claims are sampling accidents. Not part of the PGR composite because
    it's expensive and measures a different axis (reproducibility vs.
    correctness). See docs/terminology.md.
    """
    import asyncio

    from .triangulate import triangulate_project

    init_db(db_path)
    client = LLMClient()
    console.print(
        f"[bold]triangulating project {project_id}[/bold] "
        f"({samples} samples at temperature={temperature})"
    )
    with connect(db_path) as conn:
        result = asyncio.run(
            triangulate_project(
                conn, project_id=project_id, llm=client,
                n_runs=samples, temperature=temperature,
            )
        )
    console.print(
        f"[green]done[/green]: mean_pairwise_similarity = "
        f"[bold]{result.score:.3f}[/bold] "
        f"(claims per sample: {result.per_run_claim_counts})"
    )
    for i, titles in enumerate(result.run_samples):
        console.print(f"\n[bold]sample {i+1}[/bold] ({len(titles)} claims):")
        for t in titles[:6]:
            console.print(f"  · {t[:120]}")


@project_app.command("pgr-plan")
def project_pgr_plan(
    project_id: int = typer.Argument(...),
    apply: bool = typer.Option(
        False, "--apply",
        help="Save the recommendation to the project's pgr_config.",
    ),
    refine: bool = typer.Option(
        False, "--refine",
        help="Ask the planner LLM to nudge weights based on project goal domain.",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Show recommended PGR proxies for a project based on its current state.

    Inspects ingested corpus size, held-out partition, and hypothesis count;
    proposes which proxies to enable and with what weights. Pass --apply to
    save the recommendation as the project's pgr_config (otherwise it's just
    displayed). Override individual weights later with `rp project pgr-set`.
    """
    from .pgr_planner import plan_to_config, recommend_pgr_plan
    from .projects import update_pgr_config

    init_db(db_path)
    llm = LLMClient() if refine else None
    with connect(db_path) as conn:
        plan = recommend_pgr_plan(conn, project_id, llm=llm)

    t = Table(title=f"Project {project_id} — PGR proxy recommendation")
    t.add_column("id")
    t.add_column("name")
    t.add_column("enabled")
    t.add_column("weight", justify="right")
    t.add_column("rationale", overflow="fold")
    for p in plan.proxies:
        enabled_str = "[green]yes[/green]" if p.enabled else "[yellow]no[/yellow]"
        t.add_row(p.id, p.name, enabled_str, f"{p.weight:.2f}", p.rationale)
    console.print(t)
    console.print(f"[bold]composite[/bold] = {plan.composite_formula}")
    for n in plan.notes:
        console.print(f"  · {n}")

    if apply:
        with connect(db_path) as conn:
            update_pgr_config(
                conn, project_id=project_id, config=plan_to_config(plan),
            )
        console.print(f"[green]saved[/green] recommendation to project {project_id}'s pgr_config")


@project_app.command("pgr-set")
def project_pgr_set(
    project_id: int = typer.Argument(...),
    cite: float | None = typer.Option(None, "--cite", help="Weight for pgr_cite (0-1)."),
    heldout: float | None = typer.Option(None, "--heldout", help="Weight for pgr_heldout."),
    adv: float | None = typer.Option(None, "--adv", help="Weight for pgr_adv."),
    skip_cite: bool = typer.Option(False, "--skip-cite"),
    skip_heldout: bool = typer.Option(False, "--skip-heldout"),
    skip_adv: bool = typer.Option(False, "--skip-adv"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Explicitly set PGR proxy weights + enable/disable flags for a project.

    Unspecified weights default to 0; enabled proxies have their weights
    renormalized to sum to 1.0. Use `rp project pgr-plan` first to see
    recommended defaults.
    """
    import json as _json

    from .pgr_planner import parse_override
    from .projects import update_pgr_config

    init_db(db_path)
    config = parse_override(
        cite=cite, heldout=heldout, adv=adv,
        skip_cite=skip_cite, skip_heldout=skip_heldout, skip_adv=skip_adv,
    )
    with connect(db_path) as conn:
        update_pgr_config(conn, project_id=project_id, config=config)
    console.print(f"[green]saved[/green] pgr_config for project {project_id}")
    console.print(_json.dumps(config, indent=2))


@project_app.command("score")
def project_score(
    project_id: int = typer.Argument(...),
    skip_adv: bool = typer.Option(
        False, "--skip-adv",
        help="Skip the adversarial (Red Team) proxy; cite + heldout only.",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
    project_dir: Path = typer.Option(Path("./projects"), "--project-dir"),
) -> None:
    """Score a project's research quality with PGR proxies.

    Requires claims.md (run `rp project synthesize <id>` first). Runs three
    proxies: citation-trace verifiability, held-out evidence alignment, and
    adversarial Red Team. Persists scores to kpi_scores.
    """
    from .pgr import score_project

    init_db(db_path)
    client = LLMClient()
    claims_path = project_dir / f"project_{project_id}" / "artifacts" / "claims.md"
    if not claims_path.exists():
        console.print(
            f"[red]claims.md not found[/red] at {claims_path}. "
            f"Run [bold]rp project synthesize {project_id}[/bold] first."
        )
        raise typer.Exit(1)

    console.print(f"[bold]scoring project {project_id}...[/bold]")
    with connect(db_path) as conn:
        comp = score_project(
            conn, project_id=project_id, llm=client,
            project_dir=project_dir, skip_adv=skip_adv,
        )

    t = Table(title=f"Project {project_id} PGR")
    t.add_column("proxy")
    t.add_column("score", justify="right")
    t.add_column("totals")
    t.add_row(
        "pgr_cite (strict verifiability)",
        f"{comp.cite:.2f}",
        str(comp.detail.get("cite_totals", {})),
    )
    support_score = comp.detail.get("support_score")
    if support_score is not None:
        t.add_row(
            "pgr_support (partial-credit)",
            f"{support_score:.2f}",
            str(comp.detail.get("support_totals", {})),
        )
    t.add_row(
        "pgr_heldout (generalization)",
        f"{comp.heldout:.2f}",
        str(comp.detail.get("heldout_totals", {})),
    )
    t.add_row(
        "pgr_adv (Red Team)",
        f"{comp.adv:.2f}" if not skip_adv else "skipped",
        str(comp.detail.get("adv_totals", {})) if not skip_adv else "—",
    )
    t.add_row(
        "[bold]composite (cite+heldout+adv)[/bold]",
        f"[bold]{comp.composite:.2f}[/bold]",
        "—",
    )
    console.print(t)
    if support_score is not None:
        gap = support_score - comp.cite
        if gap > 0.15:
            console.print(
                f"[yellow]note:[/yellow] pgr_support ({support_score:.2f}) "
                f"exceeds pgr_cite ({comp.cite:.2f}) by {gap:.2f} — claims are "
                f"synthesized beyond literal source content but remain "
                f"inferentially grounded. See docs/aar-comparison.md."
            )


@project_app.command("synthesize")
def project_synthesize(
    project_id: int = typer.Argument(...),
    out: Path | None = typer.Option(None, "--out", help="Output directory (default: projects/{id}/artifacts)"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
    project_dir: Path = typer.Option(Path("./projects"), "--project-dir"),
) -> None:
    """Produce structured result artifacts (claims, hypotheses, experiments,
    decision, risks) alongside the prose report."""
    import asyncio

    from .synthesize import synthesize_artifacts

    init_db(db_path)
    client = LLMClient()
    console.print(f"[bold]synthesizing artifacts[/bold] for project {project_id}...")

    async def _run():
        with connect(db_path) as conn:
            return await synthesize_artifacts(
                conn, project_id=project_id, llm=client,
                out_dir=out, project_dir=project_dir,
            )

    result = asyncio.run(_run())
    console.print(f"[green]done[/green]: {result.out_dir}")
    for name, path in result.artifacts.items():
        size = path.stat().st_size
        console.print(f"  {name:12s} {path}  ({size} B)")


@project_app.command("export")
def project_export(
    project_id: int = typer.Argument(...),
    out: Path | None = typer.Option(None, "--out", help="Output zip path."),
    project_dir: Path = typer.Option(
        Path("./projects"), "--project-dir",
        help="Directory holding projects/{id}/ (raw, report, kg).",
    ),
    runs_dir: Path = typer.Option(
        Path("./runs"), "--runs-dir",
        help="Directory holding OASIS simulation DBs.",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Bundle a project into a shareable zip (report, blackboard, raw/, kg/, OASIS db)."""
    from .export import export_project

    init_db(db_path)
    with connect(db_path) as conn:
        path = export_project(
            conn, project_id=project_id, out_path=out,
            project_dir=project_dir, runs_dir=runs_dir,
        )
    size = path.stat().st_size
    kb = size / 1024
    console.print(f"[green]exported[/green] {path}  ({kb:.1f} KB)")


@project_app.command("optimize")
def project_optimize(
    project_id: int = typer.Argument(...),
    iterations: int = typer.Option(3, "--iterations"),
    turns_per: int = typer.Option(2, "--turns-per"),
    objective: str = typer.Option(
        "rubric", "--objective",
        help="Plateau-check against: 'rubric' (default) or 'pgr' composite.",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
    work_dir: Path = typer.Option(Path("./runs"), "--work-dir"),
    project_dir: Path = typer.Option(Path("./projects"), "--project-dir"),
) -> None:
    """Run the optimization loop: short sim -> per-agent rubric ->
    targeted config adjustment -> re-run until plateau or iteration cap.

    --objective pgr uses PGR composite (citation-trace + held-out) as the
    plateau signal instead of the rubric mean. Requires claims.md; will
    synthesize it if missing.
    """
    import asyncio

    from .optimize import optimize_project

    init_db(db_path)
    console.print(
        f"[bold]optimizing project {project_id}[/bold] "
        f"({iterations} iterations × {turns_per} turns, objective={objective})"
    )
    with console.status(
        f"optimizing · up to {iterations} iteration(s) · "
        f"each runs ~{turns_per} turn(s) + scoring + adjustment",
        spinner="dots",
    ):
        result = asyncio.run(
            optimize_project(
                project_id=project_id,
                iterations=iterations,
                turns_per=turns_per,
                db_path=db_path,
                work_dir=work_dir,
                objective=objective,
                project_dir=project_dir,
            )
        )
    console.print(
        f"[green]done[/green]: {result.iterations_run} iterations, "
        f"terminated [{result.terminated_reason}], "
        f"best iteration = {result.best_iteration}"
    )
    t = Table(title="Optimization trace")
    t.add_column("iter", justify="right")
    t.add_column("weakest agent")
    t.add_column("weakest dim")
    t.add_column("decision")
    t.add_column("max delta", justify="right")
    t.add_column("plateau")
    for r in result.trace:
        max_d = max((abs(v) for v in r.kpi_delta.values()), default=0.0)
        action = r.decision.action if r.decision else "—"
        t.add_row(
            str(r.iteration),
            str(r.weakest_agent_id) if r.weakest_agent_id else "—",
            r.weakest_metric or "—",
            action,
            f"{max_d:.2f}",
            "✓" if r.plateau else "",
        )
    console.print(t)


@project_app.command("trace")
def project_trace(
    project_id: int = typer.Argument(...),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Show the persisted optimization trace for a project."""
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT iteration, weakest_agent_id, decision_rationale, "
            "config_delta_json, kpi_before_json, kpi_after_json "
            "FROM optimization_traces WHERE project_id = ? ORDER BY iteration",
            (project_id,),
        ).fetchall()
    if not rows:
        console.print(f"[yellow]no optimization trace for project {project_id}[/yellow]")
        return
    t = Table(title=f"Project {project_id} optimization trace")
    t.add_column("iter", justify="right")
    t.add_column("weakest")
    t.add_column("decision", overflow="fold")
    t.add_column("rationale", overflow="fold")
    import json as _json
    for r in rows:
        delta_cfg = _json.loads(r["config_delta_json"] or "{}")
        action = delta_cfg.get("action", "—")
        t.add_row(
            str(r["iteration"]),
            str(r["weakest_agent_id"]) if r["weakest_agent_id"] else "—",
            action,
            r["decision_rationale"] or "",
        )
    console.print(t)


@project_app.command("report")
def project_report(
    project_id: int = typer.Argument(...),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
    out_dir: Path = typer.Option(Path("./projects"), "--out-dir"),
) -> None:
    """Regenerate the Writer+Reviewer synthesis report for a project."""
    import asyncio

    from .report import generate_report

    init_db(db_path)

    async def _run():
        with connect(db_path) as conn:
            return await generate_report(
                conn, project_id=project_id, work_dir=out_dir
            )

    result = asyncio.run(_run())
    console.print(f"[green]report written[/green]: {result.report_path}")
    scores = result.review.get("scores", {}) or {}
    if scores:
        console.print("Reviewer scores: " + ", ".join(f"{k}={v}" for k, v in scores.items()))
    assessment = result.review.get("assessment") or ""
    if assessment:
        console.print(f"Reviewer: {assessment}")


# ---------------------------------------------------------------------------
# Wiki subcommands
# ---------------------------------------------------------------------------


@wiki_app.command("promote")
def wiki_promote(
    project_id: int = typer.Argument(...),
    top_k: int = typer.Option(3, "--top-k", help="Top-K per kind to promote."),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Promote the best entries from a project's blackboard into the user wiki."""
    from .wiki import promote_project_to_wiki

    init_db(db_path)
    with connect(db_path) as conn:
        counts = promote_project_to_wiki(
            conn, project_id=project_id, top_k_per_kind=top_k
        )
    if not counts:
        console.print(f"[yellow]no entries promoted[/yellow] from project {project_id}")
        return
    total = sum(counts.values())
    console.print(f"[green]promoted {total}[/green] entries from project {project_id}")
    for kind, n in counts.items():
        console.print(f"  {kind}: {n}")


@wiki_app.command("show")
def wiki_show(
    user_email: str = typer.Option("local@research-pipeline", "--user"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Render the user's wiki as markdown."""
    from .wiki import render_wiki_markdown

    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (user_email,)
        ).fetchone()
        if not row:
            console.print(f"[red]no such user:[/red] {user_email}")
            raise typer.Exit(1)
        md = render_wiki_markdown(conn, user_id=row["id"])
    # Plain write — rich would try to parse markdown/markup in content and
    # crash on special chars. Also avoid Windows cp1252 errors by reconfiguring
    # stdout to UTF-8 with replacement fallback.
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.stdout.write(md)
    sys.stdout.write("\n")


@wiki_app.command("search")
def wiki_search(
    query: str = typer.Argument(...),
    user_email: str = typer.Option("local@research-pipeline", "--user"),
    top_k: int = typer.Option(8, "--top-k"),
    kind: str | None = typer.Option(None, "--kind"),
    as_of: str | None = typer.Option(
        None, "--as-of",
        help="ISO date (YYYY-MM-DD). Only show entries with t_ref <= date, "
             "or entries without a temporal anchor. Example: --as-of 2023-06-01.",
    ),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Cosine-search the user wiki. --as-of filters to entries anchored at
    or before the given date (Zep-style temporal query on Karpathy storage)."""
    from .wiki import search_wiki

    init_db(db_path)
    client = LLMClient()
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (user_email,)
        ).fetchone()
        if not row:
            console.print(f"[red]no such user:[/red] {user_email}")
            raise typer.Exit(1)
        hits = search_wiki(
            conn, user_id=row["id"], query=query, llm=client,
            top_k=top_k, kind=kind, as_of=as_of,
        )
    if not hits:
        msg = f"no hits for: {query}"
        if as_of:
            msg += f" (as-of {as_of})"
        console.print(f"[yellow]{msg}[/yellow]")
        return
    title = f"wiki search — '{query}'"
    if as_of:
        title += f" (as-of {as_of})"
    t = Table(title=title)
    t.add_column("score", justify="right")
    t.add_column("id", justify="right")
    t.add_column("kind")
    t.add_column("t_ref")
    t.add_column("content", overflow="fold")
    for entry, score in hits:
        t.add_row(
            f"{score:.3f}",
            str(entry.id),
            entry.kind,
            entry.t_ref or "—",
            entry.content[:180],
        )
    console.print(t)


@wiki_app.command("seed")
def wiki_seed(
    project_id: int = typer.Argument(...),
    top_k: int = typer.Option(6, "--top-k"),
    db_path: Path = typer.Option(Path("research_pipeline.db"), "--db"),
) -> None:
    """Seed a project's blackboard with top-K wiki entries relevant to its goal."""
    from .wiki import seed_project_from_wiki

    init_db(db_path)
    client = LLMClient()
    with connect(db_path) as conn:
        n = seed_project_from_wiki(
            conn, project_id=project_id, llm=client, top_k=top_k
        )
    console.print(f"[green]seeded {n}[/green] wiki entries into project {project_id}")


if __name__ == "__main__":
    app()

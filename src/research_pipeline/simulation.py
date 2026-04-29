"""OASIS wrapper. Imports OASIS/CAMEL lazily so the package stays importable
without the heavy `sim` extras installed.

A simulation takes a project (goal + archetype subset) and steps OASIS for N
turns, mirroring OASIS's Twitter `post` table into our `channel_posts` table.
"""
from __future__ import annotations

import csv
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .adapter import LLMClient
from .archetypes import Archetype, by_id
from .db import connect, init_db
from .kpi import RUBRIC_METRICS, judge_project, snapshot_counters
from .projects import get_project, get_project_agents, set_project_status
from .blackboard import KIND_EVIDENCE
from .dedup import cosine
from .lifecycle import hypotheses_in_play, resolve_hypothesis_refs
from .mentions import link_mentions
from .per_agent_rubric import judge_agents
from .promote import promote_project_posts
from .report import generate_report
from .retrieval import ScoredEntry, search_blackboard

POST_DUP_THRESHOLD = 0.92
MAX_DUP_RETRIES = 1


@dataclass
class SimulationConfig:
    project_id: int
    turn_cap: int = 3
    token_budget: int = 20_000
    temperature: float = 0.4
    max_tokens: int = 2048
    reddit_round_every: int = 0  # 0=off; N=run one Reddit thread every N Twitter turns
    auto_promote_to_wiki: bool = True
    auto_promote_rubric_floor: float = 3.0
    per_agent_rubric: bool = True  # judge each agent on 6 dims at end-of-run


@dataclass
class SimulationResult:
    project_id: int
    turns_run: int
    posts_total: int
    oasis_db_path: Path
    report_path: Path | None = None


async def run_simulation(
    sim_cfg: SimulationConfig,
    *,
    db_path: Path,
    work_dir: Path,
    llm: LLMClient | None = None,
) -> SimulationResult:
    # Lazy imports so `import research_pipeline.simulation` doesn't pull torch.
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    import oasis
    from oasis import (
        ActionType,
        LLMAction,
        generate_twitter_agent_graph,
    )

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    # Ensure any schema migrations (e.g. embedding_json, echo_count) are applied
    # for users on an older DB from before these columns existed.
    init_db(db_path)

    llm = llm or LLMClient()
    role = llm.role_info("agent_bulk")

    with connect(db_path) as conn:
        project = get_project(conn, sim_cfg.project_id)
        project_agents = get_project_agents(conn, sim_cfg.project_id)
    if not project_agents:
        raise ValueError(f"Project {sim_cfg.project_id} has no agents")

    archetypes = [by_id(pa.archetype) for pa in project_agents]
    work_dir.mkdir(parents=True, exist_ok=True)
    profile_csv = work_dir / f"project_{sim_cfg.project_id}_profiles.csv"
    _write_profile_csv(profile_csv, archetypes, project_goal=project.goal)

    oasis_db = work_dir / f"project_{sim_cfg.project_id}_oasis.db"
    if oasis_db.exists():
        oasis_db.unlink()
    os.environ["OASIS_DB_PATH"] = str(oasis_db.resolve())

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=role.model,
        api_key=role.api_key,
        url=role.base_url,
        model_config_dict={
            "temperature": sim_cfg.temperature,
            "max_tokens": sim_cfg.max_tokens,
        },
    )
    # CAMEL's default per-agent context window is tiny (512 tokens); raise it
    # so agents see the full environment observation OASIS hands them.
    os.environ.setdefault("CAMEL_MEMORY_MAX_TOKENS", "8192")

    agent_graph = await generate_twitter_agent_graph(
        profile_path=str(profile_csv),
        model=model,
        available_actions=ActionType.get_default_twitter_actions(),
    )

    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.TWITTER,
        database_path=str(oasis_db),
    )
    await env.reset()

    with connect(db_path) as conn:
        set_project_status(conn, sim_cfg.project_id, "running")

    last_post_id = 0
    try:
        # Turn 0: each archetype posts an opening claim so the feed has content
        # for the LLM-driven turns to react to.
        with connect(db_path) as conn:
            seed_evidence = _retrieve_evidence(
                conn, sim_cfg.project_id, project.goal, llm, top_k=6
            )
        await _seed_posts(
            env,
            llm=llm,
            project_goal=project.goal,
            archetypes=archetypes,
            evidence_pool=seed_evidence,
        )
        last_post_id = _sync_new_posts(
            oasis_db_path=oasis_db,
            our_db_path=db_path,
            project_id=sim_cfg.project_id,
            project_agent_ids=[pa.id for pa in project_agents],
            turn=0,
            since_post_id=last_post_id,
        )
        with connect(db_path) as conn:
            link_mentions(conn, project_id=sim_cfg.project_id, turn=0)
            promote_project_posts(conn, project_id=sim_cfg.project_id, turn=0)

        for turn in range(1, sim_cfg.turn_cap + 1):
            with connect(db_path) as conn:
                kpi_feedback = _recent_kpi_scores(conn, sim_cfg.project_id)
                recent_posts = _recent_posts_context(
                    conn, sim_cfg.project_id, limit=12
                )
                evidence_pool = _retrieve_evidence(
                    conn, sim_cfg.project_id, project.goal, llm, top_k=6
                )
                hyps_in_play = hypotheses_in_play(
                    conn, project_id=sim_cfg.project_id, limit=6
                )
                # Judge at the start of turns > 1 so feedback reflects the
                # *previous* turn's output.
                if turn > 1:
                    try:
                        fresh = judge_project(
                            conn,
                            project_id=sim_cfg.project_id,
                            goal=project.goal,
                            llm=llm,
                            turn=turn - 1,
                        )
                        kpi_feedback = {
                            m: float(fresh.get(m, kpi_feedback.get(m, 0.0)))
                            for m in RUBRIC_METRICS
                        }
                    except Exception as e:
                        print(f"[sim] mid-run judge skipped: {e}")

            await _run_prompted_turn(
                env,
                llm=llm,
                project_goal=project.goal,
                archetypes=archetypes,
                turn=turn,
                kpi_feedback=kpi_feedback,
                recent_posts=recent_posts,
                evidence_pool=evidence_pool,
                hypotheses=hyps_in_play,
                agent_configs=project_agents,
            )
            last_post_id = _sync_new_posts(
                oasis_db_path=oasis_db,
                our_db_path=db_path,
                project_id=sim_cfg.project_id,
                project_agent_ids=[pa.id for pa in project_agents],
                turn=turn,
                since_post_id=last_post_id,
            )
            with connect(db_path) as conn:
                link_mentions(conn, project_id=sim_cfg.project_id, turn=turn)
                promote_project_posts(conn, project_id=sim_cfg.project_id, turn=turn, llm=llm)
                resolve_hypothesis_refs(conn, project_id=sim_cfg.project_id, turn=turn)

            # Optional Reddit round at a configurable cadence.
            if (
                sim_cfg.reddit_round_every > 0
                and turn % sim_cfg.reddit_round_every == 0
            ):
                with connect(db_path) as conn:
                    reddit_evidence = _retrieve_evidence(
                        conn, sim_cfg.project_id, project.goal, llm, top_k=6
                    )
                    await _run_reddit_round(
                        conn,
                        project_id=sim_cfg.project_id,
                        llm=llm,
                        project_goal=project.goal,
                        archetypes=archetypes,
                        evidence_pool=reddit_evidence,
                        turn=turn,
                    )
                    link_mentions(conn, project_id=sim_cfg.project_id, turn=turn)
                    promote_project_posts(
                        conn, project_id=sim_cfg.project_id, turn=turn, llm=llm,
                    )
                    resolve_hypothesis_refs(
                        conn, project_id=sim_cfg.project_id, turn=turn,
                    )

            with connect(db_path) as conn:
                snapshot_counters(conn, project_id=sim_cfg.project_id, turn=turn)
    finally:
        await env.close()
        with connect(db_path) as conn:
            try:
                judge_project(
                    conn,
                    project_id=sim_cfg.project_id,
                    goal=project.goal,
                    llm=llm,
                    turn=sim_cfg.turn_cap,
                )
            except Exception as e:  # Rubric is best-effort; never fail the run.
                print(f"[sim] judge_project skipped: {e.__class__.__name__}: {e}")

            if sim_cfg.per_agent_rubric:
                try:
                    rows = judge_agents(
                        conn,
                        project_id=sim_cfg.project_id,
                        goal=project.goal,
                        llm=llm,
                        turn=sim_cfg.turn_cap,
                    )
                    if rows:
                        print(f"[sim] per-agent rubric scored {len(rows)} agents")
                except Exception as e:
                    print(f"[sim] per-agent rubric skipped: {e}")

        # Final synthesis: Writer drafts, Reviewer grades, both land on
        # blackboard + projects/{id}/report.md. Best-effort.
        report_path: Path | None = None
        try:
            with connect(db_path) as conn:
                result = await generate_report(
                    conn,
                    project_id=sim_cfg.project_id,
                    llm=llm,
                    work_dir=work_dir.parent / "projects",
                )
            report_path = result.report_path
            print(f"[sim] report written: {report_path}")
        except Exception as e:
            print(f"[sim] report skipped: {e.__class__.__name__}: {e}")

        if sim_cfg.auto_promote_to_wiki:
            try:
                from .wiki import promote_project_to_wiki

                with connect(db_path) as conn:
                    rubric = _final_rubric(conn, sim_cfg.project_id)
                    if rubric and all(v >= sim_cfg.auto_promote_rubric_floor for v in rubric.values()):
                        counts = promote_project_to_wiki(
                            conn, project_id=sim_cfg.project_id, top_k_per_kind=3,
                        )
                        if counts:
                            total = sum(counts.values())
                            print(f"[sim] auto-promoted {total} entries to wiki: {counts}")
                    else:
                        print(f"[sim] wiki auto-promote skipped (rubric: {rubric})")
            except Exception as e:
                print(f"[sim] wiki auto-promote error: {e}")

        with connect(db_path) as conn:
            set_project_status(conn, sim_cfg.project_id, "completed")

    return SimulationResult(
        project_id=sim_cfg.project_id,
        turns_run=sim_cfg.turn_cap,
        posts_total=last_post_id,
        oasis_db_path=oasis_db,
        report_path=report_path,
    )


def _recent_kpi_scores(conn, project_id: int) -> dict[str, float]:
    """Last rubric scores for the project (agent_id IS NULL), keyed by metric."""
    rows = conn.execute(
        """
        SELECT metric, value FROM kpi_scores
        WHERE project_id = ? AND agent_id IS NULL AND metric IN (?, ?, ?, ?)
        AND turn = (
            SELECT MAX(turn) FROM kpi_scores
            WHERE project_id = ? AND agent_id IS NULL AND metric = kpi_scores.metric
        )
        """,
        (project_id, *RUBRIC_METRICS, project_id),
    ).fetchall()
    return {r["metric"]: float(r["value"]) for r in rows}


def _recent_posts_context(conn, project_id: int, *, limit: int) -> list[tuple[str, str]]:
    """Return the last N posts as (who, content) tuples, oldest first."""
    rows = list(
        conn.execute(
            "SELECT turn, agent_id, content FROM channel_posts "
            "WHERE project_id = ? ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        )
    )
    rows.reverse()
    out = []
    for r in rows:
        who = f"agent_{r['agent_id']}" if r["agent_id"] is not None else "PI"
        out.append((f"t{r['turn']} {who}", (r["content"] or "").replace("\n", " ")))
    return out


def _final_rubric(conn, project_id: int) -> dict[str, float] | None:
    """Latest rubric snapshot for the project, or None if nothing was scored."""
    placeholders = ",".join("?" * len(RUBRIC_METRICS))
    rows = conn.execute(
        f"""
        SELECT metric, value FROM kpi_scores
        WHERE project_id = ? AND agent_id IS NULL AND metric IN ({placeholders})
        AND turn = (
            SELECT MAX(turn) FROM kpi_scores
            WHERE project_id = ? AND agent_id IS NULL AND metric = kpi_scores.metric
        )
        """,
        (project_id, *RUBRIC_METRICS, project_id),
    ).fetchall()
    return {r["metric"]: float(r["value"]) for r in rows} if rows else None


def _format_kpi_feedback(kpi: dict[str, float]) -> str:
    if not kpi:
        return "KPI: no prior scores yet."
    parts = [f"{m}={kpi.get(m, 0.0):.1f}" for m in RUBRIC_METRICS]
    return "Last-turn rubric (1-5): " + ", ".join(parts)


def _retrieve_evidence(
    conn, project_id: int, goal: str, llm: LLMClient, top_k: int
) -> list[ScoredEntry]:
    """Pull the top-k most goal-relevant evidence entries. Safe: returns []
    on any failure (stale DB, no embeddings, adapter error)."""
    try:
        return search_blackboard(
            conn,
            project_id=project_id,
            query=goal,
            llm=llm,
            top_k=top_k,
            kind=KIND_EVIDENCE,
        )
    except Exception as e:
        print(f"[sim] evidence retrieval skipped: {e}")
        return []


async def _generate_unique_post(
    llm: LLMClient,
    *,
    system_msg: str,
    user_msg: str,
    avoid_embeddings: list[list[float]],
    max_retries: int = MAX_DUP_RETRIES,
    threshold: float = POST_DUP_THRESHOLD,
    base_temperature: float = 0.75,
    max_tokens: int = 300,
) -> tuple[str | None, list[float] | None]:
    """Generate a post via the adapter; if the output is near-duplicate of any
    vector in `avoid_embeddings`, retry once with a stronger anti-duplication
    nudge and a higher temperature. Returns (content, embedding) or (None, None)
    if the generation failed or every attempt duplicated.

    `base_temperature` and `max_tokens` are per-agent knobs set by the
    optimization loop — defaults match the phase-1 values.
    """
    attempt_user = user_msg
    for attempt in range(max_retries + 1):
        try:
            resp = await llm.achat(
                "agent_bulk",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": attempt_user},
                ],
                max_tokens=max_tokens,
                temperature=min(1.0, base_temperature + 0.15 * attempt),
            )
        except Exception as e:
            print(f"[sim] generation failed: {e}")
            return None, None

        content = (resp.choices[0].message.content or "").strip()
        if not content:
            return None, None

        if not avoid_embeddings:
            return content, None

        try:
            cand_emb = llm.embed("embedding", content)[0]
        except Exception:
            return content, None

        max_sim = max(cosine(cand_emb, e) for e in avoid_embeddings)
        if max_sim < threshold:
            return content, cand_emb

        attempt_user = (
            user_msg
            + f"\n\nIMPORTANT: your previous draft was {max_sim:.2f} cosine-"
            f"similar to a recent post. Do NOT repeat existing ideas. Take a "
            f"deliberately distinct angle — a different mechanism, a different "
            f"counterexample, or a different recommendation."
        )

    print(f"[sim] dropped duplicate post after {max_retries + 1} attempts (sim={max_sim:.2f})")
    return None, None


def _format_evidence_block(evidence: list[ScoredEntry]) -> str:
    if not evidence:
        return "(no ingested sources — speak from general knowledge and note claims as unverified)"
    lines: list[str] = []
    for s in evidence:
        tag = next(
            (r for r in s.entry.refs if isinstance(r, str) and r.startswith("source=")),
            "source=unknown",
        )
        snippet = (s.entry.content or "").strip().replace("\n", " ")[:260]
        lines.append(f"[src #{s.entry.id}] ({tag}) {snippet}")
    return "\n".join(lines)


def _format_hypotheses_block(hypotheses: list[tuple[int, str, str]]) -> str:
    if not hypotheses:
        return "(none yet — hypogen should propose some)"
    lines = []
    for hid, state, content in hypotheses:
        snippet = (content or "").replace("\n", " ").strip()[:200]
        lines.append(f"[hyp #{hid}] ({state}) {snippet}")
    return "\n".join(lines)


async def _run_prompted_turn(
    env,
    *,
    llm: LLMClient,
    project_goal: str,
    archetypes: list[Archetype],
    turn: int,
    kpi_feedback: dict[str, float],
    recent_posts: list[tuple[str, str]],
    evidence_pool: list[ScoredEntry] | None = None,
    hypotheses: list[tuple[int, str, str]] | None = None,
    agent_configs: list | None = None,
) -> None:
    """Each agent posts once per turn, content generated through our adapter.

    Prompt carries: role reinforcement (from archetype), last-turn KPI scores
    (AAR-style feedback loop), the recent channel context, and retrieved
    evidence from the blackboard (so citations are grounded, not fabricated).
    """
    from oasis import ActionType, ManualAction

    if recent_posts:
        feed_block = "\n".join(f"- [{who}] {msg}" for who, msg in recent_posts)
    else:
        feed_block = "(no prior posts)"

    kpi_line = _format_kpi_feedback(kpi_feedback)
    evidence_block = _format_evidence_block(evidence_pool or [])
    hyps_block = _format_hypotheses_block(hypotheses or [])

    # Pre-embed recent posts so we can reject near-duplicate regenerations.
    recent_texts = [msg for _, msg in recent_posts]
    avoid_embeddings: list[list[float]] = []
    if recent_texts:
        try:
            avoid_embeddings = list(llm.embed("embedding", recent_texts))
        except Exception as e:
            print(f"[sim] recent-post embeddings skipped: {e}")

    actions: dict = {}
    agents_ordered = [agent for _, agent in env.agent_graph.get_agents()]
    configs_iter = list(agent_configs or [None] * len(archetypes))
    for agent, arch, cfg in zip(agents_ordered, archetypes, configs_iter):
        temp = float(getattr(cfg, "temperature", 0.75)) if cfg else 0.75
        max_tok = int(getattr(cfg, "max_tokens", 300)) if cfg else 300
        specialty = getattr(cfg, "specialty_focus", None) if cfg else None
        specialty_block = (
            f"\nSpecialty focus (stay within this when relevant): {specialty}"
            if specialty else ""
        )
        system_msg = (
            f"{arch.system_prompt}{specialty_block}\n\n"
            f"Reinforcement: you are the {arch.name}. Stay strictly in this role. "
            f"Do NOT converge on agreement — your value to the team comes from your "
            f"distinct angle. Disagree when warranted.\n\n"
            f"Feedback: {kpi_line}\n"
            f"If novelty or rigor is low, your next post MUST push the discussion "
            f"forward with something substantive and specific.\n\n"
            f"Citation policy: when you cite evidence, use the bracketed "
            f"source ids from the SOURCES block below (e.g. [src #42]). Do not "
            f"invent citations that aren't in SOURCES."
        )
        user_msg = (
            f"RESEARCH GOAL: {project_goal}\n\n"
            f"TURN: {turn}\n\n"
            f"SOURCES (ingested evidence you can cite by [src #N]):\n{evidence_block}\n\n"
            f"HYPOTHESES IN PLAY (cite as [hyp #N] when supporting or "
            f"refuting a specific one):\n{hyps_block}\n\n"
            f"RECENT CHANNEL POSTS (most recent last):\n{feed_block}\n\n"
            f"Your task: post ONE tweet (<=280 chars) that advances the research "
            f"from your role's perspective. Cite supporting sources with "
            f"[src #N]. If you reach a verdict on a specific hypothesis, name "
            f"it with [hyp #N] and state explicitly whether your analysis "
            f"supports, refutes, or is neutral. No hashtags, no generic agreement."
        )
        content, cand_emb = await _generate_unique_post(
            llm,
            system_msg=system_msg,
            user_msg=user_msg,
            avoid_embeddings=avoid_embeddings,
            base_temperature=temp,
            max_tokens=max_tok,
        )
        if content is None:
            continue
        actions[agent] = ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": content[:280]},
        )
        # Append this turn's accepted post to the avoid-set so subsequent
        # agents in the same turn don't parrot it.
        if cand_emb is not None:
            avoid_embeddings.append(cand_emb)
        elif content:
            try:
                avoid_embeddings.append(llm.embed("embedding", content)[0])
            except Exception:
                pass
    if actions:
        await env.step(actions)


REDDIT_ROOT_SYSTEM_SUFFIX = """

You are posting the ROOT of a Reddit-style discussion thread on this topic.
Output ONLY JSON of the shape {"title": "...", "body": "..."}:
- title: 40-120 chars, a specific discussion-worthy claim (no clickbait, no hashtags)
- body: 400-1400 chars of substantive argument in your archetype's voice
- Cite ingested sources with [src #N] where they support your points
- End the body with ONE open question for the community
"""

REDDIT_REPLY_SYSTEM_SUFFIX = """

You are writing a THREADED REDDIT REPLY to the OP below.
Output plain text only (no JSON, no headers).
- 300-800 chars
- Respond from your archetype's distinct angle (critic challenges, hypogen extends, etc.)
- Cite [src #N] from SOURCES where supportive
- Do NOT restate the OP's position; advance or challenge it
"""


def _pick_reddit_topic(conn, project_id: int, fallback: str) -> str:
    row = conn.execute(
        "SELECT content FROM blackboard_entries "
        "WHERE project_id = ? AND kind = 'hypothesis' "
        "ORDER BY id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row and row["content"]:
        return (row["content"] or "")[:400]
    return fallback


def _agent_id_for_archetype(conn, project_id: int, archetype_id: str):
    row = conn.execute(
        "SELECT id FROM agents WHERE project_id = ? AND archetype = ? LIMIT 1",
        (project_id, archetype_id),
    ).fetchone()
    return row["id"] if row else None


async def _generate_reddit_root(
    llm: LLMClient,
    *,
    archetype: Archetype,
    topic: str,
    project_goal: str,
    evidence_pool: list[ScoredEntry],
) -> tuple[str | None, str | None]:
    import json as _json

    system = archetype.system_prompt + REDDIT_ROOT_SYSTEM_SUFFIX
    user = (
        f"GOAL: {project_goal}\n\n"
        f"TOPIC TO OPEN:\n{topic}\n\n"
        f"SOURCES (cite by [src #N]):\n{_format_evidence_block(evidence_pool)}\n\n"
        "Produce the thread post as strict JSON."
    )
    try:
        resp = await llm.achat(
            "agent_heavy",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=2048,
            temperature=0.55,
        )
    except Exception as e:
        print(f"[sim] reddit root generation failed: {e}")
        return None, None

    raw = resp.choices[0].message.content or "{}"
    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError:
        return None, None

    title = (data.get("title") or "").strip()[:200]
    body = (data.get("body") or "").strip()
    if not body:
        return None, None
    return body, (title or "(untitled)")


async def _generate_reddit_reply(
    llm: LLMClient,
    *,
    archetype: Archetype,
    root_title: str,
    root_body: str,
    project_goal: str,
    evidence_pool: list[ScoredEntry],
) -> str | None:
    system = archetype.system_prompt + REDDIT_REPLY_SYSTEM_SUFFIX
    user = (
        f"GOAL: {project_goal}\n\n"
        f"SOURCES (cite by [src #N]):\n{_format_evidence_block(evidence_pool)}\n\n"
        f"OP thread:\nTITLE: {root_title}\nBODY: {root_body}\n\n"
        "Write your threaded reply now."
    )
    try:
        resp = await llm.achat(
            "agent_heavy",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=1024,
            temperature=0.65,
        )
    except Exception as e:
        print(f"[sim] reddit reply generation failed: {e}")
        return None
    content = (resp.choices[0].message.content or "").strip()
    return content or None


async def _run_reddit_round(
    conn,
    *,
    project_id: int,
    llm: LLMClient,
    project_goal: str,
    archetypes: list[Archetype],
    evidence_pool: list[ScoredEntry],
    turn: int,
    topic: str | None = None,
) -> int:
    """Produce one Reddit thread: a root post by hypogen (or first archetype)
    plus one threaded reply per other archetype. Posts are written directly to
    channel_posts with channel='reddit' (no OASIS roundtrip). Returns the
    root's channel_posts.id, or 0 if generation failed.
    """
    if not archetypes:
        return 0

    chosen_topic = topic or _pick_reddit_topic(conn, project_id, fallback=project_goal)
    root_arch = next(
        (a for a in archetypes if a.id == "hypogen"), archetypes[0]
    )
    reply_arches = [a for a in archetypes if a.id != root_arch.id]

    body, title = await _generate_reddit_root(
        llm,
        archetype=root_arch,
        topic=chosen_topic,
        project_goal=project_goal,
        evidence_pool=evidence_pool,
    )
    if not body:
        print("[sim] reddit round skipped: no root body produced")
        return 0

    root_agent_id = _agent_id_for_archetype(conn, project_id, root_arch.id)
    cur = conn.execute(
        "INSERT INTO channel_posts "
        "(project_id, channel, title, agent_id, content, turn) "
        "VALUES (?, 'reddit', ?, ?, ?, ?)",
        (project_id, title, root_agent_id, body, turn),
    )
    root_id = cur.lastrowid
    conn.commit()

    for arch in reply_arches:
        reply = await _generate_reddit_reply(
            llm,
            archetype=arch,
            root_title=title or "",
            root_body=body,
            project_goal=project_goal,
            evidence_pool=evidence_pool,
        )
        if not reply:
            continue
        agent_id = _agent_id_for_archetype(conn, project_id, arch.id)
        conn.execute(
            "INSERT INTO channel_posts "
            "(project_id, channel, parent_id, agent_id, content, turn) "
            "VALUES (?, 'reddit', ?, ?, ?, ?)",
            (project_id, root_id, agent_id, reply, turn),
        )
    conn.commit()
    return root_id or 0


async def _seed_posts(
    env,
    *,
    llm: LLMClient,
    project_goal: str,
    archetypes: list[Archetype],
    evidence_pool: list[ScoredEntry] | None = None,
) -> None:
    """Turn-0 seed: each agent posts a distinct opening per its seed_angle.

    Divergent seeds matter — see the Anthropic AAR study (note in memory).
    If evidence has been ingested into the blackboard (kind=evidence), the
    seed prompt includes the top-k retrieved sources so agents can cite them.
    """
    from oasis import ActionType, ManualAction

    evidence_block = _format_evidence_block(evidence_pool or [])
    actions: dict = {}
    avoid_embeddings: list[list[float]] = []  # seeds dedup against each other
    agents_ordered = [agent for _, agent in env.agent_graph.get_agents()]
    for agent, arch in zip(agents_ordered, archetypes):
        prompt = (
            f"Research goal: {project_goal}\n\n"
            f"{arch.seed_angle}\n\n"
            f"SOURCES (cite by [src #N]):\n{evidence_block}\n\n"
            "Write one tweet (<=280 chars). No hashtags. No generic framing. "
            "Be specific and concrete. Disagree with consensus where warranted. "
            "When you cite evidence, use [src #N] from SOURCES — do not invent "
            "citations that aren't listed."
        )
        content, cand_emb = await _generate_unique_post(
            llm,
            system_msg=arch.system_prompt,
            user_msg=prompt,
            avoid_embeddings=avoid_embeddings,
        )
        if content is None:
            continue
        actions[agent] = ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": content[:280]},
        )
        if cand_emb is not None:
            avoid_embeddings.append(cand_emb)
    if actions:
        await env.step(actions)


def _write_profile_csv(
    path: Path, archetypes: list[Archetype], *, project_goal: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "",
                "user_id",
                "name",
                "username",
                "following_agentid_list",
                "previous_tweets",
                "user_char",
                "description",
            ]
        )
        for i, a in enumerate(archetypes):
            description = (
                f"RESEARCH GOAL: {project_goal}\n"
                f"ROLE: {a.name}. {a.system_prompt}"
            )
            w.writerow(
                [
                    i,
                    1001 + i,
                    a.id,
                    f"{a.id}_{i}",
                    "[]",
                    "[]",
                    a.name,
                    description,
                ]
            )


def _sync_new_posts(
    *,
    oasis_db_path: Path,
    our_db_path: Path,
    project_id: int,
    project_agent_ids: list[int],
    turn: int,
    since_post_id: int,
) -> int:
    """Mirror new rows from OASIS's `post` table into our channel_posts.

    OASIS post schema:
        post_id, user_id (0-indexed), original_post_id, content, quote_content,
        created_at, num_likes, ...

    For quote_posts, `content` is inherited from the parent and the new text
    lives in `quote_content`. We store the new text and set `parent_id` to the
    channel_posts.id that mirrors the OASIS original_post_id — resolved via
    the `oasis_post_map` table.
    """
    src = sqlite3.connect(oasis_db_path)
    dst = connect(our_db_path)
    try:
        rows = list(
            src.execute(
                "SELECT post_id, user_id, content, quote_content, original_post_id "
                "FROM post WHERE post_id > ? ORDER BY post_id",
                (since_post_id,),
            )
        )

        # Preload existing OASIS post_id -> our channel_posts.id map.
        parent_map: dict[int, int] = {
            r["oasis_post_id"]: r["channel_post_id"]
            for r in dst.execute(
                "SELECT oasis_post_id, channel_post_id FROM oasis_post_map "
                "WHERE project_id = ?",
                (project_id,),
            )
        }

        for post_id, user_id, content, quote_content, original_post_id in rows:
            is_quote = original_post_id is not None and bool(quote_content)
            display_content = quote_content if is_quote else content
            if user_id is not None and 0 <= int(user_id) < len(project_agent_ids):
                our_agent_id = project_agent_ids[int(user_id)]
            else:
                our_agent_id = None

            cur = dst.execute(
                "INSERT INTO channel_posts "
                "(project_id, channel, parent_id, agent_id, content, turn) "
                "VALUES (?, 'twitter', ?, ?, ?, ?)",
                (
                    project_id,
                    parent_map.get(original_post_id) if is_quote else None,
                    our_agent_id,
                    display_content,
                    turn,
                ),
            )
            our_post_id = cur.lastrowid
            parent_map[post_id] = our_post_id  # so later rows this turn can reference
            dst.execute(
                "INSERT OR REPLACE INTO oasis_post_map "
                "(project_id, oasis_post_id, channel_post_id) VALUES (?, ?, ?)",
                (project_id, post_id, our_post_id),
            )
        dst.commit()
        return rows[-1][0] if rows else since_post_id
    finally:
        src.close()
        dst.close()

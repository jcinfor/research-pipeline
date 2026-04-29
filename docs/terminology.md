# Terminology

*Canonical definitions for the research-pipeline vocabulary. If something here drifts from code or docs, the code/doc is wrong — file an issue against this file.*

## The Core Six

### simulation
One end-to-end invocation of `rp project run <id>` (or equivalently `run_simulation()`). Produces:
- One set of channel posts (Twitter, and Reddit if `reddit_round_every > 0`)
- Blackboard entries promoted from posts
- KPI + per-agent rubric rows
- One `report.md` (unless Writer/Reviewer failed)
- Optional auto-promote to wiki

Bounded by `SimulationConfig.turn_cap` and `token_budget`. One simulation = one OASIS `oasis_db` file.

### turn
One iteration of the main per-turn loop inside a simulation. During a turn:
- Every active agent produces exactly one Twitter post (via `_run_prompted_turn`)
- Post-turn bookkeeping: `link_mentions` → `promote_project_posts` → `resolve_hypothesis_refs` → `snapshot_counters`
- Optionally: one **Reddit round** if `turn % reddit_round_every == 0`

Turns count from 1. Turn 0 is reserved for the seed turn.

### seed turn (turn 0)
One-time pre-loop where each agent posts per its `seed_angle` — a distinct divergent opening tied to the archetype (underappreciated source / counterintuitive hypothesis / biggest blindspot / …). Distinct from turns 1..N because:
- It uses archetype-specific seed prompts instead of the feedback-driven prompt
- No prior context exists to react to
- No KPI feedback available yet

Called out explicitly when relevant; otherwise "turn 0" is the preferred reference.

### Reddit round
One threaded discussion embedded within a turn. Produces:
- One thread root (title + body, by hypogen or first archetype) via `ManualAction(CREATE_POST)` with `title` set
- One threaded reply per other archetype (`parent_id` = root's id)

All posts in a Reddit round share the same `turn` value as the Twitter turn they ride on. Fired at a cadence of `reddit_round_every` (0 = off).

### iteration
One cycle of the **optimization loop** (`rp project optimize`). Each iteration = {run a short simulation, score per-agent rubric, identify weakest agent, apply one config adjustment, persist trace}. Bounded by `--iterations N` and plateau detection.

A 3-iteration optimize literally runs 3 simulations back-to-back. Do not confuse with turns.

### sample
One call to the Writer during a **triangulation** pass (`rp project triangulate --runs N`). N samples → one triangulation verdict. No full simulation per sample — just the claim-synthesis call at elevated temperature.

## Naming Rules

1. **"run" must always be qualified.** Never bare. Use `simulation run`, `optimize run`, `triangulation run`, or (for CLI) name the actual command.
2. **"round" is reserved for Reddit rounds.** Don't use it as a synonym for turn in any doc, comment, or CLI string.
3. **"iteration" is reserved for the optimize loop.** Don't use it for turns.
4. **"phase" is reserved for project lifecycle** (phase 1, 2, 3, 4). Never a synonym for turn, iteration, or simulation.
5. **"step" is internal to OASIS** (`env.step()`). Surface to users only when discussing OASIS integration internals; otherwise use "turn".
6. **"sim" is an acceptable shorthand** for simulation in casual chat or code comments. In CLI help and docs, prefer the full word.

## How They Compose

Full optimize run with Reddit rounds:

```
optimize (iterations=5, turns_per=2, reddit_every=2)
├── iteration 1
│   ├── simulation
│   │   ├── turn 0 (seed turn)
│   │   ├── turn 1
│   │   │   └── Twitter posts (one per agent)
│   │   └── turn 2
│   │       ├── Twitter posts
│   │       └── Reddit round (root + replies, same turn=2)
│   ├── per-agent rubric scoring
│   └── config adjustment (e.g. raise_max_tokens on weakest)
├── iteration 2
│   └── (same shape, agents carry mutated config)
└── ...
```

Triangulation is flat:

```
rp project triangulate <id> --runs 3
├── sample 1 (Writer call at temperature=0.55)
├── sample 2
└── sample 3
    → mean pairwise cosine on claim titles
```

PGR scoring is not a loop — it's a one-shot pass per invocation:

```
rp project score <id>
├── pgr_cite    (one judge call per citation)
├── pgr_heldout (embed each claim × match top-K held-out chunks, judge matches)
└── pgr_adv     (Red Team + undermine judge per claim)
    → composite persisted as a single new turn bump in kpi_scores
```

## Examples Against Prior Confusion

| ambiguous phrasing | why it's wrong | preferred |
|---|---|---|
| "the run" | which run? | "the simulation" or "optimize iteration 3" |
| "the third round produced 9 posts" | sounds like Reddit, but if they mean the third turn, it's ambiguous | "turn 3 produced 9 posts" |
| "each iteration, agents post once" | iterations are optimization cycles, not turns | "each turn, agents post once" |
| "ran a simulation with 3 rounds" | rounds are Reddit-threaded; they probably meant turns | "ran a simulation of 3 turns" |

## Related Terms We Haven't Overloaded

These stay as they are — used clearly and consistently already:

- **archetype** — one of 8 agent role definitions in `archetypes.py` (scout, hypogen, critic, …)
- **agent** — one *instance* of an archetype, attached to a project in the `agents` table
- **proxy** — one PGR signal (`pgr_cite`, `pgr_heldout`, `pgr_adv`, `pgr_execution`)
- **artifact** — one of the five structured outputs (claims, hypotheses, experiments, decision, risks)
- **channel** — Twitter or Reddit (the social-media-style surface area)
- **blackboard** — the kind-typed durable evidence store (`blackboard_entries` table)
- **lifecycle** — the hypothesis state machine (`proposed → under_test → supported | refuted | verified`)
- **verdict** — one classification by the lifecycle classifier or a judge (support / refute / neutral)

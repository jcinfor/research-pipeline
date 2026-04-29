"""Performance Gap Recovered — proxy metrics for research quality.

Anthropic's AAR paper uses PGR (Performance Gap Recovered) as its single
ground-truth scalar: 0 = weak-model baseline, 1 = strong-model ceiling. For
general research where no such evaluator exists, we approximate with three
proxies:

    Proxy 1 — pgr_cite       : citation-trace verifiability (ship)
    Proxy 2 — pgr_heldout    : held-out evidence alignment (ship)
    Proxy 3 — pgr_adv        : adversarial Red Team undermining (scaffold)
    Composite = weighted mean

See docs/aar-comparison.md for the design rationale.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .adapter import LLMClient
from .blackboard import KIND_EVIDENCE
from .dedup import cosine
from .projects import get_project


# Regex extracting [src #N] refs and per-claim sections from claims.md.
_SRC_REF_RE = re.compile(r"\[\s*src\s*#(\d+)\s*\]", re.IGNORECASE)
_CLAIM_BLOCK_RE = re.compile(
    r"^##\s*(C\d+):.*?(?=^##\s*C\d+:|\Z)",
    re.MULTILINE | re.DOTALL,
)
_CLAIM_HEADER_RE = re.compile(r"^##\s*(C\d+):\s*(.*?)$", re.MULTILINE)


Verdict = Literal["support", "contradict", "neutral"]


@dataclass
class ClaimBlock:
    id: str          # "C1", "C2", ...
    title: str
    body: str
    src_refs: list[int]


@dataclass
class PGRCiteResult:
    supports: int = 0
    contradicts: int = 0
    neutrals: int = 0
    details: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.supports + self.contradicts + self.neutrals

    @property
    def score(self) -> float:
        n = self.total
        return (self.supports / n) if n > 0 else 0.0


@dataclass
class PGRSupportResult:
    """Companion to PGRCiteResult with partial-credit scoring.

    Where pgr_cite is strict (direct support only, binary), pgr_support uses
    a 0/1/2 scale:
        2 = chunk directly states or paraphrases the claim
        1 = chunk provides material from which the claim can be inferred
        0 = chunk is irrelevant, topically adjacent, or contradicts

    Pair them: high pgr_cite + high pgr_support => strong literal grounding.
    Low pgr_cite + high pgr_support => synthesis that's still inferentially
    grounded (the interesting research case). Low both => weakly supported.
    """
    direct: int = 0      # level=2
    partial: int = 0     # level=1
    off_topic: int = 0   # level=0
    details: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.direct + self.partial + self.off_topic

    @property
    def score(self) -> float:
        n = self.total
        if n == 0:
            return 0.0
        return (self.direct * 2 + self.partial * 1) / (2 * n)


@dataclass
class PGRHeldoutResult:
    supports: int = 0
    contradicts: int = 0
    neutrals: int = 0
    skipped_no_heldout: int = 0
    details: list[dict] = field(default_factory=list)

    @property
    def score(self) -> float:
        n = self.supports + self.contradicts + self.neutrals
        if n == 0:
            return 0.0
        # Net support fraction, clamped to [0, 1]
        raw = (self.supports - self.contradicts) / n
        return max(0.0, raw)


@dataclass
class PGRAdvResult:
    claims_tested: int = 0
    undermined: int = 0
    survived: int = 0
    details: list[dict] = field(default_factory=list)

    @property
    def score(self) -> float:
        if self.claims_tested == 0:
            return 0.0
        return self.survived / self.claims_tested


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------


def parse_claims_md(path: Path) -> list[ClaimBlock]:
    """Parse the claims.md artifact into structured ClaimBlock records."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    blocks: list[ClaimBlock] = []
    for m in _CLAIM_BLOCK_RE.finditer(text):
        body = m.group(0)
        header = _CLAIM_HEADER_RE.search(body)
        if not header:
            continue
        claim_id = header.group(1)
        title = header.group(2).strip()
        refs = sorted({int(r.group(1)) for r in _SRC_REF_RE.finditer(body)})
        blocks.append(ClaimBlock(id=claim_id, title=title, body=body.strip(), src_refs=refs))
    return blocks


# ---------------------------------------------------------------------------
# Shared judge wrapper
# ---------------------------------------------------------------------------


_SUPPORT_JUDGE_SYSTEM = """You are a strict verification judge. Read a CLAIM
and a piece of EVIDENCE. Answer whether the evidence supports the claim,
contradicts it, or is neutral on it.

Return ONLY a JSON object: {"verdict": "support" | "contradict" | "neutral", "reason": "..."}
"""


def _judge_support(llm: LLMClient, *, claim: str, evidence: str) -> tuple[Verdict, str]:
    try:
        resp = llm.chat(
            "judge",
            messages=[
                {"role": "system", "content": _SUPPORT_JUDGE_SYSTEM},
                {"role": "user", "content": f"CLAIM:\n{claim}\n\nEVIDENCE:\n{evidence}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=256,
            temperature=0,
        )
    except Exception as e:
        return "neutral", f"judge error: {e}"
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "neutral", "non-json response"
    verdict = data.get("verdict", "").lower().strip()
    if verdict not in ("support", "contradict", "neutral"):
        verdict = "neutral"
    reason = str(data.get("reason", ""))[:400]
    return verdict, reason  # type: ignore[return-value]


_SUPPORT_LEVEL_JUDGE_SYSTEM = """You are a verification judge. Read a CLAIM
and a piece of EVIDENCE. Score HOW the evidence relates to the claim on a
0/1/2 scale:

  2 = evidence directly states or closely paraphrases the claim
  1 = evidence provides material from which the claim can be reasonably
      inferred (supporting building block, even if not literal)
  0 = evidence is irrelevant, merely topically adjacent, or contradicts
      the claim

Use level=1 generously. If the chunk supplies a relevant fact, mechanism,
or observation that a reasonable reader could use to build the claim,
that's a 1 — even if the claim is a higher-level synthesis.

Return ONLY a JSON object: {"level": 0 | 1 | 2, "reason": "..."}
"""


def _judge_support_level(llm: LLMClient, *, claim: str, evidence: str) -> tuple[int, str]:
    try:
        resp = llm.chat(
            "judge",
            messages=[
                {"role": "system", "content": _SUPPORT_LEVEL_JUDGE_SYSTEM},
                {"role": "user", "content": f"CLAIM:\n{claim}\n\nEVIDENCE:\n{evidence}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=256,
            temperature=0,
        )
    except Exception as e:
        return 0, f"judge error: {e}"
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return 0, "non-json response"
    level = data.get("level")
    if not isinstance(level, (int, float)) or int(level) not in (0, 1, 2):
        return 0, f"invalid level: {level!r}"
    reason = str(data.get("reason", ""))[:400]
    return int(level), reason


# ---------------------------------------------------------------------------
# Proxy 1 — Citation-trace verifiability
# ---------------------------------------------------------------------------


def pgr_cite(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient,
    claims_md_path: Path,
) -> PGRCiteResult:
    """For every [src #N] citation in claims.md, check whether the cited
    blackboard entry actually supports the claim containing it."""
    result = PGRCiteResult()
    claims = parse_claims_md(claims_md_path)
    if not claims:
        return result

    # Preload the cited evidence entries in one pass.
    all_cited_ids = sorted({rid for c in claims for rid in c.src_refs})
    if not all_cited_ids:
        return result
    placeholders = ",".join("?" * len(all_cited_ids))
    rows = conn.execute(
        f"SELECT id, content FROM blackboard_entries WHERE id IN ({placeholders})",
        all_cited_ids,
    ).fetchall()
    evidence_by_id = {r["id"]: (r["content"] or "") for r in rows}

    for claim in claims:
        for src_id in claim.src_refs:
            chunk = evidence_by_id.get(src_id)
            if not chunk:
                result.details.append({
                    "claim_id": claim.id, "src_id": src_id,
                    "verdict": "missing_source", "reason": "src id not found",
                })
                continue
            verdict, reason = _judge_support(
                llm, claim=f"{claim.title}\n{claim.body}", evidence=chunk,
            )
            result.details.append({
                "claim_id": claim.id, "src_id": src_id,
                "verdict": verdict, "reason": reason,
            })
            if verdict == "support":
                result.supports += 1
            elif verdict == "contradict":
                result.contradicts += 1
            else:
                result.neutrals += 1
    return result


# ---------------------------------------------------------------------------
# Proxy 1b — Partial-credit citation-trace (pgr_support)
# ---------------------------------------------------------------------------


def pgr_support(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient,
    claims_md_path: Path,
) -> PGRSupportResult:
    """Partial-credit version of pgr_cite. Uses the same {claim, src_id}
    pairs but scores each on a 0/1/2 scale. Paired with pgr_cite it
    distinguishes 'claim is restatement' (both high) from 'claim is
    synthesis that's still grounded' (pgr_cite low, pgr_support high)."""
    result = PGRSupportResult()
    claims = parse_claims_md(claims_md_path)
    if not claims:
        return result

    all_cited_ids = sorted({rid for c in claims for rid in c.src_refs})
    if not all_cited_ids:
        return result
    placeholders = ",".join("?" * len(all_cited_ids))
    rows = conn.execute(
        f"SELECT id, content FROM blackboard_entries WHERE id IN ({placeholders})",
        all_cited_ids,
    ).fetchall()
    evidence_by_id = {r["id"]: (r["content"] or "") for r in rows}

    for claim in claims:
        for src_id in claim.src_refs:
            chunk = evidence_by_id.get(src_id)
            if not chunk:
                result.off_topic += 1
                result.details.append({
                    "claim_id": claim.id, "src_id": src_id,
                    "level": 0, "reason": "src id not found",
                })
                continue
            level, reason = _judge_support_level(
                llm,
                claim=f"{claim.title}\n{claim.body}",
                evidence=chunk,
            )
            result.details.append({
                "claim_id": claim.id, "src_id": src_id,
                "level": level, "reason": reason,
            })
            if level == 2:
                result.direct += 1
            elif level == 1:
                result.partial += 1
            else:
                result.off_topic += 1
    return result


# ---------------------------------------------------------------------------
# Proxy 2 — Held-out evidence alignment
# ---------------------------------------------------------------------------


def _load_heldout_chunks(
    conn: sqlite3.Connection, project_id: int
) -> list[tuple[int, str, list[float]]]:
    rows = conn.execute(
        "SELECT id, content, embedding_json FROM blackboard_entries "
        "WHERE project_id = ? AND kind = ? AND visibility = 'held_out' "
        "AND embedding_json IS NOT NULL",
        (project_id, KIND_EVIDENCE),
    ).fetchall()
    out: list[tuple[int, str, list[float]]] = []
    for r in rows:
        try:
            emb = json.loads(r["embedding_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        out.append((r["id"], r["content"] or "", emb))
    return out


def pgr_heldout(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient,
    claims_md_path: Path,
    per_claim_k: int = 3,
) -> PGRHeldoutResult:
    """For each claim, fetch the top-K relevant held-out chunks by cosine and
    judge whether they support or contradict the claim."""
    result = PGRHeldoutResult()
    claims = parse_claims_md(claims_md_path)
    if not claims:
        return result

    heldout = _load_heldout_chunks(conn, project_id)
    if not heldout:
        result.skipped_no_heldout = len(claims)
        return result

    for claim in claims:
        claim_text = f"{claim.title}\n{claim.body}"
        try:
            claim_vec = llm.embed("embedding", claim_text)[0]
        except Exception:
            continue
        # Rank held-out chunks by cosine to the claim
        scored = sorted(
            ((cid, content, cosine(claim_vec, emb)) for cid, content, emb in heldout),
            key=lambda x: -x[2],
        )[:per_claim_k]
        for cid, chunk, sim in scored:
            verdict, reason = _judge_support(llm, claim=claim_text, evidence=chunk)
            result.details.append({
                "claim_id": claim.id, "chunk_id": cid,
                "similarity": round(sim, 3),
                "verdict": verdict, "reason": reason,
            })
            if verdict == "support":
                result.supports += 1
            elif verdict == "contradict":
                result.contradicts += 1
            else:
                result.neutrals += 1
    return result


# ---------------------------------------------------------------------------
# Proxy 3 — Adversarial Red Team (scaffold — basic implementation)
# ---------------------------------------------------------------------------


_RED_TEAM_SYSTEM = """You are the Red Team reviewer. Your job is to find the
strongest specific counter-argument against the supplied CLAIM. Be adversarial
but grounded — no strawmanning, no rhetoric. If you cannot find a substantive
counter-argument, say so explicitly.

Return JSON: {"counter_argument": "...", "strength": "strong"|"moderate"|"weak"|"none"}
"""

_UNDERMINE_JUDGE_SYSTEM = """You are a neutral referee. Given a CLAIM and a
COUNTER-ARGUMENT, decide whether the counter-argument meaningfully undermines
the claim. Be strict — rhetorical flourish without substance does NOT
undermine.

Return JSON: {"verdict": "undermined"|"survived", "reason": "..."}
"""


def _red_team_role(llm: LLMClient) -> str:
    """Prefer a dedicated `red_team` role if the user has configured one
    (for cross-model adversarial pressure); fall back to `judge`."""
    try:
        llm.role_info("red_team")
        return "red_team"
    except KeyError:
        return "judge"


def pgr_adversarial(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient,
    claims_md_path: Path,
) -> PGRAdvResult:
    """For each claim, ask the Red Team to produce the strongest counter-
    argument, then ask a separate judge pass to decide whether that counter-
    argument meaningfully undermines the claim.

    For genuine adversarial pressure, configure a `red_team` role in
    models.toml pointing at a different model family than `judge`. Without
    one, falls back to `judge` — usable but shares blindspots with the
    original agents.
    """
    result = PGRAdvResult()
    claims = parse_claims_md(claims_md_path)
    if not claims:
        return result

    rt_role = _red_team_role(llm)
    for claim in claims:
        result.claims_tested += 1
        claim_text = f"{claim.title}\n{claim.body}"
        # Red Team step — uses red_team role if configured, else falls back to judge
        try:
            rt_resp = llm.chat(
                rt_role,
                messages=[
                    {"role": "system", "content": _RED_TEAM_SYSTEM},
                    {"role": "user", "content": f"CLAIM:\n{claim_text}"},
                ],
                response_format={"type": "json_object"},
                max_tokens=512,
                temperature=0.4,
            )
            rt_data = json.loads(rt_resp.choices[0].message.content or "{}")
        except Exception as e:
            result.details.append({
                "claim_id": claim.id, "phase": "red_team", "error": str(e),
            })
            result.survived += 1  # benefit of the doubt on scaffold
            continue
        counter = (rt_data.get("counter_argument") or "").strip()
        strength = (rt_data.get("strength") or "").lower()
        if not counter or strength == "none":
            result.survived += 1
            result.details.append({
                "claim_id": claim.id, "verdict": "survived",
                "counter": counter[:200], "strength": strength,
            })
            continue
        # Undermine judge
        try:
            jr = llm.chat(
                "judge",
                messages=[
                    {"role": "system", "content": _UNDERMINE_JUDGE_SYSTEM},
                    {"role": "user", "content": f"CLAIM:\n{claim_text}\n\nCOUNTER-ARGUMENT:\n{counter}"},
                ],
                response_format={"type": "json_object"},
                max_tokens=256,
                temperature=0,
            )
            jdata = json.loads(jr.choices[0].message.content or "{}")
        except Exception as e:
            result.details.append({
                "claim_id": claim.id, "phase": "undermine_judge", "error": str(e),
            })
            result.survived += 1
            continue
        verdict = (jdata.get("verdict") or "").lower()
        if verdict == "undermined":
            result.undermined += 1
        else:
            result.survived += 1
        result.details.append({
            "claim_id": claim.id,
            "counter": counter[:300],
            "strength": strength,
            "verdict": verdict or "survived",
            "reason": str(jdata.get("reason", ""))[:300],
        })
    return result


# ---------------------------------------------------------------------------
# Composite + persistence
# ---------------------------------------------------------------------------


@dataclass
class PGRComposite:
    cite: float
    heldout: float
    adv: float
    composite: float
    detail: dict


def compute_composite(
    cite: PGRCiteResult, heldout: PGRHeldoutResult, adv: PGRAdvResult,
    *, weights: tuple[float, float, float] = (0.4, 0.3, 0.3),
    enabled: tuple[bool, bool, bool] = (True, True, True),
) -> PGRComposite:
    w_cite, w_ho, w_adv = weights
    e_cite, e_ho, e_adv = enabled
    contrib = (
        (cite.score * w_cite if e_cite else 0.0)
        + (heldout.score * w_ho if e_ho else 0.0)
        + (adv.score * w_adv if e_adv else 0.0)
    )
    # Renormalize against the enabled mass so a disabled proxy doesn't pull
    # the composite down.
    active_mass = (
        (w_cite if e_cite else 0.0)
        + (w_ho if e_ho else 0.0)
        + (w_adv if e_adv else 0.0)
    )
    composite = (contrib / active_mass) if active_mass > 0 else 0.0
    return PGRComposite(
        cite=cite.score,
        heldout=heldout.score,
        adv=adv.score,
        composite=composite,
        detail={
            "cite_totals": {"support": cite.supports, "contradict": cite.contradicts, "neutral": cite.neutrals},
            "heldout_totals": {"support": heldout.supports, "contradict": heldout.contradicts, "neutral": heldout.neutrals, "skipped": heldout.skipped_no_heldout},
            "adv_totals": {"tested": adv.claims_tested, "undermined": adv.undermined, "survived": adv.survived},
        },
    )


def persist_pgr(
    conn: sqlite3.Connection, *, project_id: int, turn: int,
    composite: PGRComposite, support_score: float | None = None,
) -> None:
    """Write PGR scores into kpi_scores so they show up in trajectory charts.

    `support_score` is the diagnostic pgr_support metric (not part of
    composite; paired with pgr_cite for strict-vs-loose reading).
    """
    rows = [
        ("pgr_cite", composite.cite),
        ("pgr_heldout", composite.heldout),
        ("pgr_adv", composite.adv),
        ("pgr_composite", composite.composite),
    ]
    if support_score is not None:
        rows.append(("pgr_support", float(support_score)))
    for metric, value in rows:
        conn.execute(
            "INSERT INTO kpi_scores (project_id, agent_id, metric, value, turn) "
            "VALUES (?, NULL, ?, ?, ?)",
            (project_id, metric, float(value), turn),
        )
    conn.commit()


def score_project(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    llm: LLMClient,
    project_dir: Path = Path("./projects"),
    skip_adv: bool = False,
) -> PGRComposite:
    """Run enabled PGR proxies against the project's claims.md artifact,
    persist scores into kpi_scores, and return the composite.

    Respects per-project configuration in `projects.pgr_config_json` (set via
    `rp project pgr-set` or `rp project pgr-plan --apply`). If no config is
    present, falls back to (0.4/0.3/0.3) hard-coded weights.

    `skip_adv=True` overrides the project config to force Red Team off —
    useful when the user wants a cheap score.
    """
    from .pgr_planner import resolve_effective_weights
    from .projects import get_project

    project = get_project(conn, project_id)
    weights_cfg = resolve_effective_weights(project.pgr_config)
    cite_enabled, cite_w = weights_cfg["pgr_cite"]
    ho_enabled, ho_w = weights_cfg["pgr_heldout"]
    adv_enabled, adv_w = weights_cfg["pgr_adv"]
    if skip_adv:
        adv_enabled = False

    claims_path = project_dir / f"project_{project_id}" / "artifacts" / "claims.md"

    cite_res = (
        pgr_cite(conn, project_id=project_id, llm=llm, claims_md_path=claims_path)
        if cite_enabled
        else PGRCiteResult()
    )
    # pgr_support is a diagnostic sibling of pgr_cite — always computed when
    # cite is enabled (same cost profile; doesn't affect composite).
    support_res = (
        pgr_support(conn, project_id=project_id, llm=llm, claims_md_path=claims_path)
        if cite_enabled
        else PGRSupportResult()
    )
    heldout_res = (
        pgr_heldout(conn, project_id=project_id, llm=llm, claims_md_path=claims_path)
        if ho_enabled
        else PGRHeldoutResult()
    )
    adv_res = (
        pgr_adversarial(conn, project_id=project_id, llm=llm, claims_md_path=claims_path)
        if adv_enabled
        else PGRAdvResult()
    )

    composite = compute_composite(
        cite_res, heldout_res, adv_res,
        weights=(cite_w, ho_w, adv_w),
        enabled=(cite_enabled, ho_enabled, adv_enabled),
    )
    # Attach support totals to composite detail so the CLI can show them.
    composite.detail["support_totals"] = {
        "direct": support_res.direct,
        "partial": support_res.partial,
        "off_topic": support_res.off_topic,
    }
    composite.detail["support_score"] = support_res.score

    # Score turn = one past the latest existing turn for this project
    row = conn.execute(
        "SELECT COALESCE(MAX(turn), 0) + 1 AS t FROM kpi_scores WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    persist_pgr(
        conn, project_id=project_id, turn=row["t"],
        composite=composite,
        support_score=support_res.score if cite_enabled else None,
    )
    return composite

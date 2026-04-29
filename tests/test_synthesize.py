import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from research_pipeline.blackboard import (
    KIND_CRITIQUE, KIND_EVIDENCE, KIND_HYPOTHESIS, KIND_RESULT, add_entry,
)
from research_pipeline.db import connect, init_db
from research_pipeline.lifecycle import resolve_hypothesis_refs
from research_pipeline.projects import create_project, upsert_user
from research_pipeline.synthesize import (
    _format_entries_for_prompt,
    _gather_context,
    _synthesize_hypotheses,
    synthesize_artifacts,
)


@dataclass
class _Msg: content: str
@dataclass
class _Choice: message: _Msg
@dataclass
class _Resp: choices: list


class _FakeLLM:
    """Canned responses per-call. Used to test the orchestration layer
    without touching a real LLM."""

    def __init__(self, responses: list[str]):
        self._q = list(responses)
        self.calls = 0

    async def achat(self, role, messages, **kwargs):
        self.calls += 1
        text = self._q.pop(0) if self._q else ""
        return _Resp(choices=[_Choice(message=_Msg(content=text))])

    def embed(self, role, texts):
        if isinstance(texts, str):
            texts = [texts]
        return [[0.0] * 8 for _ in texts]


def _setup(tmp_path: Path):
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="evaluate X vs Y for agent memory",
            archetype_ids=["scout", "hypogen", "critic", "replicator"],
        )
        scout_id, hypogen_id, critic_id, rep_id = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM agents WHERE project_id=? ORDER BY id", (pid,)
            )
        ]
        add_entry(conn, project_id=pid, kind=KIND_EVIDENCE,
                  content="Soni et al. 2022: fragment-based screening produces non-covalent hits.",
                  turn=0, agent_id=scout_id, refs=["Soni et al.", "2022"])
        h1 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="X outperforms Y on DMR benchmarks.",
                       turn=0, agent_id=hypogen_id)
        h2 = add_entry(conn, project_id=pid, kind=KIND_HYPOTHESIS,
                       content="Single-session tasks regress with X.",
                       turn=0, agent_id=hypogen_id)
        add_entry(conn, project_id=pid, kind=KIND_RESULT,
                  content=f"My replication confirms [hyp #{h1}]; X wins DMR.",
                  turn=1, agent_id=rep_id)
        add_entry(conn, project_id=pid, kind=KIND_CRITIQUE,
                  content=f"[hyp #{h2}] is refuted — single-session numbers actually improve.",
                  turn=1, agent_id=critic_id)
        resolve_hypothesis_refs(conn, project_id=pid, turn=1)
    return db, pid


def test_hypothesis_matrix_is_mechanical(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        ctx = _gather_context(conn, pid)
        md = _synthesize_hypotheses(ctx)
    assert "# Hypothesis Matrix" in md
    assert "supported" in md
    assert "refuted" in md
    assert "## Summary" in md


def test_format_entries_truncates_and_tags_state(tmp_path: Path):
    db, pid = _setup(tmp_path)
    with connect(db) as conn:
        ctx = _gather_context(conn, pid)
    text = _format_entries_for_prompt(ctx["by_kind"][KIND_HYPOTHESIS])
    # At least one hypothesis has been marked refuted
    assert "[refuted]" in text or "[supported]" in text


def test_synthesize_writes_five_files(tmp_path: Path):
    """When both hypotheses are resolved (one supported, one refuted), the
    experiments generator short-circuits with no LLM call — so we expect 3
    LLM calls (claims + decision + risks), plus the mechanical hypotheses.
    """
    db, pid = _setup(tmp_path)
    llm = _FakeLLM(responses=[
        "# Claims\n\n## C1: X wins\n- Confidence: medium\n- Supporting: [hyp #2]\n- Falsifier: \"Wrong if Y wins at N>1000.\"\n- Status: supported\n",
        "# Recommended Next Action\n\nDeploy X.\n\n## Predicted Outcome\nDMR improves 15pct.\n\n## Confidence\n\nmedium.\n\n## Rooted in\n- [hyp #2]\n",
        "# Top Risks\n\n## R1: Extraction fragility\n- Likelihood: medium\n- Impact: high\n- Mitigation: fallback to embeddings\n",
    ])
    out_dir = tmp_path / "artifacts"
    with connect(db) as conn:
        result = asyncio.run(
            synthesize_artifacts(
                conn, project_id=pid, llm=llm, out_dir=out_dir,
            )
        )
    assert set(result.artifacts.keys()) == {
        "claims", "hypotheses", "experiments", "decision", "risks",
    }
    for path in result.artifacts.values():
        assert path.exists()
        assert path.stat().st_size > 0
    assert llm.calls == 3

    # Check specific contents
    claims_content = (out_dir / "claims.md").read_text(encoding="utf-8")
    assert "C1: X wins" in claims_content
    decision_content = (out_dir / "decision.md").read_text(encoding="utf-8")
    assert "Deploy X" in decision_content
    # Experiments short-circuited: no LLM call, stub content
    experiments_content = (out_dir / "experiments.md").read_text(encoding="utf-8")
    assert "no unresolved hypotheses" in experiments_content.lower()


def test_synthesize_falls_back_on_llm_failure(tmp_path: Path):
    db, pid = _setup(tmp_path)

    class _BrokenLLM:
        calls = 0
        async def achat(self, *a, **kw):
            _BrokenLLM.calls += 1
            raise RuntimeError("simulated failure")
        def embed(self, role, texts):
            return [[0.0]] if isinstance(texts, str) else [[0.0]] * len(texts)

    out_dir = tmp_path / "artifacts"
    with connect(db) as conn:
        result = asyncio.run(
            synthesize_artifacts(
                conn, project_id=pid, llm=_BrokenLLM(), out_dir=out_dir,
            )
        )
    # Five files must still exist even when LLM is broken
    assert set(result.artifacts.keys()) == {
        "claims", "hypotheses", "experiments", "decision", "risks",
    }
    claims = (out_dir / "claims.md").read_text(encoding="utf-8")
    assert "generation failed" in claims.lower()
    # Hypotheses is mechanical, so it should still have real content
    hyps = (out_dir / "hypotheses.md").read_text(encoding="utf-8")
    assert "Hypothesis Matrix" in hyps


def test_synthesize_handles_empty_hypotheses(tmp_path: Path):
    # Fresh project, no blackboard entries
    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(conn, user_id=uid, goal="empty",
                             archetype_ids=["scout"])
        ctx = _gather_context(conn, pid)
        md = _synthesize_hypotheses(ctx)
    assert "no hypotheses yet" in md.lower()

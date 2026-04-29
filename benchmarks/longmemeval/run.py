"""LongMemEval benchmark orchestrator.

Mirrors `benchmarks.locomo_eval.run` but for LongMemEval (Wang et al.,
ICLR 2025). Key protocol difference from LoCoMo: each question owns its
own controlled-haystack history. So we ingest a fresh memory store per
question, then run that one question, then drop the store.

Usage:
    # Quick smoke (cost-managed)
    uv run python -m benchmarks.longmemeval.run --variant oracle --max-questions 20

    # Full oracle (500 q × N systems)
    uv run python -m benchmarks.longmemeval.run --variant oracle

    # Full S — much slower (40-session haystacks per question)
    uv run python -m benchmarks.longmemeval.run --variant s

By default runs prototype + multitier + mem0_lite. Add --include-mem0-real
to also run real mem0.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from research_pipeline.adapter import LLMClient

from benchmarks.e1_blackboard_stress.systems import (
    EpistemicPrototype, GapAwarePrototype,
    Mem0Lite, MultiTierMemory, PrototypeMemory,
)

from .evaluator import JudgeResult, llm_judge_score, substring_score
from .loader import (
    LongMemQuestion, QUESTION_TYPES, filter_questions, load_longmemeval,
)


@dataclass
class QResult:
    qid: str
    qtype: str
    abstention: bool
    question: str
    gold: str
    prediction: str
    substring_correct: bool
    judge_correct: bool
    judge_raw: str
    ingest_ms: int
    query_ms: int


@dataclass
class SystemResult:
    name: str
    results: list[QResult] = field(default_factory=list)
    error: str | None = None

    def correct_substring(self) -> int:
        return sum(1 for r in self.results if r.substring_correct)

    def correct_judge(self) -> int:
        return sum(1 for r in self.results if r.judge_correct)

    @property
    def total(self) -> int:
        return len(self.results)

    def by_qtype(self, qtype: str, abstention: bool | None = None) -> tuple[int, int, int]:
        ms = [
            r for r in self.results
            if r.qtype == qtype
            and (abstention is None or r.abstention == abstention)
        ]
        if not ms:
            return (0, 0, 0)
        return (
            sum(1 for r in ms if r.substring_correct),
            sum(1 for r in ms if r.judge_correct),
            len(ms),
        )

    def total_ingest_ms(self) -> int:
        return sum(r.ingest_ms for r in self.results)


def _new_system(name: str, client: LLMClient):
    if name == "mem0_lite":
        return Mem0Lite(client)
    if name == "prototype":
        return PrototypeMemory(client)
    if name == "multitier":
        return MultiTierMemory(client, episode_size=200)
    if name == "epistemic_prototype":
        return EpistemicPrototype(client)
    if name == "gapaware_prototype":
        return GapAwarePrototype(client)
    if name in ("mem0_real", "mem0_real_v3"):
        # mem0_real and mem0_real_v3 use the same adapter; active mem0 package
        # version determines the algorithm — see BENCHMARKS.md Methodology.
        if name == "mem0_real_v3":
            # Fail loudly if someone runs --only-systems mem0_real_v3 against
            # a v2 install (PyPI default). ADDITIVE_EXTRACTION_PROMPT is the
            # v3 marker — the single-pass ADD-only extraction prompt mem0's
            # v3 changelog headlines.
            try:
                from mem0.configs.prompts import ADDITIVE_EXTRACTION_PROMPT  # noqa: F401
            except ImportError:
                raise RuntimeError(
                    "`mem0_real_v3` requested but installed mem0 lacks v3 markers "
                    "(ADDITIVE_EXTRACTION_PROMPT not found in mem0.configs.prompts). "
                    "Install v3 from mem0 git mainline via "
                    "`uv pip install git+https://github.com/mem0ai/mem0.git@693e7093` "
                    "(or `uv pip install -e <path-to-mem0-clone>` if you have a local clone). "
                    "See BENCHMARKS.md → Methodology → Reproducing v3 vs v2."
                )
        from benchmarks._real_products.mem0_real import Mem0Real
        return Mem0Real(collection=f"longmem_{int(time.time() * 1000)}")
    if name == "mflow_real":
        from benchmarks._real_products.mflow_real import MFlowReal
        return MFlowReal()
    raise ValueError(name)


def run_system_on_question(
    name: str,
    client: LLMClient,
    q: LongMemQuestion,
    judge_llm: LLMClient | None,
) -> QResult:
    """Ingest this question's haystack into a fresh memory store, then query.

    Each LongMemEval question is independent — its haystack contains the
    sessions controlled-sampled around its evidence. So unlike LoCoMo, we
    can't reuse one ingested store across many questions: we ingest a
    fresh one per question.
    """
    system = _new_system(name, client)

    t0 = time.time()
    for doc in q.docs:
        try:
            system.ingest(doc)
        except Exception as e:
            print(f"    [{name}] ingest error on {doc.id}: {str(e)[:120]}")
    ingest_ms = int((time.time() - t0) * 1000)

    t1 = time.time()
    try:
        prediction = system.query(q.question)
    except Exception as e:
        prediction = f"(error: {str(e)[:120]})"
    query_ms = int((time.time() - t1) * 1000)

    substr = substring_score(prediction, q.answer)

    if judge_llm is not None:
        jr = llm_judge_score(
            judge_llm,
            question=q.question, gold=q.answer, prediction=prediction,
            qtype=q.qtype, abstention=q.abstention,
        )
        judge_correct = jr.correct
        judge_raw = jr.raw
    else:
        judge_correct = substr
        judge_raw = "(no judge)"

    return QResult(
        qid=q.qid, qtype=q.qtype, abstention=q.abstention,
        question=q.question, gold=q.answer, prediction=prediction,
        substring_correct=substr, judge_correct=judge_correct,
        judge_raw=judge_raw, ingest_ms=ingest_ms, query_ms=query_ms,
    )


def render_report(rows: dict[str, SystemResult], variant: str, n_q: int) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    needs_mem0 = any(
        n in ("mem0_real", "mem0_real_v3", "mem0_lite") for n in rows
    )
    mem0_line = ""
    if needs_mem0:
        try:
            from benchmarks._real_products.mem0_real import mem0_provenance
            mem0_line = f"*mem0 provenance: {mem0_provenance()}*\n"
        except Exception:
            pass
    lines = [
        f"# LongMemEval evaluation — results\n",
        f"*Run: {now} | variant={variant} | n_questions={n_q}*\n",
        mem0_line,
        "Substring (lower bound) + LLM-judge (paper protocol, per-type prompts).\n",
    ]

    lines.append("## Overall accuracy\n")
    lines.append("| system | substring | LLM-judge | total ingest s | n |")
    lines.append("|---|---|---|---|---|")
    for name, sr in rows.items():
        lines.append(
            f"| **{name}** | "
            f"{sr.correct_substring()}/{sr.total} ({100*sr.correct_substring()/max(sr.total,1):.0f}%) | "
            f"{sr.correct_judge()}/{sr.total} ({100*sr.correct_judge()/max(sr.total,1):.0f}%) | "
            f"{sr.total_ingest_ms()/1000:.0f} | {sr.total} |"
        )
    lines.append("")

    qtypes_seen = sorted({r.qtype for sr in rows.values() for r in sr.results})
    if qtypes_seen:
        lines.append("## Per-type LLM-judge (answerable)\n")
        header = "| system | " + " | ".join(qtypes_seen) + " |"
        sep = "|" + "---|" * (len(qtypes_seen) + 1)
        lines.append(header)
        lines.append(sep)
        for name, sr in rows.items():
            cells = []
            for qt in qtypes_seen:
                _, ok, n = sr.by_qtype(qt, abstention=False)
                cells.append("—" if n == 0 else f"{ok}/{n}")
            lines.append(f"| **{name}** | " + " | ".join(cells) + " |")
        lines.append("")

        lines.append("## Per-type LLM-judge (abstention subset)\n")
        lines.append(header)
        lines.append(sep)
        for name, sr in rows.items():
            cells = []
            for qt in qtypes_seen:
                _, ok, n = sr.by_qtype(qt, abstention=True)
                cells.append("—" if n == 0 else f"{ok}/{n}")
            lines.append(f"| **{name}** | " + " | ".join(cells) + " |")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="oracle",
                        choices=["oracle", "s", "m"],
                        help="oracle (smallest) | s (~40 sessions) | m (~500 sessions)")
    parser.add_argument("--max-questions", type=int, default=None,
                        help="Cap on questions for cost-managed runs")
    parser.add_argument("--qtypes", type=str, default=None,
                        help=f"Comma-separated question types from {sorted(QUESTION_TYPES)}")
    parser.add_argument("--no-abstention", action="store_true",
                        help="Skip abstention questions")
    parser.add_argument("--include-mem0-real", action="store_true",
                        help="Also run real mem0")
    parser.add_argument("--include-mflow-real", action="store_true",
                        help="Also run real m_flow")
    parser.add_argument("--exclude-mem0-lite", action="store_true",
                        help="Skip mem0_lite (the always-on baseline)")
    parser.add_argument("--only-systems", type=str, default=None,
                        help="Override system list (comma-sep, e.g. 'mflow_real'). "
                             "When set, ignores all other --include/--exclude flags.")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM-judge scoring (substring only)")
    parser.add_argument("--max-workers", type=int, default=10,
                        help="Concurrent (question,system) workers. vLLM "
                             "handles concurrent requests via continuous "
                             "batching; Ollama embeddings serialize, so the "
                             "real speedup vs sequential is ~3-6×.")
    args = parser.parse_args()

    qtypes = (
        tuple(s.strip() for s in args.qtypes.split(",")) if args.qtypes else None
    )

    questions = load_longmemeval(variant=args.variant)
    questions = filter_questions(
        questions, qtypes=qtypes,
        include_abstention=not args.no_abstention,
        max_n=args.max_questions,
    )

    client = LLMClient()
    judge_llm = None if args.no_judge else client

    if args.only_systems:
        systems_to_run = [s.strip() for s in args.only_systems.split(",") if s.strip()]
    else:
        systems_to_run = ["prototype", "multitier"]
        if not args.exclude_mem0_lite:
            systems_to_run.insert(0, "mem0_lite")
        if args.include_mem0_real:
            systems_to_run.append("mem0_real")
        if args.include_mflow_real:
            systems_to_run.append("mflow_real")

    rows: dict[str, SystemResult] = {n: SystemResult(name=n) for n in systems_to_run}
    rows_lock = Lock()
    print_lock = Lock()

    n_jobs = len(questions) * len(systems_to_run)
    print(
        f"\n=== LongMemEval ({args.variant}) — {len(questions)} questions × "
        f"{len(systems_to_run)} systems = {n_jobs} jobs, "
        f"max_workers={args.max_workers} ==="
    )

    def _job(qi: int, q: LongMemQuestion, name: str) -> tuple[int, str, QResult]:
        sr_q = run_system_on_question(name, client, q, judge_llm)
        return qi, name, sr_q

    completed = 0
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = [
            pool.submit(_job, qi, q, name)
            for qi, q in enumerate(questions)
            for name in systems_to_run
        ]
        for fut in as_completed(futures):
            qi, name, sr_q = fut.result()
            with rows_lock:
                rows[name].results.append(sr_q)
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed else 0
            eta_sec = (n_jobs - completed) / rate if rate else 0
            ms = "✓" if sr_q.substring_correct else "✗"
            mj = "✓" if sr_q.judge_correct else "✗"
            with print_lock:
                print(
                    f"[{completed}/{n_jobs} eta={eta_sec/60:.0f}m] "
                    f"Q{qi+1} {sr_q.qid} {name:11s} qtype={sr_q.qtype} "
                    f"sub={ms} judge={mj} ingest={sr_q.ingest_ms}ms "
                    f"query={sr_q.query_ms}ms: {sr_q.prediction[:50]}",
                    flush=True,
                )

    print("\n" + "=" * 80)
    print("LONGMEMEVAL SUMMARY")
    print("=" * 80)
    for name, sr in rows.items():
        print(
            f"  {name:14s} "
            f"substring={sr.correct_substring()}/{sr.total} "
            f"({100*sr.correct_substring()/max(sr.total,1):.0f}%)  "
            f"judge={sr.correct_judge()}/{sr.total} "
            f"({100*sr.correct_judge()/max(sr.total,1):.0f}%)"
        )

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = out_dir / f"run_{args.variant}_{stamp}.md"
    report.write_text(
        render_report(rows, args.variant, len(questions)),
        encoding="utf-8",
    )
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

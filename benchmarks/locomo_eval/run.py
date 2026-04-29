"""LoCoMo benchmark orchestrator.

Usage:
    # Quick subset (cost-managed)
    uv run python -m benchmarks.locomo_eval.run \
        --conversations 1 --max-questions 20

    # Full evaluation
    uv run python -m benchmarks.locomo_eval.run --conversations 10

By default runs the prototype + multitier + mem0_lite. Add --include-mem0-real
to also run real mem0 (slower but closes Gap 1).

Scoring: both substring + LLM-judge. Substring is a fast lower-bound; LLM-judge
matches the paper's protocol more closely.
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
    CATEGORY_NAMES, LocomoConversation, LocomoQuestion,
    filter_questions, load_locomo,
)


@dataclass
class QResult:
    qid: str
    category: int
    question: str
    gold: str
    prediction: str
    substring_correct: bool
    judge_correct: bool
    judge_raw: str
    duration_ms: int


@dataclass
class SystemResult:
    name: str
    ingest_ms: int = 0
    results: list[QResult] = field(default_factory=list)
    error: str | None = None

    def correct_substring(self) -> int:
        return sum(1 for r in self.results if r.substring_correct)

    def correct_judge(self) -> int:
        return sum(1 for r in self.results if r.judge_correct)

    @property
    def total(self) -> int:
        return len(self.results)

    def by_category(self, cat: int) -> tuple[int, int, int]:
        ms = [r for r in self.results if r.category == cat]
        if not ms:
            return (0, 0, 0)
        return (
            sum(1 for r in ms if r.substring_correct),
            sum(1 for r in ms if r.judge_correct),
            len(ms),
        )


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
        # mem0_real and mem0_real_v3 use the same adapter; the active mem0
        # package version (v2 OSS pypi vs v3 OSS git mainline) determines the
        # algorithm. The two names are kept distinct so result files clearly
        # label which version produced them — see BENCHMARKS.md Methodology.
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
        return Mem0Real(collection=f"locomo_{int(time.time())}")
    if name == "zep_real":
        from benchmarks._real_products.zep_real import ZepReal
        return ZepReal(warmup_seconds=10.0)
    if name == "supermemory_real":
        from benchmarks._real_products.supermemory_real import SupermemoryReal
        return SupermemoryReal(warmup_seconds=10.0)
    raise ValueError(name)


def run_system_on_conversation(
    name: str,
    client: LLMClient,
    conv: LocomoConversation,
    questions: list[LocomoQuestion],
    judge_llm: LLMClient | None = None,
) -> SystemResult:
    """Ingest one conversation's turns into the system, then run questions."""
    system = _new_system(name, client)

    # Ingest
    t0 = time.time()
    for doc in conv.docs:
        try:
            system.ingest(doc)
        except Exception as e:
            print(f"  [{name}] ingest error on {doc.id}: {str(e)[:120]}")
    ingest_ms = int((time.time() - t0) * 1000)
    print(f"[{name}] ingested {len(conv.docs)} turns in {ingest_ms}ms "
          f"({ingest_ms / max(len(conv.docs), 1):.0f}ms/turn)")

    sr = SystemResult(name=name, ingest_ms=ingest_ms)
    for q in questions:
        t1 = time.time()
        try:
            prediction = system.query(q.question)
        except Exception as e:
            prediction = f"(error: {str(e)[:120]})"
        dur = int((time.time() - t1) * 1000)

        substr = substring_score(prediction, q.answer)

        if judge_llm is not None:
            jr = llm_judge_score(
                judge_llm,
                question=q.question, gold=q.answer, prediction=prediction,
            )
            judge_correct = jr.correct
            judge_raw = jr.raw
        else:
            judge_correct = substr  # fallback when judge disabled
            judge_raw = "(no judge)"

        sr.results.append(QResult(
            qid=q.qid, category=q.category, question=q.question,
            gold=q.answer, prediction=prediction,
            substring_correct=substr, judge_correct=judge_correct,
            judge_raw=judge_raw, duration_ms=dur,
        ))
        mark_s = "✓" if substr else "✗"
        mark_j = "✓" if judge_correct else "✗"
        print(f"  [{name}] {q.qid} (cat={q.category}) "
              f"sub={mark_s} judge={mark_j} ({dur}ms): {prediction[:70]}")
    return sr


def render_report(
    rows: dict[str, SystemResult], n_questions: int, n_conversations: int,
) -> str:
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
        f"# LoCoMo evaluation — results\n",
        f"*Run: {now}*\n",
        mem0_line,
        f"{n_conversations} conversation(s), {n_questions} question(s) per system. "
        f"Substring + LLM-judge scoring.\n",
    ]
    cats = sorted({r.category for sr in rows.values() for r in sr.results})

    lines.append("## Overall accuracy\n")
    lines.append("| system | substring | LLM-judge | ingest ms | n |")
    lines.append("|---|---|---|---|---|")
    for name, sr in rows.items():
        lines.append(
            f"| **{name}** | {sr.correct_substring()}/{sr.total} "
            f"({100 * sr.correct_substring() / max(sr.total, 1):.0f}%) | "
            f"{sr.correct_judge()}/{sr.total} "
            f"({100 * sr.correct_judge() / max(sr.total, 1):.0f}%) | "
            f"{sr.ingest_ms} | {sr.total} |"
        )
    lines.append("")

    lines.append("## Per-category LLM-judge accuracy\n")
    header = (
        "| system | "
        + " | ".join(f"cat {c} ({CATEGORY_NAMES.get(c, '?')})" for c in cats)
        + " |"
    )
    sep = "|" + "---|" * (len(cats) + 1)
    lines.append(header)
    lines.append(sep)
    for name, sr in rows.items():
        cells = []
        for c in cats:
            ok_s, ok_j, n = sr.by_category(c)
            cells.append("—" if n == 0 else f"{ok_j}/{n}")
        lines.append(f"| **{name}** | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversations", type=int, default=1,
                        help="Number of LoCoMo conversations to process (1-10)")
    parser.add_argument("--max-questions", type=int, default=None,
                        help="Cap on questions per conversation (None = all)")
    parser.add_argument("--categories", type=str, default=None,
                        help="Comma-separated category ids (1-5). Default: all")
    parser.add_argument("--include-mem0-real", action="store_true",
                        help="Also run real mem0 (closes Gap 1; slower)")
    parser.add_argument("--include-real-products", action="store_true",
                        help="Run all real products: mem0, zep, supermemory")
    parser.add_argument("--include-variants", action="store_true",
                        help="Also run epistemic_prototype + gapaware_prototype")
    parser.add_argument("--only-systems", type=str, default=None,
                        help="Override system list (comma-sep). When set, ignores other --include flags.")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM-judge scoring (substring only)")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="Concurrent (conversation, system) workers. vLLM "
                             "handles concurrent requests via continuous batching; "
                             "Ollama embeddings serialize. Default 4.")
    args = parser.parse_args()

    convs = load_locomo()[: args.conversations]
    cats = (
        tuple(int(c) for c in args.categories.split(","))
        if args.categories else None
    )

    client = LLMClient()
    judge_llm = None if args.no_judge else client

    if args.only_systems:
        systems_to_run = [s.strip() for s in args.only_systems.split(",") if s.strip()]
    else:
        systems_to_run = ["mem0_lite", "prototype", "multitier"]
        if args.include_mem0_real:
            systems_to_run.append("mem0_real")
        if args.include_real_products:
            for s in ("mem0_real", "zep_real", "supermemory_real"):
                if s not in systems_to_run:
                    systems_to_run.append(s)
        if args.include_variants:
            systems_to_run.extend(["epistemic_prototype", "gapaware_prototype"])

    # Aggregate results across conversations per system. We dispatch
    # (conversation, system) pairs to a thread pool so vLLM's continuous
    # batching can saturate across systems instead of running them serially
    # per conversation (which used to cap a 4-system run at ~21h on local
    # Gemma; with max_workers=4 we get ~5h).
    rows: dict[str, SystemResult] = {}
    rows_lock = Lock()
    print_lock = Lock()
    total_qs_per_system = 0

    # Pre-filter questions per conversation so the worker only does the
    # ingest+query work — keep filtering outside the lock-contended path.
    convs_with_qs = []
    for ci, conv in enumerate(convs):
        questions = filter_questions(
            conv.questions, categories=cats,
            answerable_only=True, max_n=args.max_questions,
        )
        total_qs_per_system += len(questions)
        convs_with_qs.append((ci, conv, questions))

    def _job(ci: int, conv: LocomoConversation, questions, name: str):
        sr = run_system_on_conversation(
            name, client, conv, questions, judge_llm=judge_llm,
        )
        return ci, conv, name, sr

    n_jobs = len(convs_with_qs) * len(systems_to_run)
    print(
        f"\n=== LoCoMo: {len(convs_with_qs)} conversation(s) × "
        f"{len(systems_to_run)} system(s) = {n_jobs} jobs, "
        f"max_workers={args.max_workers} ==="
    )

    completed = 0
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = [
            pool.submit(_job, ci, conv, questions, name)
            for ci, conv, questions in convs_with_qs
            for name in systems_to_run
        ]
        for fut in as_completed(futures):
            ci, conv, name, sr = fut.result()
            with rows_lock:
                existing = rows.get(name)
                if existing is None:
                    rows[name] = sr
                else:
                    existing.results.extend(sr.results)
                    existing.ingest_ms += sr.ingest_ms
            completed += 1
            elapsed = time.time() - t_start
            rate = completed / elapsed if elapsed else 0
            eta_s = (n_jobs - completed) / rate if rate else 0
            with print_lock:
                print(
                    f"[{completed}/{n_jobs} eta={eta_s/60:.0f}m] "
                    f"conv {ci+1}/{len(convs_with_qs)} ({conv.sample_id}) "
                    f"{name:18s} {sr.correct_judge()}/{sr.total} "
                    f"({100*sr.correct_judge()/max(sr.total,1):.0f}%)",
                    flush=True,
                )

    print("\n" + "=" * 80)
    print("LOCOMO SUMMARY")
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
    report = out_dir / f"run_{stamp}.md"
    report.write_text(
        render_report(rows, total_qs_per_system, len(convs)),
        encoding="utf-8",
    )
    print(f"\nreport -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

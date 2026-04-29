"""LongMemEval dataset loader.

Mirrors `benchmarks.locomo_eval.loader` but for LongMemEval (Wang et al.,
ICLR 2025). Adapts each haystack-conversation's turns into our Doc-stream
format and exposes questions in a system-agnostic way.

Source: https://github.com/xiaowu0162/LongMemEval (cloned as a sibling of research-pipeline at science/LongMemEval)
HF data: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned

Three variants:
  longmemeval_oracle.json  — only evidence sessions (smallest, easiest)
  longmemeval_s_cleaned.json — ~40 sessions per question (~115K tokens)
  longmemeval_m_cleaned.json — ~500 sessions per question (massive)

Each entry has:
  question_id        unique id, suffix '_abs' for abstention questions
  question_type      one of: single-session-user, single-session-assistant,
                     single-session-preference, temporal-reasoning,
                     knowledge-update, multi-session
  question           the question text
  answer             gold answer (or rubric for preference; or "no info" for abstention)
  haystack_sessions  list of sessions; each is a list of {role, content}
  haystack_session_ids   per-session ids
  haystack_dates     timestamps per session
  answer_session_ids which session-ids contain the evidence
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from benchmarks.e1_blackboard_stress.corpus import Doc


# LongMemEval is cloned as a sibling of research-pipeline. Resolve relative to
# this file: loader.py -> longmemeval/ -> benchmarks/ -> research-pipeline/ -> science/.
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "LongMemEval" / "data"
_VARIANT_FILES = {
    "oracle": "longmemeval_oracle.json",
    "s": "longmemeval_s_cleaned.json",
    "m": "longmemeval_m_cleaned.json",
}


# Question types from the README; abstention is detected via the '_abs' suffix.
QUESTION_TYPES = {
    "single-session-user",
    "single-session-assistant",
    "single-session-preference",
    "temporal-reasoning",
    "knowledge-update",
    "multi-session",
}


@dataclass(frozen=True)
class LongMemQuestion:
    qid: str
    question: str
    answer: str  # gold answer or rubric (for preference) or unanswerable explanation
    qtype: str  # one of QUESTION_TYPES
    abstention: bool  # True if qid endswith '_abs'
    evidence_sessions: tuple[str, ...]  # session_ids that contain the evidence
    docs: list[Doc]  # haystack rendered as a Doc stream


def _parse_session_date(raw: str) -> datetime:
    """LongMemEval session timestamps are typically ISO-ish strings like
    '2023/05/08 (Mon) 14:30'. Try a few common formats; fall back to a
    deterministic synthetic date so the rest of the pipeline still works."""
    cleaned = raw.strip()
    formats = (
        "%Y/%m/%d (%a) %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return datetime(2023, 1, 1, 0, 0)


def _entry_to_question(entry: dict) -> LongMemQuestion:
    qid = str(entry["question_id"])
    abstention = qid.endswith("_abs")
    qtype = str(entry.get("question_type", ""))
    question = str(entry.get("question", ""))
    answer = str(entry.get("answer", ""))

    sessions = entry.get("haystack_sessions") or []
    session_ids = entry.get("haystack_session_ids") or [
        f"sess_{i:04d}" for i in range(len(sessions))
    ]
    session_dates = entry.get("haystack_dates") or [""] * len(sessions)
    evidence = tuple(str(x) for x in (entry.get("answer_session_ids") or ()))

    docs: list[Doc] = []
    for sess_idx, session in enumerate(sessions):
        sid = str(session_ids[sess_idx]) if sess_idx < len(session_ids) else f"sess_{sess_idx:04d}"
        sdate = session_dates[sess_idx] if sess_idx < len(session_dates) else ""
        base_dt = _parse_session_date(sdate)
        if not isinstance(session, list):
            continue
        for turn_i, turn in enumerate(session):
            role = turn.get("role", "user") if isinstance(turn, dict) else "user"
            content = turn.get("content", "") if isinstance(turn, dict) else str(turn)
            t = base_dt + timedelta(seconds=turn_i)
            docs.append(Doc(
                id=f"{sid}:{turn_i}",
                pub_date=t.isoformat(timespec="seconds"),
                text=f"[{role}] {content}",
                entities=tuple(),
            ))

    return LongMemQuestion(
        qid=qid,
        question=question,
        answer=answer,
        qtype=qtype,
        abstention=abstention,
        evidence_sessions=evidence,
        docs=docs,
    )


def load_longmemeval(
    variant: str = "oracle",
    data_dir: Path | None = None,
) -> list[LongMemQuestion]:
    """Load a LongMemEval JSON file into a list of LongMemQuestion.

    Args:
        variant: 'oracle' (smallest, evidence-only), 's' (standard ~115K
            tokens), or 'm' (very long ~500 sessions).
        data_dir: override default location.

    Each question owns its own haystack as a Doc stream — unlike LoCoMo
    where many questions share one conversation, LongMemEval pairs each
    question with its own controlled-haystack history.
    """
    if variant not in _VARIANT_FILES:
        raise ValueError(f"variant must be one of {sorted(_VARIANT_FILES)}; got {variant!r}")
    base = Path(data_dir) if data_dir else _DEFAULT_DATA_DIR
    path = base / _VARIANT_FILES[variant]
    if not path.exists():
        raise FileNotFoundError(
            f"LongMemEval data file not found: {path}\n"
            f"Download from: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/"
            f"resolve/main/{_VARIANT_FILES[variant]}"
        )
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    return [_entry_to_question(entry) for entry in raw]


def filter_questions(
    questions: list[LongMemQuestion],
    *,
    qtypes: tuple[str, ...] | None = None,
    include_abstention: bool = True,
    answerable_only: bool = False,
    max_n: int | None = None,
) -> list[LongMemQuestion]:
    """Subset by question type and/or abstention status, optionally cap n.

    answerable_only drops abstention questions AND items with no gold answer.
    Useful for cost-managed runs that mirror locomo's filter_questions.
    """
    out = list(questions)
    if qtypes:
        out = [q for q in out if q.qtype in qtypes]
    if not include_abstention:
        out = [q for q in out if not q.abstention]
    if answerable_only:
        out = [q for q in out if not q.abstention and q.answer]
    if max_n is not None:
        out = out[:max_n]
    return out

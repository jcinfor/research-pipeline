"""LoCoMo dataset loader.

Closes Gap 2: we've been benchmarking on synthetic corpora; LoCoMo is the
established external benchmark mem0 / m-flow / supermemory all report on.
Adapts each conversation's turns into our Doc-stream format and exposes
questions in a system-agnostic way.

Source: https://github.com/snap-research/locomo (cloned as a sibling of research-pipeline at science/locomo)
Paper: Maharana et al., "Evaluating Very Long-Term Conversational Memory of LLM Agents", ACL 2024
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from benchmarks.e1_blackboard_stress.corpus import Doc


# locomo is cloned as a sibling of research-pipeline. Resolve relative to this
# file: loader.py -> locomo_eval/ -> benchmarks/ -> research-pipeline/ -> science/.
_DEFAULT_DATA_PATH = Path(__file__).resolve().parents[3] / "locomo" / "data" / "locomo10.json"


# LoCoMo categories (per the README + paper)
CATEGORY_NAMES = {
    1: "single_hop",
    2: "multi_hop",
    3: "open_domain",
    4: "temporal_reasoning",
    5: "adversarial",
}


@dataclass(frozen=True)
class LocomoQuestion:
    qid: str
    question: str
    answer: str
    category: int
    evidence: tuple[str, ...]  # dialogue ids (e.g. ('D1:3',))


@dataclass
class LocomoConversation:
    sample_id: str
    speaker_a: str
    speaker_b: str
    docs: list[Doc]                  # one per turn, chronological
    questions: list[LocomoQuestion]


def _parse_session_datetime(raw: str) -> datetime:
    """LoCoMo session timestamps look like '1:56 pm on 8 May, 2023'.

    We attempt the documented format; on parse failure fall back to a
    deterministic synthetic timestamp so ingest still works (the order
    matters more than the exact wallclock for our memory benchmarks)."""
    # Normalize: '1:56 pm on 8 May, 2023' → '1:56 pm 8 May 2023'
    cleaned = raw.replace(" on ", " ").replace(",", "")
    for fmt in ("%I:%M %p %d %B %Y", "%I:%M %p %d %b %Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    # Fallback
    return datetime(2023, 1, 1, 0, 0)


def load_locomo(data_path: Path | None = None) -> list[LocomoConversation]:
    path = Path(data_path) if data_path else _DEFAULT_DATA_PATH
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    out: list[LocomoConversation] = []
    for sample in raw:
        sample_id = str(sample.get("sample_id", f"conv_{len(out)}"))
        conv = sample["conversation"]
        speaker_a = conv["speaker_a"]
        speaker_b = conv["speaker_b"]

        # Collect (session_index, datetime, [turn dicts]) tuples
        session_keys = sorted(
            (k for k in conv.keys()
             if re.match(r"^session_\d+$", k)),
            key=lambda k: int(k.split("_")[1]),
        )

        docs: list[Doc] = []
        for sk in session_keys:
            idx = int(sk.split("_")[1])
            dt_key = f"session_{idx}_date_time"
            base_dt = _parse_session_datetime(conv.get(dt_key, ""))
            for turn_i, turn in enumerate(conv[sk]):
                speaker = turn["speaker"]
                text = turn["text"]
                dia_id = turn["dia_id"]
                # Synthesize per-turn timestamp by stepping seconds within session
                t = base_dt.replace(microsecond=0)
                # Add (idx-1) hours base offset + per-turn second offset.
                # Sessions are sequential days/hours apart; turns within a
                # session step by seconds for deterministic ordering.
                from datetime import timedelta
                t = t + timedelta(seconds=turn_i)
                docs.append(Doc(
                    id=dia_id,
                    pub_date=t.isoformat(timespec="seconds"),
                    text=f"[{speaker}] {text}",
                    entities=tuple(),
                ))

        questions: list[LocomoQuestion] = []
        for qi, q in enumerate(sample.get("qa", [])):
            qid = f"{sample_id}_q{qi:03d}"
            ev = q.get("evidence")
            if isinstance(ev, list):
                evidence = tuple(str(e) for e in ev)
            elif isinstance(ev, str):
                evidence = (ev,)
            else:
                evidence = tuple()
            questions.append(LocomoQuestion(
                qid=qid,
                question=str(q.get("question", "")),
                answer=str(q.get("answer", "")) if q.get("answer") is not None else "",
                category=int(q.get("category", 0)) if q.get("category") is not None else 0,
                evidence=evidence,
            ))

        out.append(LocomoConversation(
            sample_id=sample_id,
            speaker_a=speaker_a,
            speaker_b=speaker_b,
            docs=docs,
            questions=questions,
        ))
    return out


def filter_questions(
    questions: list[LocomoQuestion],
    *,
    categories: tuple[int, ...] | None = None,
    answerable_only: bool = True,
    max_n: int | None = None,
) -> list[LocomoQuestion]:
    """Subset questions by category and (optionally) skip ones with no
    ground-truth answer. Useful for cost-managed runs."""
    out = list(questions)
    if categories:
        out = [q for q in out if q.category in categories]
    if answerable_only:
        out = [q for q in out if q.answer]
    if max_n is not None:
        out = out[:max_n]
    return out

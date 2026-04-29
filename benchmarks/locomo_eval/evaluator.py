"""LoCoMo evaluator — substring + LLM-judge scoring.

Substring match is fast and deterministic but brittle on free-form QA. The
LoCoMo paper uses LLM-judge for scoring. We implement both: substring as a
quick lower-bound, LLM-judge as the closer-to-paper number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from research_pipeline.adapter import LLMClient


_JUDGE_SYSTEM = """You are a strict QA judge for the LoCoMo conversational
memory benchmark. Given a question, the gold answer, and a model's predicted
answer, decide whether the predicted answer is correct.

A prediction is CORRECT if it conveys the same factual content as the gold
answer. Minor paraphrasing, additional context, or different formatting is
fine. The prediction is INCORRECT if it asserts a different fact, contradicts
the gold answer, or fails to commit to the gold information.

For yes/no questions, the answer must agree on the yes/no decision.
For date/time questions, the date or time must match (any reasonable
phrasing is acceptable).
For "no information" gold answers ("Not enough info", "Unknown"), a correct
prediction either says it doesn't know or refuses to commit.

Reply with EXACTLY one word: CORRECT or INCORRECT.
"""


@dataclass
class JudgeResult:
    correct: bool
    raw: str  # raw judge response


def normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace, drop trailing punctuation."""
    if not text:
        return ""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t.rstrip(" .,!?;:")


def substring_score(answer: str, gold: str) -> bool:
    """True if the gold answer substring appears in the predicted answer."""
    if not gold:
        return False
    return normalize(gold) in normalize(answer)


def llm_judge_score(
    llm: LLMClient,
    *,
    question: str,
    gold: str,
    prediction: str,
    role: str = "judge",
) -> JudgeResult:
    """Use an LLM to grade prediction against gold. Returns CORRECT/INCORRECT."""
    try:
        resp = llm.chat(
            role,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": (
                    f"QUESTION: {question}\n"
                    f"GOLD ANSWER: {gold}\n"
                    f"PREDICTED: {prediction}\n\n"
                    "Reply CORRECT or INCORRECT."
                )},
            ],
            max_tokens=10, temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip().upper()
    except Exception as e:
        return JudgeResult(correct=False, raw=f"(judge error: {str(e)[:80]})")

    correct = raw.startswith("CORRECT") or raw == "CORRECT"
    return JudgeResult(correct=correct, raw=raw)

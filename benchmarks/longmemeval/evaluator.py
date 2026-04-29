"""LongMemEval evaluator — substring + LLM-judge scoring.

Mirrors `benchmarks.locomo_eval.evaluator` but uses LongMemEval's per-type
judge prompts (Wang et al., ICLR 2025) which differ by question_type:

  - single-session-* / multi-session: standard "contains correct answer" check
  - temporal-reasoning: same, but allow off-by-one for day/week/month counts
  - knowledge-update: yes if updated answer appears (old-info coexistence ok)
  - single-session-preference: rubric-based ("does response use user info correctly")
  - abstention: yes iff the model says it can't answer / info is incomplete

These templates come straight from
`LongMemEval/src/evaluation/evaluate_qa.py:get_anscheck_prompt`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from research_pipeline.adapter import LLMClient


_BASE_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a "
    "model. Please answer yes if the response contains the correct answer. "
    "Otherwise, answer no. If the response is equivalent to the correct "
    "answer or contains all the intermediate steps to get the correct "
    "answer, you should also answer yes. If the response only contains a "
    "subset of the information required by the answer, answer no.\n\n"
    "Question: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\n"
    "Is the model response correct? Answer yes or no only."
)

_TEMPORAL_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a "
    "model. Please answer yes if the response contains the correct answer. "
    "Otherwise, answer no. If the response is equivalent to the correct "
    "answer or contains all the intermediate steps to get the correct "
    "answer, you should also answer yes. If the response only contains a "
    "subset of the information required by the answer, answer no. In "
    "addition, do not penalize off-by-one errors for the number of days. "
    "If the question asks for the number of days/weeks/months, etc., and "
    "the model makes off-by-one errors (e.g., predicting 19 days when the "
    "answer is 18), the model's response is still correct.\n\n"
    "Question: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\n"
    "Is the model response correct? Answer yes or no only."
)

_KNOWLEDGE_UPDATE_TEMPLATE = (
    "I will give you a question, a correct answer, and a response from a "
    "model. Please answer yes if the response contains the correct answer. "
    "Otherwise, answer no. If the response contains some previous "
    "information along with an updated answer, the response should be "
    "considered as correct as long as the updated answer is the required "
    "answer.\n\n"
    "Question: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\n"
    "Is the model response correct? Answer yes or no only."
)

_PREFERENCE_TEMPLATE = (
    "I will give you a question, a rubric for desired personalized "
    "response, and a response from a model. Please answer yes if the "
    "response satisfies the desired response. Otherwise, answer no. The "
    "model does not need to reflect all the points in the rubric. The "
    "response is correct as long as it recalls and utilizes the user's "
    "personal information correctly.\n\n"
    "Question: {q}\n\nRubric: {a}\n\nModel Response: {r}\n\n"
    "Is the model response correct? Answer yes or no only."
)

_ABSTENTION_TEMPLATE = (
    "I will give you an unanswerable question, an explanation, and a "
    "response from a model. Please answer yes if the model correctly "
    "identifies the question as unanswerable. The model could say that the "
    "information is incomplete, or some other information is given but the "
    "asked information is not.\n\n"
    "Question: {q}\n\nExplanation: {a}\n\nModel Response: {r}\n\n"
    "Does the model correctly identify the question as unanswerable? "
    "Answer yes or no only."
)


@dataclass
class JudgeResult:
    correct: bool
    raw: str  # raw judge response


def normalize(text: str) -> str:
    if not text:
        return ""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t.rstrip(" .,!?;:")


def substring_score(answer: str, gold: str) -> bool:
    """Fast substring lower-bound. Not always meaningful for LongMemEval
    (especially preference/abstention questions) but useful as a sanity
    check alongside LLM-judge."""
    if not gold:
        return False
    return normalize(gold) in normalize(answer)


def _select_template(qtype: str, abstention: bool) -> str:
    if abstention:
        return _ABSTENTION_TEMPLATE
    if qtype == "temporal-reasoning":
        return _TEMPORAL_TEMPLATE
    if qtype == "knowledge-update":
        return _KNOWLEDGE_UPDATE_TEMPLATE
    if qtype == "single-session-preference":
        return _PREFERENCE_TEMPLATE
    # single-session-user / single-session-assistant / multi-session
    return _BASE_TEMPLATE


def llm_judge_score(
    llm: LLMClient,
    *,
    question: str,
    gold: str,
    prediction: str,
    qtype: str,
    abstention: bool = False,
    role: str = "judge",
) -> JudgeResult:
    """Grade prediction against gold using LongMemEval's per-type judge prompt.

    Returns CORRECT/INCORRECT mapped from the paper's yes/no judge protocol.
    """
    template = _select_template(qtype, abstention)
    user_prompt = template.format(q=question, a=gold, r=prediction)
    try:
        resp = llm.chat(
            role,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=10, temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip().lower()
    except Exception as e:
        return JudgeResult(correct=False, raw=f"(judge error: {str(e)[:80]})")
    correct = raw.startswith("yes")
    return JudgeResult(correct=correct, raw=raw)

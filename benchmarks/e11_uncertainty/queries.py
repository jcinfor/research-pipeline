"""E11 queries — designed to elicit "I don't know" when the answer is absent.

10 queries across four categories:
    control            — answer IS in memory; should be returned correctly
    missing_attribute  — entity is in memory; attribute was never recorded
    missing_entity     — entity was never mentioned at all
    never_happened     — specific event never observed; correct answer is "no"

For control queries: substring scoring on the correct value.

For absence queries (the other three categories): scoring is INVERTED. We
check that the answer contains an "I don't know" signal AND does NOT contain
a confident hallucinated value. The set of hallucination markers is the
union of all values that EXIST in the corpus for similar attributes — if
the system makes one up that happens to be in our value set, it's a clear
hallucination.
"""
from __future__ import annotations

from dataclasses import dataclass


# Phrases that signal honest uncertainty
_UNCERTAINTY_MARKERS = (
    "unknown",
    "don't know",
    "do not know",
    "no record",
    "not recorded",
    "no information",
    "not in",       # "not in the memory", "not in the data"
    "not available",
    "not provided",
    "no data",
    "not mention",   # "not mentioned"
    "no observ",     # "no observation", "not observed"
    "cannot determine",
    "can't determine",
    "not specified",
    "no entry",
    "not present",
    "not found",
    "no",            # naked "no" — covers "did X happen?" answered "No."
    "never",         # "never recorded", "never happened"
)

# Concrete values that exist in the corpus — used as hallucination markers.
# If a system's answer to an absence question contains any of these, it's
# making things up.
_CORPUS_VALUES = (
    "active", "blocked", "review", "done", "idle",
    "lead", "contributor", "reviewer", "advisor", "observer",
    "alpha", "beta", "gamma", "delta",
)


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    category: str  # control / missing_attribute / missing_entity / never_happened
    correct_key: str | None = None        # for control only
    forbidden_values: tuple[str, ...] = () # values that would indicate hallucination


QUERIES: tuple[Query, ...] = (
    # === CONTROL — answers ARE in memory ===
    Query(
        id="q1_control_alice_status",
        question="What is Alice's current status?",
        category="control",
        correct_key="review",
    ),
    Query(
        id="q2_control_bob_role",
        question="What is Bob's current role?",
        category="control",
        correct_key="reviewer",
    ),

    # === MISSING ATTRIBUTE — entity exists, attribute was never recorded ===
    # Alice's salary, location, manager, age — none of these were observed.
    Query(
        id="q3_missing_alice_salary",
        question="What is Alice's salary?",
        category="missing_attribute",
        forbidden_values=_CORPUS_VALUES,  # values from other attrs would be hallucination
    ),
    Query(
        id="q4_missing_bob_manager",
        question="Who is Bob's manager?",
        category="missing_attribute",
        forbidden_values=("Alice", "Carol"),  # only known names
    ),
    Query(
        id="q5_missing_carol_location",
        question="What city is Carol based in?",
        category="missing_attribute",
        # No city values in the corpus — any specific city is hallucination
        forbidden_values=tuple(),
    ),

    # === MISSING ENTITY — entity was never mentioned ===
    Query(
        id="q6_missing_entity_dave",
        question="What is Dave's current role?",
        category="missing_entity",
        forbidden_values=_CORPUS_VALUES,
    ),
    Query(
        id="q7_missing_entity_eve",
        question="What project is Eve assigned to?",
        category="missing_entity",
        forbidden_values=_CORPUS_VALUES,
    ),

    # === NEVER HAPPENED — specific event/transition not in memory ===
    # Alice was never on project gamma. Bob was never an observer. Carol was never blocked.
    Query(
        id="q8_alice_was_on_gamma",
        question="Has Alice ever been assigned to project gamma? Answer yes or no.",
        category="never_happened",
        # Correct answer: "no". A system that says "yes" is hallucinating
        # OR is confused. Either way, wrong.
        forbidden_values=("yes",),
    ),
    Query(
        id="q9_bob_was_observer",
        question="Has Bob ever held the role of observer? Answer yes or no.",
        category="never_happened",
        forbidden_values=("yes",),
    ),
    Query(
        id="q10_carol_was_blocked",
        question="Has Carol ever had a status of blocked? Answer yes or no.",
        category="never_happened",
        forbidden_values=("yes",),
    ),
)


def _has_uncertainty_signal(text: str) -> bool:
    """Detect honest "I don't know" signals in `text` (already lowercased).

    Uses word-boundary regex for short markers ("no", "never") to avoid false
    positives inside words like "know", "annotation", "now"."""
    import re
    # Word-boundary markers — must appear as whole words
    word_markers = ("no", "never", "none")
    for w in word_markers:
        if re.search(rf"\b{re.escape(w)}\b", text):
            return True
    # Substring-fine markers — phrases that don't have the false-positive issue
    phrase_markers = (
        "unknown", "don't know", "do not know", "no record", "not recorded",
        "no information", "not in the", "not available", "not provided",
        "no data", "not mention", "no observ", "cannot determine",
        "can't determine", "not specified", "no entry", "not present",
        "not found", "do not have", "don't have", "isn't recorded",
        "is not recorded", "no such", "no salary", "no city", "no manager",
    )
    return any(p in text for p in phrase_markers)


def score(answer: str, query: Query) -> bool:
    """Score an answer for E11.

    For control queries: standard substring match on correct_key.
    For absence queries: PASS iff (a) answer signals uncertainty AND
        (b) answer does NOT contain a forbidden (hallucinated) value.
    """
    if not answer:
        return False
    a = answer.lower()

    if query.category == "control":
        return query.correct_key.lower() in a if query.correct_key else False

    has_uncertainty = _has_uncertainty_signal(a)
    has_hallucinated_value = any(
        v.lower() in a for v in query.forbidden_values
    )
    return has_uncertainty and not has_hallucinated_value

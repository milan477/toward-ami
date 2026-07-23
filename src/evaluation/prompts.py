"""Build deterministic MCQ/OEQ prompts and the PIEC-aware judge prompt.

MCQ  — the original multiple-choice form: shuffled lettered options, the model
       picks one. Graded automatically.
OEQ  — options stripped, the model answers in 1-2 sentences. Graded by an
       LLM-as-judge (see judge.py).

Option order is shuffled deterministically per question (seeded by qid) so runs
are reproducible and the correct answer isn't always "A".
"""

from __future__ import annotations

import json
import random
import re
import string

# Per-category grading instruction injected into the PIEC judge prompt.
STRATEGY_RUBRIC = {
    "binary_exact": (
        "PERCEPTUAL: require an exact semantic match to the reference. Accept synonyms, "
        "paraphrases, and equivalent representations such as '3' and 'three'. Do not accept "
        "a merely close numeric value or a related but different label."
    ),
    "binary_contextual": (
        "CONTEXTUAL: require an exact semantic match to the reference fact. Accept synonyms, "
        "paraphrases, and equivalent representations, but not a related fact at a different "
        "level of specificity unless it entails the reference in this question's context."
    ),
    "binary_expert_multi": (
        "INFERENTIAL: decide whether the answer is a reasonable interpretation for which "
        "general consensus is desired. It may differ from the reference wording or specificity "
        "when it is compatible with the reference and the supplied evidence. For example, if "
        "the reference is 'outdoors', 'in the mountains' can score 1, normally with LOW "
        "confidence because the compatibility is uncertain and indirect."
    ),
    "graded_experiential": (
        "EXPERIENTIAL: accept a plausible listener experience compatible with the reference; "
        "consensus is not required. Related descriptions may be correct even when they are not "
        "identical. For example, reference 'melancholic' and answer 'sadness' should score 1 "
        "with MID confidence. Reject empty, irrelevant, or clearly incompatible experiences."
    ),
}

PIEC_JUDGE_PROMPT = """You are a strict, fair evaluator of an answer to an audio benchmark.

Question category (PIEC): {category}
{rubric}

Always return a BINARY score:
- 1: correct under the category-specific rule above.
- 0: incorrect, empty, irrelevant, or unsupported under that rule.

Confidence describes how directly the available evidence supports YOUR grading decision:
- high: direct semantic equivalence with the reference answer or a clear contradiction, depending on the question category. (e.g. "melancholy" and "sadness")
- mid: a compatible interpretation, synonym, or experiential overlap that makes sense in the context of the question, but is not necessarily the same as the reference answer. (e.g. "outdoors" and "outside of the house")
- low: a reasonable answer that matches the reference answer (e.g. is a subset of the reference answer), but you don't have enough knowledge about the audio to be sure it is correct. (e.g. 'outdoors' and 'in the mountains', or 'Belgium' and 'Flanders')

Use all supplied context as evidence. The reference is authoritative but, for inferential and
experiential questions, it is not necessarily the only acceptable wording or interpretation.

Question: {question}
Original question: {original_question}
Answer format expected: {answer_format}
Reference answer: {reference}
Original benchmark answer: {original_answer}
Question nature: {question_nature}
Action-content labels: {action_content}
Creator categories: {creator_categories}
Distractors (known incorrect answers): {distractors}
Speech transcription (may be empty):
<transcription>{transcription}</transcription>
Model's answer: {answer}

Reply with ONLY a JSON object and nothing else:
{{"score": <0|1>, "confidence": "<low|mid|high>", \
"rationale": "<one short sentence>"}}"""

def parse_distractors(raw) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return [str(x) for x in val] if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def shuffled_options(correct: str, distractors: list[str], qid: str) -> list[str]:
    opts = [correct, *distractors]
    random.Random(qid).shuffle(opts)
    return opts


def build_mcq(
    question: str,
    correct: str,
    distractors: list[str],
    qid: str,
    *,
    instruction: str,
) -> dict:
    """Return {prompt, options, correct_letter, letter_map}."""
    opts = shuffled_options(correct, distractors, qid)
    letters = string.ascii_uppercase[:len(opts)]
    lines = [f"{ltr}. {opt}" for ltr, opt in zip(letters, opts)]
    correct_letter = letters[opts.index(correct)]
    prompt = f"{instruction}\n\nQuestion: {question}\n\n" + "\n".join(lines)
    return {
        "prompt": prompt,
        "options": opts,
        "letter_map": dict(zip(letters, opts)),
        "correct_letter": correct_letter,
        "correct_answer": correct,
    }


def build_oeq(question: str, correct: str, *, instruction: str,
              answer_format: str | None = None, example: str | None = None) -> dict:
    """Return {prompt, reference_answer}.

    If answer_format and/or example are given, they are added to the prompt to
    steer the answer's form (the example illustrates the expected form only — it
    is an incorrect answer, so it never leaks the correct one)."""
    lines = [instruction]
    if answer_format and answer_format.strip():
        lines.append(f"Answer format: {answer_format.strip()}.")
    if example and example.strip():
        lines.append(f'Example of a validly-formatted answer (shows the expected form '
                     f'only — it is NOT the correct answer): "{example.strip()}"')
    prompt = "\n".join(lines) + f"\n\nQuestion: {question}"
    return {"prompt": prompt, "reference_answer": correct}


def extract_letter(response: str, letter_map: dict) -> str | None:
    """Pull the chosen option letter from a free-form model reply."""
    letters = set(letter_map)
    # 1. a standalone letter, optionally like "B." / "(B)" / "B)"
    for m in re.finditer(r"\b([A-Z])\b[.):]?", response):
        if m.group(1) in letters:
            return m.group(1)
    # 2. fall back to exact option-text match
    low = response.strip().lower()
    for ltr, opt in letter_map.items():
        if opt.strip().lower() == low:
            return ltr
    return None

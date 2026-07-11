"""Step 3: build the two prompt variants for each question.

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

INSTRUCTION_MCQ = (
    "Listen to the audio and answer the multiple-choice question. "
    "Respond with only the letter of the correct option, and nothing else. Example: A\n\nNo other text or comments."
)
INSTRUCTION_OEQ = (
    "Listen to the audio and answer the question in 1-2 sentences. "
    "Be specific and ground your answer in what you hear."
)
INSTRUCTION_OEQ_GUIDED = (
    "Listen to the audio and answer the question. "
    "Be specific and ground your answer in what you hear."
)

# Per-strategy grading instruction injected into the PIAC judge prompt.
STRATEGY_RUBRIC = {
    "binary_exact": (
        "This is a PERCEPTUAL question with a single measurable ground truth. Grade BINARY: "
        "score 4 if the answer matches the reference (exactly, as a synonym/paraphrase, or "
        "within a small tolerance for a numeric value), otherwise 0. NEVER give 1/2/3. A "
        "close-but-wrong value scores 0 (e.g. 20 when the reference is 26 -> 0)."
    ),
    "binary_contextual": (
        "This is a CONTEXTUAL question - an external factual ground truth. Grade BINARY: "
        "score 4 if the answer matches the reference fact, otherwise 0. Accept a "
        "semantically-compatible answer of different specificity (reference 'China' and "
        "answer 'Beijing' -> 4; reference 'Beijing' and answer 'China' -> 4). If the reference "
        "indicates the fact is unknown and the model declines/says unknown, score 4. Never 1/2/3."
    ),
    "binary_expert_multi": (
        "This is an INFERENTIAL question - trained analysis on which experts largely agree "
        "but valid alternatives exist. Grade BINARY: score 4 if the answer matches the "
        "reference OR any other reasonable expert-valid answer to this question, otherwise 0. "
        "Do NOT require the model to justify its answer (it was not asked to). Never 1/2/3."
    ),
    "graded_affective": (
        "This is an AFFECTIVE question - subjective, with no single right answer. Grade 0-4 "
        "on: plausibility (is the described feeling musically reasonable?), internal "
        "consistency, and grounding (does it tie the feeling to perceptual/inferential "
        "features?). Accept similar emotions ('sad' ~= 'melancholic' -> high). "
        "4 = plausible, consistent and grounded; 2 = plausible but ungrounded/thin; 0 = "
        "implausible, contradictory, or empty."
    ),
}

PIAC_JUDGE_PROMPT = """You are a strict, fair music-evaluation judge. Grade a model's open-ended \
answer to a question about an audio clip, and separately assess hallucination.

Question category (PIAC): {category}
{rubric}

Also assess HALLUCINATION: a confident claim in the answer that is wrong or ungrounded - \
most often a fluent higher-level claim (affective or inferential) that rests on a wrong or \
absent lower-level (perceptual) observation, or a stated fact that contradicts the reference. \
If the answer hallucinates, set hallucinated=true and hallucination_level to the PIAC level \
of the failing claim (perceptual / inferential / affective / contextual); otherwise \
hallucinated=false and hallucination_level="none". Also rate grounding 0-1 (how well the \
answer ties its claims to observable audio features).

Question: {question}
Answer format expected: {answer_format}
Reference answer (one valid ground truth): {reference}
Model's answer: {answer}

Reply with ONLY a JSON object and nothing else:
{{"score": <int 0-4>, "grounded": <float 0-1>, "hallucinated": <true|false>, \
"hallucination_level": "<perceptual|inferential|affective|contextual|none>", \
"rationale": "<one short sentence>"}}"""

GENERAL_JUDGE_PROMPT = """You are grading a model's open-ended answer to a question about an audio clip.

Question: {question}
Reference answer (ground truth): {reference}
Model's answer: {answer}

Score how well the model's answer matches the reference answer, on an integer scale 0-4:
0 = wrong, irrelevant, or no answer
1 = mostly wrong; only a slight or incidental overlap
2 = partially correct; a MULTI-PART answer that gets some required parts but misses others
3 = largely correct; all key content present, only minor wording differences
4 = fully correct and complete

Grading rules (apply strictly):
- A single number or single discrete value (a count, a note, yes/no, one name, one word) is
  either right or wrong: 4 if it matches the reference, 0 if it does not. NEVER give partial
  credit for a close-but-wrong value - e.g. answering 20 when the reference is 26 scores 0.
- Ignore extra information: if the answer contains everything the reference requires PLUS
  additional details, do not penalize the extra - that is still 4.
- "Partially correct" (2) applies ONLY when the reference has several required parts and the
  answer is incomplete (some parts right, some missing) - never to a single value that is merely close.
- Judge meaning, not wording: accept synonyms and paraphrases of the reference.

Reply with ONLY a JSON object: {{"score": <integer 0-4>, "rationale": "<one short sentence>"}}"""


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


def build_mcq(question: str, correct: str, distractors: list[str], qid: str) -> dict:
    """Return {prompt, options, correct_letter, letter_map}."""
    opts = shuffled_options(correct, distractors, qid)
    letters = string.ascii_uppercase[:len(opts)]
    lines = [f"{ltr}. {opt}" for ltr, opt in zip(letters, opts)]
    correct_letter = letters[opts.index(correct)]
    prompt = f"{INSTRUCTION_MCQ}\n\nQuestion: {question}\n\n" + "\n".join(lines)
    return {
        "prompt": prompt,
        "options": opts,
        "letter_map": dict(zip(letters, opts)),
        "correct_letter": correct_letter,
        "correct_answer": correct,
    }


def build_oeq(question: str, correct: str,
              answer_format: str | None = None, example: str | None = None) -> dict:
    """Return {prompt, reference_answer}.

    If answer_format and/or example are given, they are added to the prompt to
    steer the answer's form (the example illustrates the expected form only — it
    is an incorrect answer, so it never leaks the correct one)."""
    guided = bool((answer_format or "").strip() or (example or "").strip())
    lines = [INSTRUCTION_OEQ_GUIDED if guided else INSTRUCTION_OEQ]
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

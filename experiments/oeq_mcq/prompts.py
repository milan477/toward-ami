"""Step 3: build the two prompt variants for each question.

MCQ  — the original multiple-choice form: shuffled lettered options, the model
       picks one. Graded automatically.
OEQ  — options stripped, the model answers in 1-2 sentences. Graded by an
       LLM-as-judge (see judge.py).

Option order is shuffled deterministically per question (seeded by qid) so runs
are reproducible and the correct answer isn't always "A".
"""

import json
import random
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

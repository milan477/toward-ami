"""Canonical definitions and prompt construction for experiments 0 through 6."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from src.evaluation.prompts import build_mcq, parse_distractors
from src.querying.common import row_answer, row_first_json_value


LETTER_AUDIO = (
    "Listen to the audio and answer the multiple-choice question. Respond with "
    "only the letter of the correct option and nothing else. Example: A"
)
LETTER_NO_AUDIO = (
    "Answer the multiple-choice question using only the written question and "
    "options. Answer with your best guess of the answer, even though you don't have access to the audio. Respond with only the letter of the correct option and nothing "
    "else. Example: A"
)
LETTER_STT = (
    "Answer the multiple-choice question using only the written question, "
    "options, and speech-to-text transcript. You do not have access to the audio. "
    "Answer with your best guess. Respond with only the letter of the correct "
    "option and nothing else. "
    "Example: A"
)
TEXT_AUDIO = (
    "Listen to the audio and answer the multiple-choice question. Respond with "
    "only the complete text of the correct option and nothing else. Do not "
    "respond with its letter."
)

OEQ_AUDIO = (
    "Listen to the audio and answer the question. "
    "Return only the answer in the requested format."
)

FORMAT_TYPE_AUDIO = (
    "Listen to the audio and answer the question without using multiple-choice "
    "options. Return only the answer in the requested format."
)

PIEC_INSTRUCTIONS = {
    "perceptual": (
        "Listen to the audio and answer the rewritten perceptual question "
        "concisely using only audible evidence."
    ),
    "inferential": (
        "Listen to the audio and answer the rewritten inferential question "
        "concisely, drawing the best-supported inference from the recording."
    ),
    "experiential": (
        "Listen to the audio and answer the rewritten experiential question "
        "concisely from the listener's experience of the recording."
    ),
    "contextual": (
        "Listen to the audio and answer the rewritten contextual question "
        "concisely using the recording and relevant background knowledge."
    ),
}

DEPENDENCY_COLUMNS = {
    "transcription": {"transcription"},
    "classification": {"action_content", "piec", "question_nature", "answer_format"},
    "oeq_rewrite": {"question_oeq", "answer_oeq"},
    "task_rewrite": {"question_task"},
}


@dataclass(frozen=True)
class ExperimentVariant:
    number: int
    name: str
    description: str
    response_mode: str
    use_audio: bool = True
    use_stt: bool = False
    question_column: str = "question"
    answer_column: str = "answer"
    add_format_type: bool = False
    piec_instruction: bool = False
    dependencies: tuple[str, ...] = ()

    @property
    def experiment_name(self) -> str:
        return f"exp_{self.number}_{self.name}"

    @property
    def requires_enhanced(self) -> bool:
        return bool(self.dependencies)

    def metadata(self) -> dict:
        return {**asdict(self), "requires_enhanced": self.requires_enhanced}


VARIANTS = {
    0: ExperimentVariant(
        0,
        "text_mcq",
        "Original benchmark MCQ with full option-text response",
        "option_text",
    ),
    1: ExperimentVariant(
        1,
        "no_audio",
        "Original benchmark MCQ without audio",
        "letter",
        use_audio=False,
    ),
    2: ExperimentVariant(
        2,
        "no_audio_stt",
        "Original benchmark MCQ without audio, with a speech-to-text transcript",
        "letter",
        use_audio=False,
        use_stt=True,
        dependencies=("transcription",),
    ),
    3: ExperimentVariant(
        3,
        "format_type_oeq",
        "Distractor-free question with answer format and question type",
        "open_text",
        add_format_type=True,
        dependencies=("classification",),
    ),
    4: ExperimentVariant(
        4,
        "original_mcq",
        "Original benchmark MCQ with letter response",
        "letter",
    ),
    5: ExperimentVariant(
        5,
        "piec_rewrite",
        "PIEC-aware open-ended question rewrite",
        "open_text",
        question_column="question_oeq",
        answer_column="answer_oeq",
        piec_instruction=True,
        dependencies=("classification", "oeq_rewrite"),
    ),
    6: ExperimentVariant(
        6,
        "task_rewrite_mcq",
        "Meaning-preserving imperative task rewrite with letter response",
        "letter",
        question_column="question_task",
        dependencies=("task_rewrite",),
    ),
}


def get_variant(number: int) -> ExperimentVariant:
    try:
        return VARIANTS[number]
    except KeyError as exc:
        raise ValueError(f"Unknown experiment {number}; expected 0 through 6.") from exc


def required_columns(variant: ExperimentVariant) -> set[str]:
    columns = {"qid", "question", "answer", "url"}
    if variant.response_mode in {"letter", "option_text"}:
        columns.add("distractors")
    for dependency in variant.dependencies:
        try:
            columns.update(DEPENDENCY_COLUMNS[dependency])
        except KeyError as exc:
            raise ValueError(
                f"Unknown preprocessing dependency {dependency!r} for "
                f"{variant.experiment_name}."
            ) from exc
    return columns


def prompt_configuration(variant: ExperimentVariant) -> dict:
    """Return every static prompt instruction used by one variant."""
    if variant.number == 0:
        return {"instruction": TEXT_AUDIO}
    if variant.number == 1:
        return {"instruction": LETTER_NO_AUDIO}
    if variant.number == 2:
        return {"instruction": LETTER_STT, "transcript_tag": "<transcription>"}
    if variant.number == 3:
        return {"instruction": FORMAT_TYPE_AUDIO}
    if variant.number == 4:
        return {"instruction": LETTER_AUDIO}
    if variant.number == 5:
        return {"instructions_by_piec": PIEC_INSTRUCTIONS}
    return {
        "instruction": LETTER_AUDIO,
        "question_preprocessing": "meaning-preserving imperative task rewrite",
        "rewrite_equivalence_validation": True,
    }


def build_variant_item(
    row, variant: ExperimentVariant, *, transcription: str = ""
) -> dict:
    """Build one prompt and its deterministic grading information."""
    original_question = str(row.get("question", "")).strip()
    question = str(row.get(variant.question_column, "")).strip()
    correct = (
        row_first_json_value(row, variant.answer_column)
        if variant.answer_column != "answer"
        else row_answer(row)
    )
    qid = str(row.get("qid", ""))

    if variant.response_mode in {"letter", "option_text"}:
        instruction = {
            0: TEXT_AUDIO,
            1: LETTER_NO_AUDIO,
            2: LETTER_STT,
            4: LETTER_AUDIO,
            6: LETTER_AUDIO,
        }[variant.number]
        mcq = build_mcq(
            question,
            correct,
            parse_distractors(row.get("distractors", "")),
            qid,
            instruction=instruction,
        )
        prompt = mcq["prompt"]
        if variant.use_stt:
            transcript = transcription.strip() or "[No intelligible speech transcribed.]"
            prompt = (
                f"{instruction}\n\nSpeech-to-text transcript:\n"
                f"<transcription>{transcript}</transcription>\n\n"
                f"Question: {question}\n\n"
                + "\n".join(
                    f"{letter}. {answer}" for letter, answer in mcq["letter_map"].items()
                )
            )
        return {
            **mcq,
            "prompt": prompt,
            "question": question,
            "original_question": original_question,
            "reference_answer": correct,
        }

    answer_format = str(row.get("answer_format", "")).strip()
    question_nature = str(row.get("question_nature", "")).strip()
    if variant.add_format_type:
        prompt = (
            f"{FORMAT_TYPE_AUDIO}\n"
            f"Question type: {question_nature or 'unspecified'}\n"
            f"Answer format: {answer_format or 'a concise answer'}\n\n"
            f"Question: {question}"
        )
    else:
        piec = str(row.get("piec", "")).strip().lower()
        instruction = PIEC_INSTRUCTIONS.get(
            piec, "Listen to the audio and answer the rewritten question concisely."
        )
        prompt = f"{instruction}\n\nQuestion: {question}"

    return {
        "prompt": prompt,
        "question": question,
        "original_question": original_question,
        "reference_answer": correct,
        "correct_answer": correct,
        "answer_format": answer_format,
        "question_nature": question_nature,
    }


def extract_option_text(response: str, options: list[str]) -> str | None:
    """Return the canonical option for an exact text response, ignoring styling."""
    normalized = _normalize_option(response)
    for option in options:
        if _normalize_option(option) == normalized:
            return option
    return None


def _normalize_option(value: str) -> str:
    value = " ".join(str(value).strip().split()).casefold()
    value = value.strip("\"'`“”‘’")
    return re.sub(r"[.!?]+$", "", value).strip()

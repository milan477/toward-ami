"""Annotators for benchmark-question analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.config import DEFAULT_JUDGE_SPEC
from src.helpers.answer_parsers import (
    clean_value,
    extract_json_object,
    normalize_piac,
    normalize_question_nature,
    normalize_skills,
)
from src.analysis.taxonomy import RULE_OF_THUMB, describe


class Client(Protocol):
    model_id: str

    def generate(self, prompt: str, max_tokens: int = 256) -> str:
        ...


@dataclass
class BaseAnnotator:
    client: Client
    name: str
    output_columns: tuple[str, ...]
    max_tokens: int = 220

    def prompt(self, row: dict) -> str:
        raise NotImplementedError

    def parse(self, text: str) -> dict:
        raise NotImplementedError

    def annotate(self, row: dict) -> dict:
        return self.parse(self.client.generate(self.prompt(row), max_tokens=self.max_tokens))


class QuestionNatureAnnotator(BaseAnnotator):
    def __init__(self, client: Client):
        super().__init__(
            client,
            "question_nature",
            ("question_nature", "question_nature_rationale"),
            max_tokens=140,
        )

    def prompt(self, row: dict) -> str:
        return f"""Classify the nature of this benchmark question.

Ignore dataset distractors/options metadata. Use only the question text and reference answer.

Labels:
- tfq: asks for true/false, yes/no, or equivalent binary truth.
- mcq: embeds a closed set of choices in the question text itself, e.g. "indoors or outdoors".
- mlc: requires a specific label/value such as a number, note, instrument, chord, tempo, location, or name.
- oeq: asks for a free-form description, explanation, or interpretation.

Question: {row.get("question", "")}
Reference answer: {row.get("correct_answer", "")}

Reply with ONLY JSON:
{{"question_nature": "<tfq|mcq|mlc|oeq>", "rationale": "<one short sentence>"}}"""

    def parse(self, text: str) -> dict:
        obj = extract_json_object(text)
        return {
            "question_nature": normalize_question_nature(obj.get("question_nature"), text),
            "question_nature_rationale": clean_value(obj.get("rationale"), 300),
        }


class AnswerFormatAnnotator(BaseAnnotator):
    def __init__(self, client: Client):
        super().__init__(
            client,
            "answer_format",
            ("answer_format", "answer_format_rationale"),
            max_tokens=140,
        )

    def prompt(self, row: dict) -> str:
        return f"""Describe the answer format for this benchmark question as-is.

Give the form a correct answer should take, not the answer content. Be specific and concise.

Question: {row.get("question", "")}
Reference answer: {row.get("correct_answer", "")}

Reply with ONLY JSON:
{{"answer_format": "<format as-is>", "rationale": "<one short sentence>"}}"""

    def parse(self, text: str) -> dict:
        obj = extract_json_object(text)
        return {
            "answer_format": clean_value(obj.get("answer_format")),
            "answer_format_rationale": clean_value(obj.get("rationale"), 300),
        }


class ExampleAnswerAnnotator(BaseAnnotator):
    def __init__(self, client: Client):
        super().__init__(
            client,
            "example_answer",
            ("example_answer", "example_answer_rationale"),
            max_tokens=160,
        )

    def prompt(self, row: dict) -> str:
        return f"""Give one example answer for this benchmark question as-is.

The example should be in the same answer space and format as the reference answer. It may be
the reference answer if that is the clearest example of the answer space.

Question: {row.get("question", "")}
Reference answer: {row.get("correct_answer", "")}

Reply with ONLY JSON:
{{"example_answer": "<example answer as-is>", "rationale": "<one short sentence>"}}"""

    def parse(self, text: str) -> dict:
        obj = extract_json_object(text)
        return {
            "example_answer": clean_value(obj.get("example_answer")),
            "example_answer_rationale": clean_value(obj.get("rationale"), 300),
        }


class PIACCategoryAnnotator(BaseAnnotator):
    def __init__(self, client: Client):
        super().__init__(
            client,
            "piac",
            ("category", "piac", "category_auto", "category_rationale", "eval_strategy"),
            max_tokens=220,
        )

    def prompt(self, row: dict) -> str:
        return f"""Classify this audio-question into exactly one PIAC category.

PIAC taxonomy:
{describe()}

{RULE_OF_THUMB}

Question: {row.get("question", "")}
Reference answer: {row.get("correct_answer", "")}

Reply with ONLY JSON:
{{"piac": "<perceptual|inferential|affective|contextual>", "rationale": "<one short sentence>"}}"""

    def parse(self, text: str) -> dict:
        from src.analysis.taxonomy import eval_strategy

        obj = extract_json_object(text)
        piac = normalize_piac(obj.get("piac"), text)
        return {
            "category": piac,
            "piac": piac,
            "category_auto": piac,
            "category_rationale": clean_value(obj.get("rationale"), 300),
            "eval_strategy": eval_strategy(piac),
        }


class SkillsAnnotator(BaseAnnotator):
    def __init__(self, client: Client):
        super().__init__(
            client,
            "skills",
            ("skills", "skills_rationale"),
            max_tokens=180,
        )

    def prompt(self, row: dict) -> str:
        return f"""List the skills required to answer this audio benchmark question.

Return one to three concise skills. Each skill must be at most three words.
Good examples: "melody identification", "pitch hearing", "spatial recognition".

Question: {row.get("question", "")}
Reference answer: {row.get("correct_answer", "")}

Reply with ONLY JSON:
{{"skills": ["<skill>", "..."], "rationale": "<one short sentence>"}}"""

    def parse(self, text: str) -> dict:
        obj = extract_json_object(text)
        return {
            "skills": ", ".join(normalize_skills(obj.get("skills"), text)),
            "skills_rationale": clean_value(obj.get("rationale"), 300),
        }


def build_annotators(spec: str = DEFAULT_JUDGE_SPEC) -> list[BaseAnnotator]:
    from models.client import make_client

    client = make_client(spec)
    return [
        QuestionNatureAnnotator(client),
        AnswerFormatAnnotator(client),
        ExampleAnswerAnnotator(client),
        PIACCategoryAnnotator(client),
        SkillsAnnotator(client),
    ]

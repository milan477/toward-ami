"""Structured LLM enhancement for normalized benchmark questions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

from src.config import DEFAULT_JUDGE_SPEC
from src.helpers.answer_parsers import (
    extract_json_object,
    normalize_piec,
    normalize_question_nature,
)
from src.analysis.dimensions import normalize_action_content
from src.analysis.prompts import build_enhancement_prompt


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


class QuestionDimensionsAnnotator(BaseAnnotator):
    """Create all five standardized enhancement fields in one model call."""

    def __init__(self, client: Client):
        super().__init__(
            client,
            "question_dimensions",
            (
                "action_content",
                "piec",
                "question_nature",
                "answer_format",
                "example_incorrect_answer",
            ),
            max_tokens=320,
        )

    def annotate(self, row: dict) -> dict:
        prompt = self.prompt(row)
        raw = self.client.generate(prompt, max_tokens=self.max_tokens)
        parsed = self.parse(raw)
        parsed["example_incorrect_answer"] = _validated_incorrect_answer(
            parsed.get("example_incorrect_answer", ""), row, parsed["question_nature"]
        )
        return {
            **parsed,
            # Stored in the JSONL provenance sidecar, not the enhanced CSV.
            "enhancement_prompt": prompt,
            "enhancement_raw_response": raw.strip(),
        }

    def prompt(self, row: dict) -> str:
        return build_enhancement_prompt(row)

    def parse(self, text: str) -> dict:
        obj = extract_json_object(text)
        pairs = normalize_action_content(obj.get("action_content"))
        nature = normalize_question_nature(obj.get("question_nature"), text)
        incorrect = _clean_scalar(obj.get("example_incorrect_answer"), 500)
        return {
            "action_content": json.dumps(pairs, ensure_ascii=False) if pairs else "",
            "piec": normalize_piec(obj.get("piec"), text),
            "question_nature": nature,
            "answer_format": _clean_scalar(obj.get("answer_format"), 200),
            "example_incorrect_answer": "" if nature == "true_false" else incorrect,
        }


def _clean_scalar(value, limit: int) -> str:
    if isinstance(value, (list, dict)):
        return ""
    return " ".join(str(value or "").split())[:limit]


def _json_list(value) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [value]
    if not isinstance(value, list):
        return []
    return [" ".join(str(item).split()) for item in value if str(item).strip()]


def _validated_incorrect_answer(value: str, row: dict, nature: str) -> str:
    """Reject correct/invalid examples and use a creator distractor as fallback."""
    if nature == "true_false":
        return ""
    def answer_key(item: str) -> str:
        return item.casefold().strip(" \t\r\n.,;:!?\"'")

    correct = {answer_key(item) for item in _json_list(row.get("answer", ""))}
    candidates = [value, *_json_list(row.get("distractors", ""))]
    for candidate in candidates:
        cleaned = _clean_scalar(candidate, 500)
        if cleaned and answer_key(cleaned) not in correct:
            return cleaned
    return ""


def build_annotators(spec: str = DEFAULT_JUDGE_SPEC) -> list[BaseAnnotator]:
    from models.client import make_client

    return [QuestionDimensionsAnnotator(make_client(spec))]

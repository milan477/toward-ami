"""Reusable parsers for structured model answers."""

from __future__ import annotations

import json
import re
from typing import Any

PIEC_CATEGORIES = {"perceptual", "inferential", "experiential", "contextual"}
QUESTION_NATURES = {
    "true_false", "multiple_choice", "ordinal_value",
    "specific_label", "open_ended",
}


def extract_json_object(text: str) -> dict[str, Any]:
    """Return the first JSON object in a model response, or an empty dict."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group())
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _clean(value: Any, limit: int | None = None) -> str:
    out = str(value or "").strip()
    return out[:limit] if limit else out


def clean_value(value: Any, limit: int | None = None) -> str:
    return _clean(value, limit)


def _normalize_nature(value: Any, text: str) -> str:
    raw = _clean(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "tf": "true_false", "tfq": "true_false", "t_f": "true_false",
        "true/false": "true_false", "true_or_false": "true_false",
        "yes_no": "true_false", "binary": "true_false",
        "mcq": "multiple_choice", "multiple_choice_question": "multiple_choice",
        "choice": "multiple_choice",
        "mlc": "specific_label", "multi_label": "specific_label",
        "multilabel": "specific_label", "label": "specific_label",
        "specific_value": "specific_label",
        "specific_label_or_value": "specific_label",
        "open": "open_ended", "oeq": "open_ended",
        "open_ended_question": "open_ended", "free_form": "open_ended",
    }
    nature = aliases.get(raw, raw)
    if nature in QUESTION_NATURES:
        return nature
    lower = text.lower()
    for candidate in QUESTION_NATURES:
        if re.search(rf"\b{candidate}\b", lower):
            return candidate
    return ""


def normalize_question_nature(value: Any, text: str = "") -> str:
    return _normalize_nature(value, text)


def _normalize_piec(value: Any, text: str) -> str:
    piec = _clean(value).lower()
    if piec in PIEC_CATEGORIES:
        return piec
    return next((c for c in PIEC_CATEGORIES if re.search(rf"\b{c}\b", text, re.I)), "")


def normalize_piec(value: Any, text: str = "") -> str:
    return _normalize_piec(value, text)


def _normalize_skills(value: Any, text: str) -> list[str]:
    raw = value if isinstance(value, list) else []
    skills: list[str] = []
    for item in raw:
        words = re.findall(r"[A-Za-z0-9]+", str(item).lower())
        if not words:
            continue
        skill = " ".join(words[:3])
        if skill not in skills:
            skills.append(skill)
        if len(skills) == 3:
            break
    if not skills:
        fallback = re.findall(r"[A-Za-z0-9]+(?:\s+[A-Za-z0-9]+){0,2}", text.lower())
        skills = [s.strip() for s in fallback[:3] if s.strip()]
    return skills or ["other"]


def normalize_skills(value: Any, text: str = "") -> list[str]:
    return _normalize_skills(value, text)


def parse_analysis_answer(text: str) -> dict:
    """Parse the unified benchmark-analysis classification response."""
    obj = extract_json_object(text)
    nature_obj = obj.get("question_nature", {})
    fmt_obj = obj.get("answer_format", {})
    example_obj = obj.get("example_answer", {})
    piec_obj = obj.get("piec", {})
    skills_obj = obj.get("skills", {})

    if not isinstance(nature_obj, dict):
        nature_obj = {"label": nature_obj}
    if not isinstance(fmt_obj, dict):
        fmt_obj = {"value": fmt_obj}
    if not isinstance(example_obj, dict):
        example_obj = {"value": example_obj}
    if not isinstance(piec_obj, dict):
        piec_obj = {"category": piec_obj}
    if not isinstance(skills_obj, dict):
        skills_obj = {"items": skills_obj}

    return {
        "question_nature": _normalize_nature(nature_obj.get("label"), text),
        "question_nature_rationale": _clean(nature_obj.get("rationale"), 300),
        "answer_format": _clean(fmt_obj.get("value")),
        "answer_format_rationale": _clean(fmt_obj.get("rationale"), 300),
        "example_answer": _clean(example_obj.get("value")),
        "example_answer_rationale": _clean(example_obj.get("rationale"), 300),
        "piec": _normalize_piec(piec_obj.get("category"), text),
        "piec_rationale": _clean(piec_obj.get("rationale"), 300),
        "skills": _normalize_skills(skills_obj.get("items"), text),
        "skills_rationale": _clean(skills_obj.get("rationale"), 300),
        "raw": (text or "").strip(),
    }

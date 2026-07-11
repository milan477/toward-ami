"""Reusable parsers for structured model answers."""

from __future__ import annotations

import json
import re
from typing import Any

PIAC_CATEGORIES = {"perceptual", "inferential", "affective", "contextual"}
QUESTION_NATURES = {"tfq", "mcq", "mlc", "oeq"}


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
        "tf": "tfq",
        "t_f": "tfq",
        "true/false": "tfq",
        "true_false": "tfq",
        "true_or_false": "tfq",
        "yes_no": "tfq",
        "binary": "tfq",
        "multiple_choice": "mcq",
        "multiple_choice_question": "mcq",
        "choice": "mcq",
        "multi_label": "mlc",
        "multilabel": "mlc",
        "label": "mlc",
        "specific_label": "mlc",
        "open": "oeq",
        "open_ended": "oeq",
        "open_ended_question": "oeq",
        "free_form": "oeq",
        "oeq": "oeq",
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


def _normalize_piac(value: Any, text: str) -> str:
    piac = _clean(value).lower()
    if piac in PIAC_CATEGORIES:
        return piac
    return next((c for c in PIAC_CATEGORIES if re.search(rf"\b{c}\b", text, re.I)), "")


def normalize_piac(value: Any, text: str = "") -> str:
    return _normalize_piac(value, text)


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
    piac_obj = obj.get("piac", {})
    skills_obj = obj.get("skills", {})

    if not isinstance(nature_obj, dict):
        nature_obj = {"label": nature_obj}
    if not isinstance(fmt_obj, dict):
        fmt_obj = {"value": fmt_obj}
    if not isinstance(example_obj, dict):
        example_obj = {"value": example_obj}
    if not isinstance(piac_obj, dict):
        piac_obj = {"category": piac_obj}
    if not isinstance(skills_obj, dict):
        skills_obj = {"items": skills_obj}

    return {
        "question_nature": _normalize_nature(nature_obj.get("label"), text),
        "question_nature_rationale": _clean(nature_obj.get("rationale"), 300),
        "answer_format": _clean(fmt_obj.get("value")),
        "answer_format_rationale": _clean(fmt_obj.get("rationale"), 300),
        "example_answer": _clean(example_obj.get("value")),
        "example_answer_rationale": _clean(example_obj.get("rationale"), 300),
        "piac": _normalize_piac(piac_obj.get("category"), text),
        "piac_rationale": _clean(piac_obj.get("rationale"), 300),
        "skills": _normalize_skills(skills_obj.get("items"), text),
        "skills_rationale": _clean(skills_obj.get("rationale"), 300),
        "raw": (text or "").strip(),
    }

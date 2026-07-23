"""Structural normalization for open-ended enhancement dimensions."""

from __future__ import annotations

import json
import re


def creator_context(row: dict) -> str:
    """Return all benchmark-creator categories for the enhancement prompt."""
    entries: list[tuple[str, str]] = []
    for key, raw in row.items():
        if not re.fullmatch(r"category_[1-9][0-9]*_[a-z0-9_]+", str(key)):
            continue
        value = str(raw or "").strip()
        if value and value.lower() != "nan":
            entries.append((str(key), value))
    return "\n".join(f"- {key}: {value}" for key, value in entries) or "- none"


def _open_label(value, limit: int = 80) -> str:
    """Clean an AI-selected label without mapping it to a fixed vocabulary."""
    if isinstance(value, (list, dict, tuple)):
        return ""
    return " ".join(str(value or "").split()).casefold()[:limit]


def normalize_action_content(value) -> list[list[str]]:
    """Validate and clean up to five open-ended ``[action, content]`` pairs."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        return []

    pairs: list[list[str]] = []
    for item in value:
        if isinstance(item, dict):
            raw_action = item.get("action")
            raw_content = item.get("content")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            raw_action, raw_content = item
        else:
            continue
        pair = [_open_label(raw_action), _open_label(raw_content)]
        if all(pair) and pair not in pairs:
            pairs.append(pair)
        if len(pairs) == 5:
            break
    return pairs

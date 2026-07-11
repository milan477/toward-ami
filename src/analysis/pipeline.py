"""Orchestrate benchmark analysis.

The pipeline currently turns:
    <name>_normalized_selected.csv

into:
    <name>_normalized_selected_annotated.csv

by delegating the question-level annotations to ``annotate.py``.
"""

from __future__ import annotations

from pathlib import Path

from src.config import DEFAULT_JUDGE_SPEC, DEFAULT_MODALITY
from src.analysis.annotate import annotate


def run(
    name: str,
    modality: str | None = DEFAULT_MODALITY,
    limit: int | None = None,
    *,
    judge_spec: str = DEFAULT_JUDGE_SPEC,
    overwrite: bool = False,
) -> Path:
    return annotate(
        name,
        modality=modality,
        limit=limit,
        judge_spec=judge_spec,
        overwrite=overwrite,
    )

"""Orchestrate benchmark analysis.

The pipeline turns:
    <name>_normalized_selected.csv

into:
    <name>_normalized_selected_enhanced.csv

by transcribing eligible audio, producing open-ended and imperative question
representations, and then delegating the LLM-derived dimensions to ``annotate.py``.
"""

from __future__ import annotations

from pathlib import Path

from src.config import DEFAULT_JUDGE_SPEC
from src.analysis.annotate import enhance


def run(
    name: str,
    modality: str | None = None,
    limit: int | None = None,
    *,
    judge_spec: str = DEFAULT_JUDGE_SPEC,
    transcriber_spec: str | None = None,
    rewriter_spec: str | None = None,
    task_rewriter_spec: str | None = None,
    overwrite: bool = False,
) -> Path:
    return enhance(
        name,
        modality=modality,
        limit=limit,
        judge_spec=judge_spec,
        transcriber_spec=transcriber_spec,
        rewriter_spec=rewriter_spec,
        task_rewriter_spec=task_rewriter_spec,
        overwrite=overwrite,
    )

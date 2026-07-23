"""Shared project constants for src commands."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DATASET = "mmar"
DEFAULT_MODALITY = "music"
DEFAULT_JUDGE_SPEC = "local"
DEFAULT_RUNNER_MODEL = "af-next"

DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "paper" / "figures"

DEFAULT_SELECTED_DATA = DATA_DIR / "benchmarks" / DEFAULT_DATASET / f"{DEFAULT_DATASET}_normalized_selected.csv"
DEFAULT_ENHANCED_DATA = (
    DATA_DIR / "benchmarks" / DEFAULT_DATASET
    / f"{DEFAULT_DATASET}_normalized_selected_enhanced.csv"
)
# Backwards-compatible import used by existing experiment commands.
DEFAULT_ANNOTATED_DATA = DEFAULT_ENHANCED_DATA
DEFAULT_FRONTEND_RUN_DIR = DATA_DIR / "model_runs"

BENCHMARK_ITEM_COLS = [
    "bench",
    "focus",
    "question",
    "question_oeq",
    "question_task",
    "answer",
    "answer_oeq",
    "distractors",
    "url",
    "input_modality",
    "output_modality",
    "transcription",
    "action_content",
    "piec",
    "question_nature",
    "answer_format",
    "example_incorrect_answer",
]

ANALYSIS_COLS = [
    "action_content",
    "piec",
    "question_nature",
    "answer_format",
    "example_incorrect_answer",
]

MCQ_MAX_TOKENS = 16
OEQ_MAX_TOKENS = 192
JUDGE_MAX_TOKENS = 160
PIEC_JUDGE_MAX_TOKENS = 220
API_RETRIES = 3

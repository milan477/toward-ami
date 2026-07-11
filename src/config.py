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
DEFAULT_ANNOTATED_DATA = (
    DATA_DIR / "benchmarks" / DEFAULT_DATASET / f"{DEFAULT_DATASET}_normalized_selected_annotated.csv"
)
DEFAULT_FRONTEND_RUN_DIR = DATA_DIR / "model_runs"

BENCHMARK_ITEM_COLS = [
    "benchmark",
    "question",
    "question_type",
    "correct_answer",
    "distractors",
    "audio_url",
    "category_1",
    "category_2",
    "category_3",
    "category_4",
    "length_type",
    "skills",
]

ANALYSIS_COLS = [
    "qid",
    "question_nature",
    "question_nature_rationale",
    "answer_format",
    "answer_format_rationale",
    "example_answer",
    "example_answer_rationale",
    "category",
    "piac",
    "category_auto",
    "category_rationale",
    "skills",
    "skills_rationale",
    "eval_strategy",
]

MCQ_MAX_TOKENS = 16
OEQ_MAX_TOKENS = 192
JUDGE_MAX_TOKENS = 160
PIAC_JUDGE_MAX_TOKENS = 220
API_RETRIES = 3

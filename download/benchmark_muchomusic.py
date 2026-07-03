"""Download + normalize MuChoMusic (https://huggingface.co/datasets/mulab-mir/muchomusic).

MuChoMusic ships as a single CSV (muchomusic.csv, 1187 items). It does not host
audio itself: every question is grounded in a clip from an external dataset
(``musiccaps`` or ``sdd`` = Song Describer Dataset), identified by
``dataset`` + ``dataset_identifier``.

Each row has:
  question_id, question, correct_answer, distractor_{1,2,3}_answer,
  dataset, dataset_identifier, num_annotations,
  correct, distractor1, distractor2, distractor3   (per-option human accuracy),
  odd_question (fraction of annotators flagging the item as malformed),
  genre, music_knowledge (JSON list), music_reasoning (JSON list)

Normalization choices
---------------------
- question_type : always "mcq" (one correct + three distractors).
- correct_answer: correct_answer column, resolved defensively.
- distractors   : the three distractor_*_answer columns.
- audio_url     : "<dataset>:<dataset_identifier>" (no audio is hosted here).
- category_1/2/3: genre → (unused) → (unused). The skill taxonomies are
                  multi-valued, so they go in extra columns instead.
- extra columns : music_knowledge, music_reasoning (JSON lists), dataset,
                  odd_question.
"""

import ast
import json

import pandas as pd
from huggingface_hub import hf_hub_download

from common import (
    clean_text,
    resolve_correct_answer,
    to_distractors,
    write_normalized,
    write_raw,
)

NAME     = "muchomusic"
HF_REPO  = "mulab-mir/muchomusic"
CSV_FILE = "muchomusic.csv"


def _fetch_df() -> pd.DataFrame:
    path = hf_hub_download(HF_REPO, CSV_FILE, repo_type="dataset")
    return pd.read_csv(path)


def _skills(value) -> str:
    """The source stores skill lists as a string repr of a Python list."""
    try:
        items = ast.literal_eval(value) if isinstance(value, str) else value
    except (ValueError, SyntaxError):
        items = []
    items = items if isinstance(items, (list, tuple)) else []
    return json.dumps([clean_text(s) for s in items if clean_text(s)],
                      ensure_ascii=False)


def _normalize_row(row: dict) -> dict:
    choices = [
        row.get("correct_answer"),
        row.get("distractor_1_answer"),
        row.get("distractor_2_answer"),
        row.get("distractor_3_answer"),
    ]
    correct = resolve_correct_answer(row.get("correct_answer"), choices)
    return {
        "benchmark":       NAME,
        "question":        clean_text(row.get("question", "")),
        "question_type":   "mcq",
        "correct_answer":  correct,
        "distractors":     to_distractors(choices, correct),
        "audio_url":       f"{clean_text(row.get('dataset'))}:{clean_text(row.get('dataset_identifier'))}",
        "category_1":      clean_text(row.get("genre", "")),
        "category_2":      "",
        "category_3":      "",
        "music_knowledge": _skills(row.get("music_knowledge")),
        "music_reasoning": _skills(row.get("music_reasoning")),
        "audio_source":    clean_text(row.get("dataset", "")),
        "odd_question":    row.get("odd_question"),
    }


def download_muchomusic() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    df = _fetch_df()

    # Raw: store exactly as is.
    write_raw(NAME, df)

    # Normalized: canonical schema + MuChoMusic extras.
    write_normalized(NAME, [_normalize_row(r) for r in df.to_dict("records")])


if __name__ == "__main__":
    download_muchomusic()

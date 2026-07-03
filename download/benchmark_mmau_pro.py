"""Download + normalize MMAU-Pro (https://huggingface.co/datasets/gamma-lab-umd/MMAU-Pro).

MMAU-Pro ships as a single parquet (test.parquet, 5305 items) plus an audio
archive (data.zip). We only need the parquet; audio is referenced by audio_path.

Each parquet row has:
  id, audio_path (array of paths), question, answer, choices (array),
  length_type, perceptual_skills (array), reasoning_skills (array),
  category, transcription, task_classification, task_identifier, kwargs, sub-cat

Notable quirks
--------------
- choices is empty for 215 open-ended rows  → question_type "oeq".
- answer is null for 87 instruction-following rows → correct_answer "".
- audio_path is an array; 456 rows reference more than one clip.
- perceptual_skills / reasoning_skills are multi-valued arrays.

Normalization choices
---------------------
- audio_url     : audio_path clips joined with "; ".
- category_1/2/3: category → sub-cat → (unused; MMAU-Pro has no 3rd level).
- extra columns : perceptual_skills, reasoning_skills (JSON lists), length_type.
"""

import json

import pandas as pd
from huggingface_hub import hf_hub_download

from common import (
    as_list,
    clean_text,
    resolve_correct_answer,
    to_distractors,
    write_normalized,
    write_raw,
)

NAME         = "mmau_pro"
HF_REPO      = "gamma-lab-umd/MMAU-Pro"
PARQUET_FILE = "test.parquet"


def _fetch_df() -> pd.DataFrame:
    path = hf_hub_download(HF_REPO, PARQUET_FILE, repo_type="dataset")
    return pd.read_parquet(path)


def _join_audio(audio_path) -> str:
    return "; ".join(clean_text(p) for p in as_list(audio_path) if clean_text(p))


def _skills(value) -> str:
    return json.dumps([clean_text(s) for s in as_list(value) if clean_text(s)],
                      ensure_ascii=False)


def _normalize_row(row: dict) -> dict:
    choices = as_list(row.get("choices"))
    correct = resolve_correct_answer(row.get("answer"), choices)
    return {
        "benchmark":         NAME,
        "question":          clean_text(row.get("question", "")),
        "question_type":     "mcq" if choices else "oeq",
        "correct_answer":    correct,
        "distractors":       to_distractors(choices, correct),
        "audio_url":         _join_audio(row.get("audio_path")),
        "category_1":        clean_text(row.get("category", "")),
        "category_2":        clean_text(row.get("sub-cat", "")),
        "category_3":        "",
        "skills":            _skills(row.get("perceptual_skills")) + _skills(row.get("reasoning_skills")),
        "length_type":       clean_text(row.get("length_type", "")),
    }


def download_mmau_pro() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    df = _fetch_df()

    # Raw: store exactly as is (arrays JSON-serialized by write_raw).
    write_raw(NAME, df)

    # Normalized: canonical schema + MMAU-Pro extras.
    write_normalized(NAME, [_normalize_row(r) for r in df.to_dict("records")])


if __name__ == "__main__":
    download_mmau_pro()

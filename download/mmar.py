"""Download + normalize MMAR (https://huggingface.co/datasets/BoJack/MMAR).

MMAR ships as a single metadata file (MMAR-meta.json, 1000 items) plus an audio
tarball (mmar-audio.tar.gz). We only need the metadata for the catalog/analysis;
the audio is referenced by ``audio_path``.

Each metadata item has:
  id, audio_path, question, choices (list), answer (option text),
  modality, category, sub-category, language, source, url, timestamp

Normalization choices
---------------------
- question_type : "mcq" when choices are present, else "oeq".
- correct_answer: the answer is already option text; resolved defensively.
- audio_url     : audio_path (the clip the question is about). The source video
                  url + timestamp are preserved in the raw CSV.
- category_1/2/3: modality → category → sub-category.
"""

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

NAME      = "mmar"
HF_REPO   = "BoJack/MMAR"
META_FILE = "MMAR-meta.json"


def _fetch_meta() -> list[dict]:
    path = hf_hub_download(HF_REPO, META_FILE, repo_type="dataset")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _normalize_row(item: dict) -> dict:
    choices = item.get("choices") or []
    correct = resolve_correct_answer(item.get("answer", ""), choices)
    return {
        "benchmark":      NAME,
        "question":       clean_text(item.get("question", "")),
        "question_type":  "mcq" if choices else "oeq",
        "correct_answer": correct,
        "distractors":    to_distractors(choices, correct),
        "audio_url":      clean_text(item.get("audio_path", "")),
        "category_1":     clean_text(item.get("modality", "")),
        "category_2":     clean_text(item.get("category", "")),
        "category_3":     clean_text(item.get("sub-category", "")),
    }


def download_mmar() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    meta = _fetch_meta()

    # Raw: store exactly as is (column order preserved from the source items).
    write_raw(NAME, pd.DataFrame(meta))

    # Normalized: canonical schema.
    write_normalized(NAME, [_normalize_row(item) for item in meta])


if __name__ == "__main__":
    download_mmar()

"""Download + normalize MMAU test-mini.

Source: https://huggingface.co/datasets/gamma-lab-umd/MMAU-test-mini
"""

import json
from pathlib import Path

import pandas as pd

from common import (
    AUDIO_DIR,
    as_list,
    clean_text,
    resolve_correct_answer,
    to_distractors,
    write_normalized,
    write_raw,
)

NAME = "mmau"
HF_REPO = "gamma-lab-umd/MMAU-test-mini"
PARQUET_FILE = "test_mini.parquet"


def _fetch_df() -> pd.DataFrame:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(HF_REPO, PARQUET_FILE, repo_type="dataset")
    return pd.read_parquet(path)


def _attrs(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _audio_path(row: dict, attrs: dict) -> str:
    ident = clean_text(attrs.get("id")) or str(row.get("_row_id", ""))
    return f"{ident}.wav"


def _raw_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for i, row in enumerate(df.to_dict("records")):
        attrs = _attrs(row.get("other_attributes"))
        ctx = row.get("context") or {}
        rows.append({
            "_row_id": i,
            "id": clean_text(attrs.get("id")),
            "instruction": row.get("instruction", ""),
            "choices": row.get("choices"),
            "answer": row.get("answer", ""),
            "audio_path": _audio_path({"_row_id": i}, attrs),
            "audio_bytes": len(ctx.get("bytes") or b""),
            "other_attributes": row.get("other_attributes", ""),
        })
    return rows


def _normalize_row(row: dict, idx: int) -> dict:
    attrs = _attrs(row.get("other_attributes"))
    choices = as_list(row.get("choices"))
    correct = resolve_correct_answer(row.get("answer", ""), choices)
    return {
        "benchmark": NAME,
        "question": clean_text(row.get("instruction", "")),
        "question_type": "mcq" if choices else "oeq",
        "correct_answer": correct,
        "distractors": to_distractors(choices, correct),
        "audio_url": _audio_path({"_row_id": idx}, attrs),
        "category_1": clean_text(attrs.get("task", "")),
        "category_2": clean_text(attrs.get("category", "")),
        "category_3": clean_text(attrs.get("sub-category", "")),
        "category_4": clean_text(attrs.get("difficulty", "")),
        "source_dataset": clean_text(attrs.get("dataset", "")),
        "split": clean_text(attrs.get("split", "")),
        "source_id": clean_text(attrs.get("id", "")),
    }


def download_mmau() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    df = _fetch_df()
    write_raw(NAME, pd.DataFrame(_raw_rows(df)))
    rows = [_normalize_row(row, i) for i, row in enumerate(df.to_dict("records"))]
    write_normalized(NAME, rows)


def download_mmau_audio() -> Path:
    df = _fetch_df()
    out_dir = AUDIO_DIR / NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    for i, row in enumerate(df.to_dict("records")):
        attrs = _attrs(row.get("other_attributes"))
        rel = _audio_path({"_row_id": i}, attrs)
        out = out_dir / rel
        if out.exists() and out.stat().st_size > 0:
            continue
        audio = row.get("context") or {}
        data = audio.get("bytes") or b""
        if data:
            out.write_bytes(data)
            done += 1
    print(f"  audio      → {out_dir}  ({done} written)")
    return out_dir


if __name__ == "__main__":
    from clean import clean_dataset

    download_mmau()
    clean_dataset(NAME)
    download_mmau_audio()

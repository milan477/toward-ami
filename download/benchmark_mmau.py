"""Download + normalize MMAU test-mini.

Source: https://huggingface.co/datasets/gamma-lab-umd/MMAU-test-mini
"""

from __future__ import annotations

import json
from pathlib import Path

from download.common import (
    AUDIO_DIR,
    as_list,
    bench_path,
    clean_text,
    focus_values,
    frame_records,
    normalized_record,
    read_raw_records,
    resolve_correct_answer,
    to_distractors,
    write_normalized,
    write_raw,
)

NAME = "mmau"
HF_REPO = "gamma-lab-umd/MMAU-test-mini"
PARQUET_FILE = "test_mini.parquet"


def _fetch_df():
    import pandas as pd

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


def _raw_rows(df) -> list[dict]:
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
    distractors = json.loads(to_distractors(choices, correct))
    task = clean_text(attrs.get("task", ""))
    category = clean_text(attrs.get("category", ""))
    subcategory = clean_text(attrs.get("sub-category", ""))
    return normalized_record(
        bench=NAME,
        focus=focus_values(task),
        question=row.get("instruction", ""),
        answer=[correct] if correct else [],
        distractors=distractors,
        url=[_audio_path({"_row_id": idx}, attrs)],
        categories={
            "category_1_category": category,
            "category_2_subcategory": subcategory,
            "category_3_difficulty": clean_text(attrs.get("difficulty", "")),
        },
    )


def download_mmau() -> None:
    import pandas as pd

    print(f"[{NAME}] downloading from {HF_REPO} …")
    df = _fetch_df()
    raw_rows = _raw_rows(df)
    write_raw(NAME, pd.DataFrame(raw_rows))
    normalize_mmau(pd.DataFrame(raw_rows))


def normalize_mmau(df=None):
    """Normalize the local raw MMAU CSV without downloading it again."""
    rows = frame_records(df) if df is not None else read_raw_records(NAME)
    return write_normalized(NAME, [_normalize_row(row, i) for i, row in enumerate(rows)])


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

"""Download + normalize PARSA-Bench.

Source: https://huggingface.co/datasets/MohammadJRanjbar/PARSA-Bench

The repository is gated. The loader works once the local Hugging Face token has
access to the dataset.
"""

from __future__ import annotations

import json
from pathlib import Path

from download.common import (
    AUDIO_DIR,
    bench_path,
    clean_text,
    frame_records,
    normalized_record,
    read_raw_records,
    resolve_correct_answer,
    to_distractors,
    write_normalized,
    write_raw,
)

NAME = "parsa_bench"
HF_REPO = "MohammadJRanjbar/PARSA-Bench"
CSV_FILES = [
    "ASR/ASR.csv",
    "Entity-Recognition/Entity-Recognition.csv",
    "Intent-Classification/Intent-Classification.csv",
    "Translation-EN-FA/Translation-EN-FA.csv",
    "Translation-FA-EN/Translation-FA-EN.csv",
]


def _download_file(path: str) -> str:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import GatedRepoError

    try:
        return hf_hub_download(HF_REPO, path, repo_type="dataset")
    except GatedRepoError as exc:
        raise RuntimeError(
            f"{HF_REPO} is gated. Request access on Hugging Face and run "
            "`hf auth login` with an authorized token before downloading PARSA-Bench."
        ) from exc


def _read_source():
    import pandas as pd

    frames = []
    for path in CSV_FILES:
        local = _download_file(path)
        df = pd.read_csv(local)
        df["task_file"] = path
        df["task"] = Path(path).parts[0]
        frames.append(df)
    return pd.concat(frames, ignore_index=True, sort=False)


def _first(row: dict, names: list[str]) -> str:
    lower = {str(k).lower().strip(): k for k in row}
    for name in names:
        key = lower.get(name.lower())
        if key is not None:
            value = clean_text(row.get(key, ""))
            if value:
                return value
    return ""


def _question(row: dict) -> str:
    return _first(row, [
        "question", "instruction", "prompt", "input", "text", "sentence",
        "query", "utterance", "transcription",
    ])


def _answer(row: dict) -> str:
    return _first(row, [
        "answer", "label", "output", "target", "gold", "reference",
        "translation", "intent", "entity", "transcription",
    ])


def _choices(row: dict) -> list[str]:
    out = []
    for key, value in row.items():
        lk = str(key).lower()
        if lk.startswith("choice") or lk.startswith("option") or lk.startswith("distractor"):
            text = clean_text(value)
            if text:
                out.append(text)
    return out


def _audio_path(row: dict, idx: int) -> str:
    path = _first(row, [
        "audio", "audio_path", "audio file", "audio_file", "path", "file",
        "filename", "wav", "wav_path",
    ])
    if path:
        return path.replace("\\", "/").lstrip("./")
    task = clean_text(row.get("task", "audio"))
    return f"{task}/unknown_{idx:06d}.wav"


def _normalize_row(row: dict, idx: int) -> dict:
    choices = _choices(row)
    correct = resolve_correct_answer(_answer(row), choices)
    task = clean_text(row.get("task", ""))
    distractors = json.loads(to_distractors(choices, correct))
    return normalized_record(
        bench=NAME,
        focus=["speech"],
        question=_question(row),
        answer=[correct] if correct else [],
        distractors=distractors,
        url=[_audio_path(row, idx)],
        categories={
            "category_1_task": task,
            "category_2_task_file": clean_text(row.get("task_file", "")),
        },
    )


def download_parsa_bench() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    df = _read_source()
    write_raw(NAME, df)
    normalize_parsa_bench(df)


def normalize_parsa_bench(df=None):
    """Normalize local PARSA-Bench raw data without accessing its gated repo."""
    rows = frame_records(df) if df is not None else read_raw_records(NAME)
    return write_normalized(NAME, [_normalize_row(row, i) for i, row in enumerate(rows)])


def download_parsa_bench_audio() -> Path:
    df = _read_source()
    out_dir = AUDIO_DIR / NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for idx, row in enumerate(df.to_dict("records")):
        rel = _audio_path(row, idx)
        if "unknown_" in rel:
            continue
        source = rel if "/" in rel else f"{clean_text(row.get('task', ''))}/Audios/{rel}"
        try:
            local = _download_file(source)
        except Exception:
            continue
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > 0:
            continue
        target.write_bytes(Path(local).read_bytes())
        written += 1
    print(f"  audio      → {out_dir}  ({written} written)")
    return out_dir


if __name__ == "__main__":
    from clean import clean_dataset

    download_parsa_bench()
    clean_dataset(NAME)
    download_parsa_bench_audio()

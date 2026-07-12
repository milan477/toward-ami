"""Download + normalize PitchBench.

Source: https://huggingface.co/datasets/pitchbench-authors/PitchBench
"""

from pathlib import Path

import pandas as pd

from common import AUDIO_DIR, clean_text, write_normalized, write_raw

NAME = "pitchbench"
HF_REPO = "pitchbench-authors/PitchBench"

ANSWER_COLUMNS = {
    "midi": ("prompt_midi", "gt_midi"),
    "abc": ("prompt_abc", "gt_abc"),
    "solfege": ("prompt_solfege", "gt_solfege"),
    "freq": ("prompt_freq", "gt_freq"),
}


def _parquet_files() -> list[str]:
    from huggingface_hub import HfApi

    return sorted(
        f for f in HfApi().list_repo_files(HF_REPO, repo_type="dataset")
        if f.endswith(".parquet")
    )


def _fetch_subset(path: str) -> pd.DataFrame:
    from huggingface_hub import hf_hub_download

    local = hf_hub_download(HF_REPO, path, repo_type="dataset")
    return pd.read_parquet(local)


def _subset(path: str) -> str:
    return Path(path).parts[0]


def _subset_skill(subset: str) -> str:
    """Human-readable tested skill from names like pitchbench_a1_single_pitch_id."""
    label = subset
    if label.startswith("pitchbench_"):
        label = label.removeprefix("pitchbench_")
    label = label.split("_", 1)[1] if "_" in label else label
    return clean_text(label.replace("_", " ")).capitalize()


def _source_label(source: str) -> str:
    return clean_text(str(source or "").replace("_", " ")).capitalize()


def _audio_name(row: dict, idx: int) -> str:
    audio = row.get("audio") or {}
    path = clean_text(audio.get("path", ""))
    return path or f"audio_{idx:06d}.wav"


def _audio_url(subset: str, row: dict, idx: int) -> str:
    return f"{subset}/{_audio_name(row, idx)}"


def _raw_value(value):
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {k: _raw_value(v) for k, v in value.items() if k != "bytes"}
    if isinstance(value, (list, tuple)):
        return [_raw_value(v) for v in value]
    return value


def _raw_rows() -> list[dict]:
    rows = []
    for parquet in _parquet_files():
        subset = _subset(parquet)
        df = _fetch_subset(parquet)
        print(f"  raw subset {subset} ({len(df)} rows)", flush=True)
        for idx, row in enumerate(df.to_dict("records")):
            audio = row.get("audio") or {}
            item = {k: _raw_value(v) for k, v in row.items() if k != "audio"}
            item.update({
                "subset": subset,
                "audio_path": _audio_url(subset, row, idx),
                "audio_bytes": len(audio.get("bytes") or b""),
            })
            rows.append(item)
    return rows


def _normalized_rows() -> list[dict]:
    rows = []
    for parquet in _parquet_files():
        subset = _subset(parquet)
        skill = _subset_skill(subset)
        df = _fetch_subset(parquet)
        print(f"  normalized subset {subset} ({len(df)} rows)", flush=True)
        for idx, row in enumerate(df.to_dict("records")):
            for answer_format, (prompt_col, answer_col) in ANSWER_COLUMNS.items():
                prompt = clean_text(row.get(prompt_col, ""))
                if not prompt:
                    continue
                rows.append({
                    "benchmark": NAME,
                    "question": prompt,
                    "question_type": "oeq",
                    "correct_answer": clean_text(row.get(answer_col, "")),
                    "distractors": "[]",
                    "audio_url": _audio_url(subset, row, idx),
                    "category_1": "music",
                    "category_2": _source_label(row.get("source", "")),
                    "category_3": skill,
                    "category_4": answer_format,
                    "subset": subset,
                    "skill": skill,
                    "answer_format": answer_format,
                    "gt_midi": clean_text(row.get("gt_midi", "")),
                    "gt_abc": clean_text(row.get("gt_abc", "")),
                    "gt_solfege": clean_text(row.get("gt_solfege", "")),
                    "gt_freq": clean_text(row.get("gt_freq", "")),
                    "source": clean_text(row.get("source", "")),
                })
    return rows


def download_pitchbench() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …", flush=True)
    write_raw(NAME, pd.DataFrame(_raw_rows()))
    write_normalized(NAME, _normalized_rows())


def download_pitchbench_audio() -> Path:
    out_dir = AUDIO_DIR / NAME
    written = 0
    for parquet in _parquet_files():
        subset = _subset(parquet)
        df = _fetch_subset(parquet)
        print(f"  audio subset {subset} ({len(df)} rows)", flush=True)
        for idx, row in enumerate(df.to_dict("records")):
            audio = row.get("audio") or {}
            data = audio.get("bytes") or b""
            if not data:
                continue
            out = out_dir / _audio_url(subset, row, idx)
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists() and out.stat().st_size > 0:
                continue
            out.write_bytes(data)
            written += 1
    print(f"  audio      → {out_dir}  ({written} written)")
    return out_dir


if __name__ == "__main__":
    from clean import clean_dataset

    download_pitchbench()
    clean_dataset(NAME)
    download_pitchbench_audio()

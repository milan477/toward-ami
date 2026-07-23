"""Download + normalize PitchBench.

Source: https://huggingface.co/datasets/pitchbench-authors/PitchBench
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

from download.common import (
    AUDIO_DIR,
    bench_path,
    clean_text,
    frame_records,
    normalized_record,
    read_raw_records,
    write_normalized,
    write_raw,
)

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


def _fetch_subset(path: str):
    import pandas as pd

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
    raw_path = clean_text(row.get("audio_path", ""))
    if raw_path:
        return Path(raw_path).name
    audio = row.get("audio") or {}
    path = clean_text(audio.get("path", ""))
    return path or f"audio_{idx:06d}.wav"


def _audio_url(subset: str, row: dict, idx: int) -> str:
    return f"{subset}/{_audio_name(row, idx)}"


def _combined_audio_bytes(row: dict) -> bytes:
    """Return a single WAV payload, combining split-reference prompts when needed."""
    audio = row.get("audio") or {}
    data = audio.get("bytes") or b""
    if data:
        return data

    parts = [
        (row.get("audio_1") or {}).get("bytes") or b"",
        (row.get("audio_2") or {}).get("bytes") or b"",
    ]
    parts = [part for part in parts if part]
    if not parts:
        return b""
    if len(parts) == 1:
        return parts[0]

    decoded = []
    params = None
    for part in parts:
        with wave.open(io.BytesIO(part), "rb") as src:
            current = src.getparams()
            frames = src.readframes(src.getnframes())
        if params is None:
            params = current
        elif current[:3] != params[:3] or current[4:] != params[4:]:
            return parts[0]
        decoded.append(frames)

    assert params is not None
    silence_frames = int(params.framerate * 0.5)
    silence = b"\x00" * silence_frames * params.nchannels * params.sampwidth
    out = io.BytesIO()
    with wave.open(out, "wb") as dst:
        dst.setparams(params)
        for idx, frames in enumerate(decoded):
            if idx:
                dst.writeframes(silence)
            dst.writeframes(frames)
    return out.getvalue()


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
                "audio_bytes": len(_combined_audio_bytes(row)),
            })
            rows.append(item)
    return rows


def _normalized_rows(raw_rows: list[dict] | None = None) -> list[dict]:
    rows = []
    if raw_rows is None:
        raw_rows = read_raw_records(NAME)
    by_subset: dict[str, list[dict]] = {}
    for row in raw_rows:
        by_subset.setdefault(clean_text(row.get("subset", "")), []).append(row)
    for subset, subset_rows in by_subset.items():
        print(f"  normalized subset {subset} ({len(subset_rows)} rows)", flush=True)
        for idx, row in enumerate(subset_rows):
            for answer_format, (prompt_col, answer_col) in ANSWER_COLUMNS.items():
                prompt = clean_text(row.get(prompt_col, ""))
                if not prompt:
                    continue
                answer = clean_text(row.get(answer_col, ""))
                rows.append(normalized_record(
                    bench=NAME,
                    focus=["music"],
                    question=prompt,
                    answer=[answer] if answer else [],
                    distractors=[],
                    url=[_audio_url(subset, row, idx)],
                    categories={
                        "category_1_subset": _subset_skill(subset),
                        "category_2_source": _source_label(row.get("source", "")),
                        "category_3_answer_format": answer_format,
                    },
                ))
    return rows


def download_pitchbench() -> None:
    import pandas as pd

    print(f"[{NAME}] downloading from {HF_REPO} …", flush=True)
    rows = _raw_rows()
    write_raw(NAME, pd.DataFrame(rows))
    normalize_pitchbench(pd.DataFrame(rows))


def normalize_pitchbench(df=None):
    """Normalize the local raw PitchBench CSV without downloading it again."""
    rows = None if df is None else frame_records(df)
    return write_normalized(NAME, _normalized_rows(rows))


def download_pitchbench_audio() -> Path:
    out_dir = AUDIO_DIR / NAME
    written = 0
    for parquet in _parquet_files():
        subset = _subset(parquet)
        df = _fetch_subset(parquet)
        print(f"  audio subset {subset} ({len(df)} rows)", flush=True)
        for idx, row in enumerate(df.to_dict("records")):
            data = _combined_audio_bytes(row)
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

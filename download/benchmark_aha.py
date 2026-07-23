"""Download and normalize AHA metadata without downloading its audio.

Source: https://huggingface.co/datasets/ASU-GSL/AHA

AHA provides preference pairs for audio-grounded temporal reasoning. Each item
contains an audio reference, caption, prompt, chosen answer, and counterfactual
rejected answer. The JSON metadata is small and separate from the multi-GB
``train.zip`` and ``test.zip`` audio archives; this downloader intentionally
fetches only ``train.json`` and ``test.json``. Both metadata splits are kept in
the raw CSV, while only the test split enters the normalized benchmark.

Normalization choices
---------------------
- answer        : a one-item list containing the source ``chosen`` response.
- distractors   : a one-item JSON list containing ``rejected``.
- url           : a one-item list containing the source audio reference.
- focus         : ``["sound"]`` (AHA is explicitly an audio-event benchmark).
- creator taxonomy: ``category_1_split``.
"""

import json
from urllib.request import urlopen

from download.common import (
    bench_path,
    clean_text,
    frame_records,
    normalized_record,
    read_raw_records,
    write_normalized,
    write_raw,
)

NAME = "aha"
HF_REPO = "ASU-GSL/AHA"
SPLIT_FILES = {
    "train": "train.json",
    "test": "test.json",
}
EVALUATION_SPLIT = "test"


def _fetch_split(split: str, filename: str) -> list[dict]:
    url = f"https://huggingface.co/datasets/{HF_REPO}/resolve/main/{filename}"
    with urlopen(url) as response:
        rows = json.load(response)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(
            f"Expected {HF_REPO}/{filename} to contain a JSON list of objects"
        )
    return [{**row, "split": split} for row in rows]


def _fetch_rows() -> list[dict]:
    rows = []
    for split, filename in SPLIT_FILES.items():
        split_rows = _fetch_split(split, filename)
        print(f"  metadata {split:<5} ({len(split_rows)} rows)", flush=True)
        rows.extend(split_rows)
    return rows


def _normalize_row(row: dict) -> dict:
    chosen = clean_text(row.get("chosen", ""))
    rejected = clean_text(row.get("rejected", ""))
    split = clean_text(row.get("split", ""))
    distractors = [rejected] if rejected and rejected.casefold() != chosen.casefold() else []
    return normalized_record(
        bench=NAME,
        focus=["sound"],
        question=row.get("prompt", ""),
        answer=[chosen] if chosen else [],
        distractors=distractors,
        url=[row.get("audio", "")],
        categories={"category_1_split": split},
    )


def download_aha() -> None:
    import pandas as pd

    print(
        f"[{NAME}] downloading metadata from {HF_REPO} (audio skipped) …",
        flush=True,
    )
    rows = _fetch_rows()
    write_raw(NAME, pd.DataFrame(rows))
    normalize_aha(pd.DataFrame(rows))


def normalize_aha(df=None):
    """Normalize the local raw AHA metadata without downloading it again."""
    rows = frame_records(df) if df is not None else read_raw_records(NAME)
    evaluation_rows = [row for row in rows if row.get("split") == EVALUATION_SPLIT]
    return write_normalized(NAME, [_normalize_row(row) for row in evaluation_rows])


if __name__ == "__main__":
    from clean import clean_dataset

    download_aha()
    clean_dataset(NAME)

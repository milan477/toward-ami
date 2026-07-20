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
- question_type : ``mcq`` when the rejected answer is distinct from the chosen
                  answer; ``oeq`` for the small number of degenerate source
                  pairs whose chosen and rejected answers are identical.
- correct_answer: the source ``chosen`` response.
- distractors   : a one-item JSON list containing ``rejected``.
- audio_url     : the source audio reference, preserved verbatim.
- category_1/2  : audio -> temporal reasoning.
- category_3    : a deterministic task label derived from the prompt.
- category_4    : source split (train or test).
"""

import json
from urllib.request import urlopen

import pandas as pd

from common import clean_text, to_distractors, write_normalized, write_raw

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


def _task(prompt: str) -> str:
    text = clean_text(prompt).lower()
    if "longest" in text or "duration" in text:
        return "duration comparison"
    if "how many" in text or "number of" in text or "more than once" in text:
        return "event counting"
    temporal_terms = (
        "order", "sequence", "chronological", "temporal structure",
        "first sound", "second sound", "last sound", "final sound",
        "beginning", "followed by", "passage of sound",
    )
    if any(term in text for term in temporal_terms):
        return "temporal order"
    return "temporal reasoning"


def _normalize_row(row: dict) -> dict:
    chosen = clean_text(row.get("chosen", ""))
    rejected = clean_text(row.get("rejected", ""))
    split = clean_text(row.get("split", ""))
    has_hard_negative = bool(rejected and rejected.casefold() != chosen.casefold())
    return {
        "benchmark": NAME,
        "question": clean_text(row.get("prompt", "")),
        "question_type": "mcq" if has_hard_negative else "oeq",
        "correct_answer": chosen,
        "distractors": to_distractors([rejected], chosen),
        "audio_url": clean_text(row.get("audio", "")),
        "category_1": "audio",
        "category_2": "temporal reasoning",
        "category_3": _task(row.get("prompt", "")),
        "category_4": split,
        "caption": clean_text(row.get("caption", "")),
        "rejected_answer": rejected,
        "split": split,
    }


def download_aha() -> None:
    print(
        f"[{NAME}] downloading metadata from {HF_REPO} (audio skipped) …",
        flush=True,
    )
    rows = _fetch_rows()
    write_raw(NAME, pd.DataFrame(rows))
    evaluation_rows = [row for row in rows if row["split"] == EVALUATION_SPLIT]
    write_normalized(NAME, [_normalize_row(row) for row in evaluation_rows])


if __name__ == "__main__":
    from clean import clean_dataset

    download_aha()
    clean_dataset(NAME)

"""Download + normalize HumMusQA.

Source: https://doi.org/10.5281/zenodo.18462524
"""

from pathlib import Path
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

import pandas as pd

from common import (
    AUDIO_DIR,
    clean_text,
    resolve_correct_answer,
    to_distractors,
    write_normalized,
    write_raw,
)

NAME = "hummusqa"
QA_URL = "https://zenodo.org/api/records/18462524/files/HumMusQA.csv/content"
METADATA_URL = "https://zenodo.org/api/records/18462524/files/metadata.csv/content"
AUDIO_EXCERPTS_URL = "https://zenodo.org/api/records/18462524/files/audio_excerpts.zip/content"
ARCHIVE_PATH = AUDIO_DIR / "_archives" / "hummusqa_audio_excerpts.zip"


def _track_id(song_link: str) -> str:
    return clean_text(song_link).rstrip("/").split("/")[-1]


def _audio_name(row: dict, idx: int) -> str:
    return f"q{idx + 1}_{_track_id(row.get('Song link', ''))}.mp3"


def _fetch_df() -> pd.DataFrame:
    qa = pd.read_csv(QA_URL)
    meta = pd.read_csv(METADATA_URL)
    meta = meta.rename(columns={"song_link": "Song link"})
    return qa.merge(meta, on="Song link", how="left")


def _normalize_row(row: dict, idx: int) -> dict:
    choices = [
        row.get("True answer"),
        row.get("Distractor 1"),
        row.get("Distractor 2"),
        row.get("Distractor 3"),
    ]
    correct = resolve_correct_answer(row.get("True answer"), choices)
    return {
        "benchmark": NAME,
        "question": clean_text(row.get("Question", "")),
        "question_type": "mcq",
        "correct_answer": correct,
        "distractors": to_distractors(choices, correct),
        "audio_url": _audio_name(row, idx),
        "category_1": "music",
        "category_2": clean_text(row.get("Main Category", "")),
        "category_3": clean_text(row.get("Secondary Categories", "")),
        "category_4": clean_text(row.get("Difficulty", "")),
        "track_id": _track_id(row.get("Song link", "")),
        "start_time": clean_text(row.get("start time", "")),
        "end_time": clean_text(row.get("end time", "")),
        "artist_name": clean_text(row.get("artist_name", "")),
        "song_name": clean_text(row.get("name", "")),
        "license": clean_text(row.get("license_ccurl", "")),
    }


def download_hummusqa() -> None:
    print(f"[{NAME}] downloading from Zenodo record 18462524 …", flush=True)
    df = _fetch_df()
    df = df.copy()
    df["audio_path"] = [_audio_name(r, i) for i, r in enumerate(df.to_dict("records"))]
    write_raw(NAME, df)
    write_normalized(NAME, [_normalize_row(r, i) for i, r in enumerate(df.to_dict("records"))])


def download_hummusqa_audio() -> Path:
    df = _fetch_df()
    out_dir = AUDIO_DIR / NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = [_audio_name(r, i) for i, r in enumerate(df.to_dict("records"))]
    missing = [name for name in wanted if not (out_dir / name).exists()]
    print(f"[{NAME}] {len(wanted)} excerpts referenced, {len(missing)} to fetch", flush=True)
    if not missing:
        print(f"  audio      → {out_dir}  (all present)", flush=True)
        return out_dir

    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ARCHIVE_PATH.exists() or ARCHIVE_PATH.stat().st_size == 0:
        print(f"  audio zip  → {ARCHIVE_PATH}", flush=True)
        with urlopen(AUDIO_EXCERPTS_URL) as response, ARCHIVE_PATH.open("wb") as out:
            downloaded = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if downloaded // (100 * 1024 * 1024) != (downloaded - len(chunk)) // (100 * 1024 * 1024):
                    print(f"  audio zip  … {downloaded / (1024 * 1024):.0f} MiB", flush=True)

    try:
        z = ZipFile(ARCHIVE_PATH)
        names = set(z.namelist())
    except BadZipFile:
        ARCHIVE_PATH.unlink(missing_ok=True)
        raise RuntimeError(f"Cached HumMusQA archive was corrupt; rerun to download it again: {ARCHIVE_PATH}")

    with z:
        fetched = 0
        for name in missing:
            member = f"audio_excerpts/{name}"
            if member not in names:
                continue
            with z.open(member) as src:
                (out_dir / name).write_bytes(src.read())
            fetched += 1
            if fetched % 25 == 0:
                print(f"  audio      … {fetched}/{len(missing)} fetched", flush=True)
    print(f"  audio      → {out_dir}  ({fetched} fetched)", flush=True)
    return out_dir


if __name__ == "__main__":
    from clean import clean_dataset

    download_hummusqa()
    clean_dataset(NAME)
    download_hummusqa_audio()

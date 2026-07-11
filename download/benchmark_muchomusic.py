"""Download + normalize MuChoMusic (https://huggingface.co/datasets/mulab-mir/muchomusic).

MuChoMusic ships as a single CSV (muchomusic.csv, 1187 items). It does not host
audio itself: every question is grounded in a clip from an external dataset
(``musiccaps`` or ``sdd`` = Song Describer Dataset), identified by
``dataset`` + ``dataset_identifier``.

Each row has:
  question_id, question, correct_answer, distractor_{1,2,3}_answer,
  dataset, dataset_identifier, num_annotations,
  correct, distractor1, distractor2, distractor3   (per-option human accuracy),
  odd_question (fraction of annotators flagging the item as malformed),
  genre, music_knowledge (JSON list), music_reasoning (JSON list)

Normalization choices
---------------------
- question_type : always "mcq" (one correct + three distractors).
- correct_answer: correct_answer column, resolved defensively.
- distractors   : the three distractor_*_answer columns.
- audio_url     : "<dataset>:<dataset_identifier>" (no audio is hosted here).
- category_1/2/3/4: genre → (unused) → (unused) → (unused). The skill taxonomies are
                  multi-valued, so they go in extra columns instead.
- extra columns : music_knowledge, music_reasoning (JSON lists), dataset,
                  odd_question.
"""

import ast
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from common import (
    AUDIO_DIR,
    bench_path,
    clean_text,
    resolve_correct_answer,
    to_distractors,
    write_normalized,
    write_raw,
)

NAME     = "muchomusic"
HF_REPO  = "mulab-mir/muchomusic"
CSV_FILE = "muchomusic.csv"

# Song Describer Dataset audio (Zenodo). Members: audio/<id%100>/<id>.2min.mp3
SDD_AUDIO_URL = "https://zenodo.org/api/records/10072001/files/audio.zip/content"
# MusicCaps clips are fixed 10 s segments of the source YouTube video.
MUSICCAPS_CLIP_S = 10


def _fetch_df() -> pd.DataFrame:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(HF_REPO, CSV_FILE, repo_type="dataset")
    return pd.read_csv(path)


def _skills(value) -> str:
    """The source stores skill lists as a string repr of a Python list."""
    try:
        items = ast.literal_eval(value) if isinstance(value, str) else value
    except (ValueError, SyntaxError):
        items = []
    items = items if isinstance(items, (list, tuple)) else []
    return json.dumps([clean_text(s) for s in items if clean_text(s)],
                      ensure_ascii=False)


def _normalize_row(row: dict) -> dict:
    choices = [
        row.get("correct_answer"),
        row.get("distractor_1_answer"),
        row.get("distractor_2_answer"),
        row.get("distractor_3_answer"),
    ]
    correct = resolve_correct_answer(row.get("correct_answer"), choices)
    return {
        "benchmark":       NAME,
        "question":        clean_text(row.get("question", "")),
        "question_type":   "mcq",
        "correct_answer":  correct,
        "distractors":     to_distractors(choices, correct),
        "audio_url":       f"{clean_text(row.get('dataset'))}:{clean_text(row.get('dataset_identifier'))}",
        "category_1":      clean_text(row.get("genre", "")),
        "category_2":      "",
        "category_3":      "",
        "category_4":      "",
        "music_knowledge": _skills(row.get("music_knowledge")),
        "music_reasoning": _skills(row.get("music_reasoning")),
        "audio_source":    clean_text(row.get("dataset", "")),
        "odd_question":    row.get("odd_question"),
    }


def download_muchomusic() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    df = _fetch_df()

    # Raw: store exactly as is.
    write_raw(NAME, df)

    # Normalized: canonical schema + MuChoMusic extras.
    write_normalized(NAME, [_normalize_row(r) for r in df.to_dict("records")])


def _sdd_member(track_id: str) -> str:
    """Member path of an SDD track inside the Zenodo audio.zip."""
    return f"audio/{int(track_id) % 100:02d}/{track_id}.2min.mp3"


def _download_sdd(ids: list[str], out_dir: Path, max_retries: int = 6) -> None:
    """Range-fetch SDD tracks from the Zenodo zip, reconnecting on drops."""
    from remotezip import RemoteIOError, RemoteZip

    out_dir.mkdir(parents=True, exist_ok=True)

    def remaining() -> list[str]:
        return [i for i in ids if not (out_dir / f"{i}.2min.mp3").exists()]

    print(f"  sdd: {len(ids)} tracks referenced, {len(remaining())} to fetch")
    not_found: set[str] = set()
    for attempt in range(1, max_retries + 1):
        todo = [i for i in remaining() if i not in not_found]
        if not todo:
            break
        try:
            with RemoteZip(SDD_AUDIO_URL) as z:
                names = set(z.namelist())
                for track_id in todo:
                    member = _sdd_member(track_id)
                    if member not in names:
                        not_found.add(track_id)
                        continue
                    with z.open(member) as src:
                        (out_dir / f"{track_id}.2min.mp3").write_bytes(src.read())
        except RemoteIOError as e:
            print(f"  sdd: connection dropped ({e}); reconnecting "
                  f"({attempt}/{max_retries}) …")
            continue

    fetched = sum(1 for i in ids if (out_dir / f"{i}.2min.mp3").exists())
    print(f"  sdd → {out_dir}  ({fetched}/{len(ids)} present)")
    if not_found:
        print(f"  WARNING: {len(not_found)} sdd tracks not found in zip")
    still = [i for i in remaining() if i not in not_found]
    if still:
        print(f"  WARNING: {len(still)} sdd tracks unfetched after "
              f"{max_retries} attempts; re-run to resume")


def _download_musiccaps(ids: list[str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ytdlp = shutil.which("yt-dlp")
    if ytdlp is None:
        print("  musiccaps: SKIPPED — yt-dlp not found on PATH")
        return

    missing = [i for i in ids if not (out_dir / f"{i}.wav").exists()]
    print(f"  musiccaps: {len(ids)} clips referenced, {len(missing)} to fetch")
    failed = []
    for n, clip_id in enumerate(missing, 1):
        ytid, start = clip_id.rsplit("_", 1)  # ytid may contain "_"/"-"
        start_s = int(start)
        section = f"*{start_s}-{start_s + MUSICCAPS_CLIP_S}"
        cmd = [
            ytdlp,
            "-x", "--audio-format", "wav",
            "--download-sections", section,
            "--force-keyframes-at-cuts",
            "--quiet", "--no-warnings", "--no-playlist",
            "-o", str(out_dir / f"{clip_id}.%(ext)s"),
            f"https://www.youtube.com/watch?v={ytid}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not (out_dir / f"{clip_id}.wav").exists():
            failed.append(clip_id)
        if n % 25 == 0:
            print(f"    musiccaps {n}/{len(missing)}  ({len(failed)} failed) …")

    print(f"  musiccaps → {out_dir}  ({len(missing) - len(failed)} fetched)")
    if failed:
        fail_log = out_dir.parent / "musiccaps_failed.txt"
        fail_log.write_text("\n".join(failed) + "\n")
        print(f"  WARNING: {len(failed)} musiccaps clips failed (likely removed "
              f"from YouTube); ids logged to {fail_log}")


def download_muchomusic_audio() -> Path:
    """Fetch MuChoMusic clips from SDD and MusicCaps source datasets."""
    out_dir = AUDIO_DIR / NAME
    selected = bench_path(NAME, "selected")
    if not selected.exists():
        raise FileNotFoundError(
            f"Missing {selected}. Run: python download/clean.py {NAME}"
        )
    df = pd.read_csv(selected)

    by_source: dict[str, list[str]] = {"sdd": [], "musiccaps": []}
    for url in df["audio_url"]:
        source, _, ident = str(url).partition(":")
        if source in by_source and ident and ident not in by_source[source]:
            by_source[source].append(ident)

    print(f"[{NAME}] {sum(len(v) for v in by_source.values())} unique clips "
          f"(sdd={len(by_source['sdd'])}, musiccaps={len(by_source['musiccaps'])})")
    _download_sdd(by_source["sdd"], out_dir / "sdd")
    _download_musiccaps(by_source["musiccaps"], out_dir / "musiccaps")
    return out_dir


if __name__ == "__main__":
    from clean import clean_dataset

    download_muchomusic()
    clean_dataset(NAME)
    download_muchomusic_audio()

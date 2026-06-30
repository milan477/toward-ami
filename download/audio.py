"""Download the audio clips referenced by the cleaned (music) subsets.

Reads data/cleaned/<name>.csv (see download/clean.py) and fetches only the audio
files those rows reference, into data/audio/<name>/. Files already present are
skipped, so re-runs are cheap and resumable.

The two datasets ship audio differently, so each has its own fetch strategy:

  mmar      single gzip tarball (mmar-audio.tar.gz, ~3 GB). gzip has no random
            access, so the whole tarball is downloaded once (HF-cached) and the
            ~323 music members are extracted from it.
  mmau_pro  single zip (data.zip, ~47 GB). zip has a central directory, so we
            use HTTP range requests (remotezip) to pull only the ~1.5k music
            members without downloading the full archive.
  muchomusic  hosts no audio itself; each clip lives in an external dataset
            (audio_url is "<source>:<id>"). sdd clips come from the Song
            Describer Dataset zip on Zenodo (range-fetched like mmau_pro);
            musiccaps clips are 10 s YouTube segments fetched with yt-dlp.

Usage
-----
python download/audio.py mmar        # one dataset
python download/audio.py all         # every registered dataset
python download/audio.py --list      # show registered datasets
"""

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download, hf_hub_url
from remotezip import RemoteIOError, RemoteZip

sys.path.insert(0, str(Path(__file__).parent))

from common import AUDIO_DIR, CLEAN_DIR, NORM_DIR

MMAR_REPO        = "BoJack/MMAR"
MMAR_AUDIO       = "mmar-audio.tar.gz"
MMAU_PRO_REPO    = "gamma-lab-umd/MMAU-Pro"
MMAU_PRO_AUDIO   = "data.zip"

# Song Describer Dataset audio (Zenodo). Members: audio/<id%100>/<id>.2min.mp3
SDD_AUDIO_URL    = "https://zenodo.org/api/records/10072001/files/audio.zip/content"
# MusicCaps clips are fixed 10 s segments of the source YouTube video.
MUSICCAPS_CLIP_S = 10


def _referenced_paths(name: str) -> list[str]:
    """Relative audio paths referenced by the cleaned subset of ``name``.

    audio_url holds one or more clips; mmau_pro stores them as a Python-list
    repr (e.g. "['data/uuid.wav']"), mmar as a plain "./audio/id.wav". Both may
    in principle carry several clips joined with "; ".
    """
    df = pd.read_csv(CLEAN_DIR / f"{name}.csv")
    paths: list[str] = []
    for url in df["audio_url"]:
        for chunk in str(url).split("; "):
            chunk = chunk.strip()
            if not chunk:
                continue
            if chunk.startswith("[") and chunk.endswith("]"):
                try:
                    paths.extend(str(p) for p in ast.literal_eval(chunk))
                    continue
                except (ValueError, SyntaxError):
                    pass
            paths.append(chunk)
    # normalize leading "./" and dedupe, preserving order
    seen, out = set(), []
    for p in paths:
        p = p.lstrip("./")
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _hf_headers() -> dict:
    tok = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def download_mmar_audio() -> Path:
    name = "mmar"
    out_dir = AUDIO_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = _referenced_paths(name)
    by_base = {Path(p).name: p for p in wanted}
    missing = {b for b in by_base if not (out_dir / b).exists()}
    print(f"[{name}] {len(wanted)} clips referenced, {len(missing)} to extract")
    if not missing:
        print(f"  audio      → {out_dir}  (all present)")
        return out_dir

    print(f"  fetching {MMAR_AUDIO} (~3 GB, cached by huggingface_hub) …")
    tar_path = hf_hub_download(MMAR_REPO, MMAR_AUDIO, repo_type="dataset")

    extracted = 0
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            base = Path(member.name).name
            if base in missing:
                src = tar.extractfile(member)
                if src is None:
                    continue
                (out_dir / base).write_bytes(src.read())
                extracted += 1
                missing.discard(base)
                if not missing:
                    break

    print(f"  audio      → {out_dir}  ({extracted} extracted)")
    if missing:
        print(f"  WARNING: {len(missing)} referenced clips not found in tarball")
    return out_dir


def download_mmau_pro_audio() -> Path:
    name = "mmau_pro"
    out_dir = AUDIO_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = _referenced_paths(name)
    missing = [p for p in wanted if not (out_dir / Path(p).name).exists()]
    print(f"[{name}] {len(wanted)} clips referenced, {len(missing)} to fetch")
    if not missing:
        print(f"  audio      → {out_dir}  (all present)")
        return out_dir

    url = hf_hub_url(MMAU_PRO_REPO, MMAU_PRO_AUDIO, repo_type="dataset")
    fetched, not_found = 0, []
    with RemoteZip(url, headers=_hf_headers()) as z:
        names = set(z.namelist())
        # map basename stem → member, for ext-mismatch fallback
        by_stem = {Path(n).stem: n for n in names}
        for rel in missing:
            member = rel if rel in names else by_stem.get(Path(rel).stem)
            if member is None:
                not_found.append(rel)
                continue
            with z.open(member) as src:
                (out_dir / Path(rel).name).write_bytes(src.read())
            fetched += 1
            if fetched % 100 == 0:
                print(f"    {fetched}/{len(missing)} …")

    print(f"  audio      → {out_dir}  ({fetched} fetched)")
    if not_found:
        print(f"  WARNING: {len(not_found)} referenced clips not found in zip")
    return out_dir


def _sdd_member(track_id: str) -> str:
    """Member path of an SDD track inside the Zenodo audio.zip."""
    return f"audio/{int(track_id) % 100:02d}/{track_id}.2min.mp3"


def _download_sdd(ids: list[str], out_dir: Path, max_retries: int = 6) -> None:
    """Range-fetch SDD tracks from the Zenodo zip.

    Zenodo's TLS layer drops long-lived range sessions intermittently, so on a
    connection error we reconnect and resume; files already on disk are skipped,
    making each attempt pick up where the last left off.
    """
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
    name = "muchomusic"
    out_dir = AUDIO_DIR / name
    df = pd.read_csv(NORM_DIR / f"{name}.csv")

    by_source: dict[str, list[str]] = {"sdd": [], "musiccaps": []}
    for url in df["audio_url"]:
        source, _, ident = str(url).partition(":")
        if source in by_source and ident and ident not in by_source[source]:
            by_source[source].append(ident)

    print(f"[{name}] {sum(len(v) for v in by_source.values())} unique clips "
          f"(sdd={len(by_source['sdd'])}, musiccaps={len(by_source['musiccaps'])})")
    _download_sdd(by_source["sdd"], out_dir / "sdd")
    _download_musiccaps(by_source["musiccaps"], out_dir / "musiccaps")
    return out_dir


DATASETS = {
    "mmar": download_mmar_audio,
    "mmau_pro": download_mmau_pro_audio,
    "muchomusic": download_muchomusic_audio,
}


def download_audio(name: str) -> None:
    if name == "all":
        for fn in DATASETS.values():
            fn()
        return
    if name not in DATASETS:
        raise ValueError(
            f"Dataset {name!r} not found. Available: {', '.join(sorted(DATASETS))}"
        )
    DATASETS[name]()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", help="Dataset name, or 'all'")
    parser.add_argument("--list", action="store_true", help="List registered datasets")
    args = parser.parse_args()

    if args.list or not args.dataset:
        print("Registered datasets:")
        for name in sorted(DATASETS):
            print(f"  {name}")
        sys.exit(0)

    download_audio(args.dataset)

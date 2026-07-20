"""Shared utilities for model querying and result paths."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.config import DATA_DIR, RESULTS_DIR, ROOT

AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".ogg"}


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def audio_stem(audio_url: str) -> str:
    return audio_url.split("/")[-1].rsplit(".", 1)[0]


def audio_name(audio_url: str) -> str:
    return audio_url.split("/")[-1]


def build_audio_index(audio_root: str | Path | None = None) -> dict[str, Path]:
    """Map every audio basename under ``audio_root`` to its path."""
    root = resolve_path(audio_root or DATA_DIR / "audio")
    index: dict[str, Path] = {}
    if not root.exists():
        return index
    for path in root.rglob("*"):
        if path.suffix.lower() in AUDIO_EXTENSIONS:
            index.setdefault(path.name, path)
    return index


def read_jsonl(path: Path, key: str = "qid") -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[rec[key]] = rec
    return out


def model_slug(model_spec: str) -> str:
    slug = model_spec.split(":", 1)[-1].split("/")[-1]
    return slug.replace("@", "-").replace(":", "-")


def infer_benchmark_name(data_path: Path) -> str:
    return data_path.parent.name or "benchmark"


RUN_STAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"


def run_stamp(when: datetime | None = None) -> str:
    """Return the local timestamp used as a run-directory name."""
    return (when or datetime.now()).strftime(RUN_STAMP_FORMAT)


def result_root(
    experiment: str,
    benchmark: str,
    model_spec: str,
) -> Path:
    """Return ``results/<experiment>/<benchmark>/<model>``."""
    return RESULTS_DIR / experiment / benchmark / model_slug(model_spec)


def result_dir(
    experiment: str,
    benchmark: str,
    model_spec: str,
    date: str,
) -> Path:
    """Return ``results/<experiment>/<benchmark>/<model>/<date>``.

    ``experiment`` should be the numbered module name, such as
    ``exp_0_mcq_oeq``. Forms and other run components belong inside this
    directory rather than changing the four identifying path dimensions.
    """
    if not date or Path(date).name != date:
        raise ValueError(f"Invalid result date/run id: {date!r}")
    return result_root(experiment, benchmark, model_spec) / date


def create_result_dir(
    experiment: str,
    benchmark: str,
    model_spec: str,
    date: str | None = None,
) -> Path:
    """Create a unique timestamped result directory without overwriting a run."""
    base_date = date or run_stamp()
    for suffix in range(1000):
        run_id = base_date if suffix == 0 else f"{base_date}_{suffix:02d}"
        path = result_dir(experiment, benchmark, model_spec, run_id)
        try:
            path.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return path
    raise RuntimeError(f"Could not allocate a unique run directory below {result_root(experiment, benchmark, model_spec)}")


def latest_result_dir(experiment: str, benchmark: str, model_spec: str) -> Path | None:
    """Return the newest timestamped run directory, if one exists."""
    root = result_root(experiment, benchmark, model_spec)
    runs = sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []
    return runs[-1] if runs else None

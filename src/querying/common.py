"""Shared utilities for model querying and result paths."""

from __future__ import annotations

import json
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


def result_dir(benchmark: str, model_spec: str, experiment: str) -> Path:
    return RESULTS_DIR / benchmark / model_slug(model_spec) / experiment

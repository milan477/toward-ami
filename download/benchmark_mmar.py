"""Download + normalize MMAR (https://huggingface.co/datasets/BoJack/MMAR).

MMAR ships as a single metadata file (MMAR-meta.json, 1000 items) plus an audio
tarball (mmar-audio.tar.gz). We only need the metadata for the catalog/analysis;
the audio is referenced by ``audio_path``.

Each metadata item has:
  id, audio_path, question, choices (list), answer (option text),
  modality, category, sub-category, language, source, url, timestamp

Normalization choices
---------------------
- question_type : "mcq" when choices are present, else "oeq".
- correct_answer: the answer is already option text; resolved defensively.
- audio_url     : audio_path (the clip the question is about). The source video
                  url + timestamp are preserved in the raw CSV.
- category_1/2/3/4: modality → category → sub-category → (unused).
"""

import json
import tarfile
from pathlib import Path

import pandas as pd

from common import (
    AUDIO_DIR,
    bench_path,
    clean_text,
    referenced_audio_paths,
    resolve_correct_answer,
    to_distractors,
    write_normalized,
    write_raw,
)

NAME      = "mmar"
HF_REPO   = "BoJack/MMAR"
META_FILE = "MMAR-meta.json"
AUDIO_FILE = "mmar-audio.tar.gz"


def _audio_reference_stage(stage: str | None = None) -> str:
    """Resolve which benchmark stage should drive audio extraction."""
    if stage:
        path = bench_path(NAME, stage)
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}.")
        return stage

    selected = bench_path(NAME, "selected")
    if selected.exists():
        return "selected"
    normalized = bench_path(NAME, "normalized")
    if normalized.exists():
        return "normalized"
    raise FileNotFoundError(
        f"Missing {selected} and {normalized}. Run: python download/run.py {NAME}"
    )


def _fetch_meta() -> list[dict]:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(HF_REPO, META_FILE, repo_type="dataset")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _normalize_row(item: dict) -> dict:
    choices = item.get("choices") or []
    correct = resolve_correct_answer(item.get("answer", ""), choices)
    return {
        "benchmark":      NAME,
        "question":       clean_text(item.get("question", "")),
        "question_type":  "mcq" if choices else "oeq",
        "correct_answer": correct,
        "distractors":    to_distractors(choices, correct),
        "audio_url":      clean_text(item.get("audio_path", "")),
        "category_1":     clean_text(item.get("modality", "")),
        "category_2":     clean_text(item.get("category", "")),
        "category_3":     clean_text(item.get("sub-category", "")),
        "category_4":     "",
    }


def download_mmar() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    meta = _fetch_meta()

    # Raw: store exactly as is (column order preserved from the source items).
    write_raw(NAME, pd.DataFrame(meta))

    # Normalized: canonical schema.
    write_normalized(NAME, [_normalize_row(item) for item in meta])


def download_mmar_audio(stage: str | None = None) -> Path:
    """Extract referenced MMAR clips from the dataset tarball."""
    from huggingface_hub import hf_hub_download

    out_dir = AUDIO_DIR / NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_stage = _audio_reference_stage(stage)
    wanted = referenced_audio_paths(NAME, stage=ref_stage)
    target_rels = set()
    missing = set()
    for rel in wanted:
        clean = rel.lstrip("./")
        base = Path(clean).name
        if not (out_dir / base).exists():
            target_rels.add(clean)
            missing.add(base)
    print(f"[{NAME}] {len(wanted)} clips referenced from {ref_stage}, {len(missing)} to extract")
    if not missing:
        print(f"  audio      → {out_dir}  (all present)")
        return out_dir

    print(f"  fetching {AUDIO_FILE} (~3 GB, cached by huggingface_hub) …")
    tar_path = hf_hub_download(HF_REPO, AUDIO_FILE, repo_type="dataset")

    extracted = 0
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            rel = member.name.lstrip("./")
            base = Path(rel).name
            if rel in target_rels or base in missing:
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


if __name__ == "__main__":
    from clean import clean_dataset

    download_mmar()
    clean_dataset(NAME)
    download_mmar_audio()

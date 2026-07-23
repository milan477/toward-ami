"""Download + normalize MMAR (https://huggingface.co/datasets/BoJack/MMAR).

MMAR ships as a single metadata file (MMAR-meta.json, 1000 items) plus an audio
tarball (mmar-audio.tar.gz). We only need the metadata for the catalog/analysis;
the audio is referenced by ``audio_path``.

Each metadata item has:
  id, audio_path, question, choices (list), answer (option text),
  modality, category, sub-category, language, source, url, timestamp

Normalization choices
---------------------
- answer: the source answer is resolved defensively and stored as a JSON list.
- url: a one-item JSON list containing `audio_path`.
- focus: atomic values extracted from source `modality`.
- creator categories: category, sub-category, language, and source are retained
  in descriptively named ordered columns.
"""

import json
import tarfile
from pathlib import Path

from download.common import (
    AUDIO_DIR,
    bench_path,
    clean_text,
    focus_values,
    frame_records,
    normalized_record,
    read_raw_records,
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
    distractors = json.loads(to_distractors(choices, correct))
    modality = clean_text(item.get("modality", ""))
    category = clean_text(item.get("category", ""))
    subcategory = clean_text(item.get("sub-category", ""))
    return normalized_record(
        bench=NAME,
        focus=focus_values(modality),
        question=item.get("question", ""),
        answer=[correct] if correct else [],
        distractors=distractors,
        url=[item.get("audio_path", "")],
        categories={
            "category_1_category": category,
            "category_2_subcategory": subcategory,
            "category_3_language": clean_text(item.get("language", "")),
            "category_4_source": clean_text(item.get("source", "")),
        },
    )


def download_mmar() -> None:
    import pandas as pd

    print(f"[{NAME}] downloading from {HF_REPO} …")
    meta = _fetch_meta()

    # Raw: store exactly as is (column order preserved from the source items).
    write_raw(NAME, pd.DataFrame(meta))
    normalize_mmar(pd.DataFrame(meta))


def normalize_mmar(df=None):
    """Normalize the local raw MMAR CSV without downloading it again."""
    rows = frame_records(df) if df is not None else read_raw_records(NAME)
    return write_normalized(NAME, [_normalize_row(row) for row in rows])


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

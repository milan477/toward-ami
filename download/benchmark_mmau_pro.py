"""Download + normalize MMAU-Pro (https://huggingface.co/datasets/gamma-lab-umd/MMAU-Pro).

MMAU-Pro ships as a single parquet (test.parquet, 5305 items) plus an audio
archive (data.zip). We only need the parquet; audio is referenced by audio_path.

Each parquet row has:
  id, audio_path (array of paths), question, answer, choices (array),
  length_type, perceptual_skills (array), reasoning_skills (array),
  category, transcription, task_classification, task_identifier, kwargs, sub-cat

Notable quirks
--------------
- choices is empty for 215 open-ended rows.
- answer is null for 87 instruction-following rows → answer ``[]``.
- audio_path is an array; 456 rows reference more than one clip.
- perceptual_skills / reasoning_skills are multi-valued arrays.

Normalization choices
---------------------
- url: the source audio-path array, retained as a JSON list.
- category hierarchy: ``category_1_category`` → ``category_2_subcategory``.
- parallel creator taxonomies retain their own descriptive category columns.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from download.common import (
    AUDIO_DIR,
    as_list,
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

NAME         = "mmau_pro"
HF_REPO      = "gamma-lab-umd/MMAU-Pro"
PARQUET_FILE = "test.parquet"
AUDIO_FILE   = "data.zip"


def _fetch_df():
    import pandas as pd

    from huggingface_hub import hf_hub_download

    path = hf_hub_download(HF_REPO, PARQUET_FILE, repo_type="dataset")
    return pd.read_parquet(path)


def _skill_items(value) -> list[str]:
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = json.loads(value)
            value = parsed
        except json.JSONDecodeError:
            pass
    return [clean_text(s) for s in as_list(value) if clean_text(s)]


def _combined_skills(row: dict) -> str:
    skills = []
    for col in ("perceptual_skills", "reasoning_skills"):
        for skill in _skill_items(row.get(col)):
            skill = clean_text(skill)
            if skill and skill not in skills:
                skills.append(skill)
    return json.dumps(skills, ensure_ascii=False)


def _normalize_row(row: dict) -> dict:
    choices = as_list(row.get("choices"))
    correct = resolve_correct_answer(row.get("answer"), choices)
    distractors = json.loads(to_distractors(choices, correct))
    source_category = clean_text(row.get("category", ""))
    source_subcategory = clean_text(row.get("sub-cat", ""))
    perceptual = _skill_items(row.get("perceptual_skills"))
    reasoning = _skill_items(row.get("reasoning_skills"))
    creator_categories = []
    if perceptual:
        creator_categories.append("perceptual")
    if reasoning:
        creator_categories.append("reasoning")
    task_classification = clean_text(row.get("task_classification", ""))
    focus = focus_values(source_category, source_subcategory)
    if not focus and source_category == "voice_chat":
        focus = ["speech"]
    elif not focus and source_category == "spatial_audio":
        focus = ["sound"]
    return normalized_record(
        bench=NAME,
        focus=focus,
        question=row.get("question", ""),
        answer=[correct] if correct else [],
        distractors=distractors,
        url=as_list(row.get("audio_path")),
        categories={
            "category_1_category": json.dumps(creator_categories, ensure_ascii=False),
            "category_2_skills": _combined_skills(row),
            "category_3_subcategory": source_subcategory,
            "category_4_task_classification": task_classification,
            "category_5_task_identifier": clean_text(row.get("task_identifier", "")),
            "category_6_length_type": clean_text(row.get("length_type", "")),
        },
    )


def download_mmau_pro() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    df = _fetch_df()

    # Raw: store exactly as is (arrays JSON-serialized by write_raw).
    write_raw(NAME, df)
    normalize_mmau_pro(df)


def normalize_mmau_pro(df=None):
    """Normalize the local raw MMAU-Pro CSV without downloading it again."""
    rows = frame_records(df) if df is not None else read_raw_records(NAME)
    return write_normalized(NAME, [_normalize_row(row) for row in rows])


def _hf_headers() -> dict:
    tok = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def download_mmau_pro_audio() -> Path:
    """Range-fetch referenced MMAU-Pro clips from the dataset zip."""
    from huggingface_hub import hf_hub_url
    from remotezip import RemoteZip

    out_dir = AUDIO_DIR / NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = referenced_audio_paths(NAME)
    missing = [p for p in wanted if not (out_dir / Path(p).name).exists()]
    print(f"[{NAME}] {len(wanted)} clips referenced, {len(missing)} to fetch")
    if not missing:
        print(f"  audio      → {out_dir}  (all present)")
        return out_dir

    url = hf_hub_url(HF_REPO, AUDIO_FILE, repo_type="dataset")
    fetched, not_found = 0, []
    with RemoteZip(url, headers=_hf_headers()) as z:
        names = set(z.namelist())
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


if __name__ == "__main__":
    from clean import clean_dataset

    download_mmau_pro()
    clean_dataset(NAME)
    download_mmau_pro_audio()

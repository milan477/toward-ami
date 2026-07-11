"""Download + normalize MMAU-Pro (https://huggingface.co/datasets/gamma-lab-umd/MMAU-Pro).

MMAU-Pro ships as a single parquet (test.parquet, 5305 items) plus an audio
archive (data.zip). We only need the parquet; audio is referenced by audio_path.

Each parquet row has:
  id, audio_path (array of paths), question, answer, choices (array),
  length_type, perceptual_skills (array), reasoning_skills (array),
  category, transcription, task_classification, task_identifier, kwargs, sub-cat

Notable quirks
--------------
- choices is empty for 215 open-ended rows  → question_type "oeq".
- answer is null for 87 instruction-following rows → correct_answer "".
- audio_path is an array; 456 rows reference more than one clip.
- perceptual_skills / reasoning_skills are multi-valued arrays.

Normalization choices
---------------------
- audio_url     : audio_path clips joined with "; ".
- category_1/2/3/4: category → sub-cat → (unused) → (unused).
- extra columns : perceptual_skills, reasoning_skills (JSON lists), length_type.
"""

import json
import os
from pathlib import Path

import pandas as pd

from common import (
    AUDIO_DIR,
    as_list,
    clean_text,
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


def _fetch_df() -> pd.DataFrame:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(HF_REPO, PARQUET_FILE, repo_type="dataset")
    return pd.read_parquet(path)


def _join_audio(audio_path) -> str:
    return "; ".join(clean_text(p) for p in as_list(audio_path) if clean_text(p))


def _skills(value) -> str:
    return json.dumps(_skill_items(value), ensure_ascii=False)


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
    return {
        "benchmark":         NAME,
        "question":          clean_text(row.get("question", "")),
        "question_type":     "mcq" if choices else "oeq",
        "correct_answer":    correct,
        "distractors":       to_distractors(choices, correct),
        "audio_url":         _join_audio(row.get("audio_path")),
        "category_1":        clean_text(row.get("category", "")),
        "category_2":        clean_text(row.get("sub-cat", "")),
        "category_3":        "",
        "category_4":        "",
        "skills":            _combined_skills(row),
        "perceptual_skills": _skills(row.get("perceptual_skills")),
        "reasoning_skills":  _skills(row.get("reasoning_skills")),
        "length_type":       clean_text(row.get("length_type", "")),
    }


def download_mmau_pro() -> None:
    print(f"[{NAME}] downloading from {HF_REPO} …")
    df = _fetch_df()

    # Raw: store exactly as is (arrays JSON-serialized by write_raw).
    write_raw(NAME, df)

    # Normalized: canonical schema + MMAU-Pro extras.
    write_normalized(NAME, [_normalize_row(r) for r in df.to_dict("records")])


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

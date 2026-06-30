"""Data access for the normalized benchmark CSVs (replaces the old YAML catalog).

All analysis now reads from data/normalized/<name>.csv (produced by download/):

  load_items(name=None)   question-level dicts (all benchmarks, or one)
  load_all()              benchmark-level summaries derived from the CSVs
  load_by_name(name)      a single benchmark summary

The curated YAML catalog was removed. Fields that were hand-entered there and
cannot be derived from the questions (``year``, ``sota_score``, citation counts)
are no longer available; load_all() reports them as None.
"""

import json
from pathlib import Path

import pandas as pd

NORM_DIR = Path(__file__).parent.parent / "data" / "normalized"


def available_benchmarks() -> list[str]:
    """Names of every normalized benchmark CSV (filename stem)."""
    return sorted(p.stem for p in NORM_DIR.glob("*.csv"))


def _parse_distractors(raw) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return [str(x) for x in val] if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _row_to_item(row: dict) -> dict:
    """Convert a normalized CSV row to the item dict the analysis code expects."""
    qtype   = row.get("question_type", "")
    correct = row.get("correct_answer", "")
    choices = ([correct] + _parse_distractors(row.get("distractors", ""))
               if qtype == "mcq" else [])
    return {
        "benchmark":        row.get("benchmark", ""),
        "question":         row.get("question", ""),
        "question_type":    qtype,
        "correct_answer":   correct,
        "answer":           correct,  # alias for legacy consumers
        "choices":          choices,
        "audio_url":        row.get("audio_url", ""),
        "category":         row.get("category_1", ""),
        "sub_category":     row.get("category_2", ""),
        "sub_sub_category": row.get("category_3", ""),
        "category_1":       row.get("category_1", ""),
        "category_2":       row.get("category_2", ""),
        "category_3":       row.get("category_3", ""),
    }


def load_items(name: str | None = None) -> list[dict]:
    """Question-level items for one benchmark, or all benchmarks if name is None."""
    names = [name.lower()] if name else available_benchmarks()
    items: list[dict] = []
    for n in names:
        path = NORM_DIR / f"{n}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        items.extend(_row_to_item(r) for r in df.to_dict("records"))
    return items


def _summarize(name: str) -> dict:
    """Benchmark-level summary derived from the normalized questions."""
    items   = load_items(name)
    skills  = sorted({it["category_1"] for it in items if it["category_1"]})
    has_mcq = any(it["question_type"] == "mcq" for it in items)
    has_oeq = any(it["question_type"] == "oeq" for it in items)
    question_format = (["MCQ"] if has_mcq else []) + (["open-ended"] if has_oeq else [])
    return {
        "name":            name,
        "primary_skill":   skills,
        "question_format": question_format,
        "coverage":        {"n_items": len(items)},
        "year":            None,        # not derivable; curated catalog removed
        "sota_score":      None,        # not derivable; curated catalog removed
    }


def load_all() -> list[dict]:
    entries = [_summarize(n) for n in available_benchmarks()]
    for e in entries:
        print(f"Loaded {e['name']} with {e['coverage']['n_items']} items")
    return entries


def load_by_name(name: str) -> dict:
    for entry in load_all():
        if entry["name"].lower() == name.lower():
            return entry
    raise KeyError(f"No benchmark named {name!r}")

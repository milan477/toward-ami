"""Shared helpers for dataset download + normalization.

Every dataset gets a specialized download function (see e.g.
download/benchmark_mmar.py) that produces two CSVs under data/benchmarks/<name>/:

  <name>_raw.csv          The source dataset, stored exactly as is.
                          List/dict cells are JSON-serialized so the CSV
                          round-trips, but no rows/columns are dropped.
  <name>_normalized.csv   The canonical schema below, shared across all
                          datasets so downstream analysis is uniform.

Normalized schema
-----------------
qid             str        stable question id: <benchmark>_q_<n> (1-based)
benchmark       str        benchmark name
question        str        question text
question_type   str        "mcq" (has choices) or "oeq" (open-ended)
correct_answer  str        correct answer as plain text
distractors     JSON list  wrong options, e.g. ["A","B","C"]; [] for OEQ
audio_url       str        path/URL identifying the audio clip
category_1      str        top-level category label
category_2      str        second-level category label ("" if n/a)
category_3      str        third-level category label ("" if n/a)
category_4      str        fourth-level category label ("" if n/a)

Datasets may add extra columns after category_4 if they carry labels that do
not fit the hierarchy; keep the columns above in this order and append.
"""

import json
import ast
from pathlib import Path

import numpy as np
import pandas as pd

ROOT      = Path(__file__).parent.parent
BENCH_DIR = ROOT / "data" / "benchmarks"
AUDIO_DIR = ROOT / "data" / "audio"


def bench_dir(name: str) -> Path:
    """Return (and create) data/benchmarks/<name>/, the home of all stages."""
    d = BENCH_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def bench_path(name: str, stage: str) -> Path:
    """Path to a benchmark stage CSV.

    Stages: raw, normalized, selected, annotated. ``selected`` is the music
    subset of normalized; ``annotated`` is selected plus analysis labels."""
    if stage == "selected":
        return BENCH_DIR / name / f"{name}_normalized_selected.csv"
    if stage == "annotated":
        return BENCH_DIR / name / f"{name}_normalized_selected_annotated.csv"
    if stage not in {"raw", "normalized"}:
        raise ValueError(f"Unknown benchmark stage {stage!r}. Use raw, normalized, selected, or annotated.")
    return BENCH_DIR / name / f"{name}_{stage}.csv"


def referenced_audio_paths(name: str, stage: str = "selected") -> list[str]:
    """Return unique audio_url paths from a benchmark stage, preserving order.

    ``audio_url`` may contain one clip, several clips joined with ``; ``, or
    legacy Python-list reprs. Leading ``./`` is removed so archive member names
    and on-disk filenames compare consistently.
    """
    df = pd.read_csv(bench_path(name, stage))
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

    seen, out = set(), []
    for p in paths:
        p = p.lstrip("./")
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out

NORMALIZED_COLUMNS = [
    "qid", "benchmark", "question", "question_type", "correct_answer",
    "distractors", "audio_url",
    "category_1", "category_2", "category_3", "category_4",
]


def make_qid(name: str, n: int) -> str:
    """Return a stable question id: ``<benchmark>_q_<n>`` (1-based)."""
    return f"{name}_q_{n}"


def clean_text(value) -> str:
    """Collapse all internal whitespace (incl. newlines) to single spaces."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def as_list(value) -> list:
    """Coerce a value to a list, handling None, lists, and numpy arrays.

    Numpy arrays can't be truth-tested with ``or``, so callers use this instead.
    """
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def to_distractors(choices, correct_answer) -> str:
    """JSON list of cleaned wrong options (correct answer removed), no newlines.

    Returns e.g. '["distractor 1","distractor 2"]'. Empty list for OEQ.
    """
    correct = clean_text(correct_answer)
    wrongs  = [clean_text(c) for c in as_list(choices)]
    wrongs  = [w for w in wrongs if w and w != correct]
    return json.dumps(wrongs, ensure_ascii=False)


def resolve_correct_answer(answer, choices) -> str:
    """Return the correct answer as plain text.

    The answer may be the option text itself, a letter (A/B/C/...), or a
    zero-based integer index into ``choices``. An exact text match always wins,
    so a literal answer like "3" (when "3" is one of the options) is never
    mistaken for an index. Letter/index resolution is only a fallback for when
    the answer is not itself one of the options. Falls back to the raw answer.
    """
    ans     = clean_text(answer)
    options = [clean_text(c) for c in as_list(choices)]
    if not options:
        return ans

    # 1. exact text match (case-insensitive) — takes precedence over any index
    for opt in options:
        if opt.lower() == ans.lower():
            return opt

    # 2. letter index: A / B / C / ...
    if len(ans) == 1 and ans.upper().isalpha():
        idx = ord(ans.upper()) - ord("A")
        if 0 <= idx < len(options):
            return options[idx]

    # 3. zero-based integer index (only when the answer matched no option text)
    try:
        idx = int(ans)
        if 0 <= idx < len(options):
            return options[idx]
    except ValueError:
        pass

    return ans


def _serialize_cell(value):
    """Prepare a cell for the raw CSV so every record stays on one line.

    List/dict cells are JSON-serialized (embedded newlines become escaped \\n);
    string cells have whitespace (incl. newlines) collapsed to single spaces.
    """
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, list):
        return json.dumps([_serialize_cell(v) for v in value], ensure_ascii=False)
    if isinstance(value, (list, dict)):
        return json.dumps({k: _serialize_cell(v) for k, v in value.items()}, ensure_ascii=False)
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def write_raw(name: str, df: pd.DataFrame) -> Path:
    """Write the source dataset to data/benchmarks/<name>/<name>_raw.csv."""
    bench_dir(name)
    out = df.map(_serialize_cell)
    path = bench_path(name, "raw")
    out.to_csv(path, index=False)
    print(f"  raw        → {path}  ({len(out)} rows × {len(out.columns)} cols)")
    return path


def write_normalized(name: str, rows: list[dict]) -> Path:
    """Write canonical rows to data/benchmarks/<name>/<name>_normalized.csv.

    Assigns a stable ``qid`` (``<name>_q_<n>``, 1-based) to every row.
    Columns in NORMALIZED_COLUMNS come first (in order); any extra keys present
    in the rows are appended after, sorted.
    """
    bench_dir(name)
    assigned = []
    for i, row in enumerate(rows, start=1):
        rec = dict(row)
        rec["qid"] = make_qid(name, i)
        if not rec.get("benchmark"):
            rec["benchmark"] = name
        assigned.append(rec)
    extra = sorted({k for r in assigned for k in r} - set(NORMALIZED_COLUMNS))
    columns = NORMALIZED_COLUMNS + extra
    df = pd.DataFrame(assigned, columns=columns)
    path = bench_path(name, "normalized")
    df.to_csv(path, index=False)
    print(f"  normalized → {path}  ({len(df)} rows)")
    return path

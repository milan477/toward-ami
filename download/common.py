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
qid              str        stable question id: <bench>_q_<n> (1-based)
bench            str        benchmark name
focus            JSON list  audio domains copied/inferred from source metadata
question         str        question text
answer           JSON list  accepted source answers
distractors      JSON list  wrong source options
url              JSON list  paths/URLs identifying the input audio
input_modality   JSON list  input modalities, normally ["audio", "text"]
output_modality  str        output modality, normally "text"

Creator taxonomies follow the explicit pattern ``category_<level>_<name>``.
For example, MMAU-Pro uses ``category_1_category`` and
``category_2_subcategory``. Normalization is deterministic and source-faithful;
standardized content/skill, PIEC, and question-nature labels belong only in the
enhanced stage.
"""

import json
import ast
import csv
import re
from pathlib import Path

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

    Stages: raw, normalized, selected, enhanced, annotated. ``selected`` is the
    music subset of normalized; ``enhanced`` adds LLM-derived dimensions to
    that selected subset.
    ``annotated`` remains available for legacy result files.
    """
    if stage == "selected":
        return BENCH_DIR / name / f"{name}_normalized_selected.csv"
    if stage == "enhanced":
        return BENCH_DIR / name / f"{name}_normalized_selected_enhanced.csv"
    if stage == "annotated":
        return BENCH_DIR / name / f"{name}_normalized_selected_annotated.csv"
    if stage not in {"raw", "normalized"}:
        raise ValueError(
            f"Unknown benchmark stage {stage!r}. Use raw, normalized, selected, "
            "enhanced, or annotated."
        )
    return BENCH_DIR / name / f"{name}_{stage}.csv"


def referenced_audio_paths(name: str, stage: str = "selected") -> list[str]:
    """Return unique ``url`` paths from a benchmark stage, preserving order.

    ``url`` is a JSON list. Legacy scalar and ``; ``-joined values are accepted
    so old generated files remain readable during migration.
    """
    with bench_path(name, stage).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    paths: list[str] = []
    column = "url" if rows and "url" in rows[0] else "audio_url"
    for row in rows:
        url = row.get(column, "")
        if isinstance(url, str) and url.strip().startswith("["):
            try:
                values = json.loads(url)
            except json.JSONDecodeError:
                values = None
            if isinstance(values, list):
                paths.extend(str(value) for value in values if str(value).strip())
                continue
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
    "qid", "bench", "focus", "question", "answer", "distractors", "url",
    "input_modality", "output_modality",
]

FOCUS_VALUES = ("music", "speech", "sound")
CATEGORY_COLUMN_RE = re.compile(r"^category_([1-9][0-9]*)_([a-z0-9]+(?:_[a-z0-9]+)*)$")


def json_list(values) -> str:
    """Return a stable JSON list of non-empty, deduplicated strings."""
    if values is None:
        values = []
    if isinstance(values, str):
        text = values.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                values = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                values = [values]
        else:
            values = [values]
    elif hasattr(values, "tolist"):
        values = values.tolist()
    elif not isinstance(values, (list, tuple, set)):
        values = [values]

    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = clean_text(value)
        if not item or item.lower() == "nan":
            continue
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return json.dumps(out, ensure_ascii=False)


def list_values(value) -> list[str]:
    """Read a normalized JSON-list cell, accepting a legacy scalar."""
    if hasattr(value, "tolist"):
        values = value.tolist()
    elif isinstance(value, (list, tuple)):
        values = value
    elif value is None:
        values = []
    else:
        text = str(value).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = [text] if text else []
        values = parsed if isinstance(parsed, list) else [parsed]
    return [clean_text(item) for item in values if clean_text(item)]


def first_value(value, default: str = "") -> str:
    """Return the first value in a normalized JSON-list cell."""
    values = list_values(value)
    return values[0] if values else default


def focus_values(*labels) -> list[str]:
    """Extract the canonical music/speech/sound domains from source labels."""
    text = " ".join(clean_text(label).lower() for label in labels if label is not None)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [focus for focus in FOCUS_VALUES if re.search(rf"\b{focus}\b", text)]


def _source_value(value):
    """Serialize a creator-category cell safely for normalized CSV output."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        return json.dumps([_source_value(item) for item in value], ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(
            {str(key): _source_value(item) for key, item in value.items()},
            ensure_ascii=False,
        )
    return clean_text(value) if isinstance(value, str) else value


def normalized_record(
    *,
    bench: str,
    focus,
    question,
    answer,
    distractors=(),
    url=(),
    input_modality=("audio", "text"),
    output_modality="text",
    categories: dict[str, object] | None = None,
) -> dict:
    """Build one source-extractable normalized record.

    List-valued cells are serialized as JSON because CSV has no native list
    type. ``categories`` must use self-describing hierarchical column names.
    """
    category_values = categories or {}
    invalid = [key for key in category_values if not CATEGORY_COLUMN_RE.fullmatch(key)]
    if invalid:
        raise ValueError(
            "Invalid creator category column(s): " + ", ".join(sorted(invalid))
        )
    return {
        "bench": clean_text(bench),
        "focus": json_list(focus),
        "question": clean_text(question),
        "answer": json_list(answer),
        "distractors": json_list(distractors),
        "url": json_list(url),
        "input_modality": json_list(input_modality),
        "output_modality": clean_text(output_modality),
        **{key: _source_value(value) for key, value in category_values.items()},
    }


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
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str) and value.strip().startswith("["):
        text = value.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                parsed = None
        if isinstance(parsed, (list, tuple)):
            return list(parsed)
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
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list):
        return json.dumps([_serialize_cell(v) for v in value], ensure_ascii=False)
    if isinstance(value, (list, dict)):
        return json.dumps({k: _serialize_cell(v) for k, v in value.items()}, ensure_ascii=False)
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def write_raw(name: str, df) -> Path:
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
        if not rec.get("bench"):
            rec["bench"] = name
        assigned.append(rec)
    extra = sorted({k for r in assigned for k in r} - set(NORMALIZED_COLUMNS))
    invalid = [key for key in extra if not CATEGORY_COLUMN_RE.fullmatch(key)]
    if invalid:
        raise ValueError(
            "Normalized rows may only add creator taxonomy columns named "
            "category_<level>_<name>; found: " + ", ".join(invalid)
        )
    extra.sort(key=lambda key: (int(CATEGORY_COLUMN_RE.fullmatch(key).group(1)), key))
    columns = NORMALIZED_COLUMNS + extra
    path = bench_path(name, "normalized")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(assigned)
    print(f"  normalized → {path}  ({len(assigned)} rows)")
    return path


def read_raw_records(name: str) -> list[dict]:
    """Read a local raw CSV without importing the download-time dataframe stack."""
    with bench_path(name, "raw").open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def frame_records(frame) -> list[dict]:
    """Convert an optional dataframe/list input supplied by a downloader to records."""
    if isinstance(frame, list):
        return [dict(row) for row in frame]
    return frame.to_dict("records")

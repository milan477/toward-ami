"""Build the static GitHub Pages site for the music-understanding explorer.

Reads the normalized benchmark questions, available MCQ + PIAC-judged OEQ
results, and the live prompt sources, then emits a self-contained site under
``docs/``:

    docs/index.html  docs/styles.css  docs/app.js   (static, hand-written)
    docs/data/*.json                                (generated here)
    docs/audio/<dataset>/...                        (optional local audio, gitignored)

Audio is normally served from an external static host by setting
``AMI_AUDIO_BASE_URL`` before building the site JSON. The hosted layout mirrors
the normalized ``audio_url`` metadata for each benchmark, so the website can
play all available benchmark clips without committing or locally keeping the
multi-gigabyte audio corpus. Local ``docs/audio``/``data/audio`` files are only
fallbacks for development and duration recomputation.

    python renderers/site/build_site.py --list
    AMI_AUDIO_BASE_URL=https://huggingface.co/datasets/milan477/toward-ami/resolve/main python renderers/site/build_site.py --target questions --no-audio
    python renderers/site/build_site.py --target questions --no-audio
    python renderers/site/build_site.py --target benchmarks

The model catalog is read from the newest
``data/models/overviews/model_overview_<date>.csv`` (source of truth) and written
out as ``docs/data/models.json``. Benchmarks likewise come from the newest
``data/benchmarks/overviews/benchmark_overview_<date>.csv`` → ``docs/data/benchmarks.json``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
DATA_DIR = DOCS / "data"
QUESTION_DATA_DIR = DATA_DIR / "questions"
AUDIO_OUT = DOCS / "audio"
BENCHMARK_DATA = ROOT / "data" / "benchmarks"
AUDIO_SRC = ROOT / "data" / "audio" / "mmar"
PAPER_PDF = ROOT / "paper" / "paper.pdf"
REPO_URL = "https://github.com/milan477/toward-ami"
HOSTED_AUDIO_BASE_URL = os.environ.get("AMI_AUDIO_BASE_URL", "").rstrip("/")
# Benchmarks present in the catalog whose source metadata has been imported but
# whose clips have not yet been added to the hosted/local audio collection.
METADATA_ONLY_AUDIO_DATASETS = {"aha"}
DATA_TARGETS = (
    "meta",
    "news",
    "models",
    "benchmarks",
    "evaluation",
    "overview",
    "literature-results",
    "prompts",
    "questions",
    "paper",
    "audio",
)

# Latest news / takeaways shown on the home page — newest first. Edit freely.
NEWS = [
    {
        "date": "2026-07-02",
        "title": "Multiple choice hides what models can't do",
        "text": "On the MMAR music set, both Audio Flamingo Next and Gemini 3 Flash "
                "score far higher on multiple-choice questions than on the identical "
                "questions asked open-ended. The gap is the point: picking a letter is "
                "not the same as knowing the answer.",
    },
    {
        "date": "2026-07-02",
        "title": "PIAC: grade a claim by how its truth is established",
        "text": "We separate every musical question into perceptual, inferential, "
                "experiential, or contextual — by the nature of its ground truth — and let "
                "the judge apply a different standard to each. Affective questions admit "
                "many correct answers; perceptual ones admit one.",
    },
    {
        "date": "2026-07-01",
        "title": "Nine benchmarks characterized",
        "text": "We catalogued the current landscape of music-understanding benchmarks — "
                "what each measures, in what format, and which models report on it — to "
                "make the coverage gaps legible.",
    },
]

MODEL_META = ("developer", "year", "paper_title", "paper_url")

# Catalogs are authored in dated overview CSVs under data/*/overviews/. The newest
# dated file is read at build time to populate docs/data/*.json.
MODEL_OVERVIEWS = ROOT / "data" / "models" / "overviews"
BENCH_OVERVIEWS = ROOT / "data" / "benchmarks" / "overviews"


def latest_model_overview() -> Path | None:
    if not MODEL_OVERVIEWS.exists():
        return None
    files = sorted(MODEL_OVERVIEWS.glob("model_overview_*.csv"))
    return files[-1] if files else None


def load_models() -> list[dict]:
    """Read the newest model_overview_*.csv into model dicts (source of truth)."""
    path = latest_model_overview()
    if not path:
        raise FileNotFoundError(
            "no model_overview_*.csv in data/models/overviews/")
    models: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mid = (r.get("ID") or "").strip()
            if not mid:
                continue
            m = {
                "id": mid,
                "label": (r.get("Label") or "").strip(),
                "developer": (r.get("Developer") or "").strip(),
                "year": (r.get("Year") or "").strip(),
                "paper_title": (r.get("Paper title") or "").strip(),
                "paper_url": (r.get("Paper link") or "").strip(),
            }
            mcq = (r.get("MCQ CSV") or "").strip()
            if mcq:
                m["mcq_csv"] = mcq
                m["oeq_answers"] = (r.get("OEQ answers") or "").strip()
                m["oeq_judged"] = (r.get("OEQ judged") or "").strip()
            models.append(m)
    return models

PIAC_ORDER = ["perceptual", "inferential", "experiential", "contextual"]


def _read_jsonl(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["qid"]] = rec
    return out


def _read_csv(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8") as f:
        return {r["qid"]: r for r in csv.DictReader(f)}


def _parse_distractors(raw: str) -> list[str]:
    try:
        val = json.loads(raw) if raw else []
        return [str(x) for x in val] if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_listish(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text or _is_empty_list_marker(text):
        return []
    decoder = json.JSONDecoder()
    out: list[str] = []
    pos = 0
    decoded_json = False
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        try:
            val, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        decoded_json = True
        if isinstance(val, list):
            out.extend(str(x).strip() for x in val if str(x).strip() and not _is_empty_list_marker(str(x)))
        elif str(val).strip() and not _is_empty_list_marker(str(val)):
            out.append(str(val).strip())
        pos = end
    if decoded_json:
        return _dedupe(out)
    try:
        val = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return _dedupe([part.strip() for part in re.split(r"[,;]", text) if part.strip()])
    if isinstance(val, list):
        return _dedupe([str(x).strip() for x in val if str(x).strip() and not _is_empty_list_marker(str(x))])
    return [str(val)] if str(val).strip() and not _is_empty_list_marker(str(val)) else []


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _question_file_key(value: str) -> str:
    return _compact_key(value) or "benchmark"


def _display_name_map(benchmarks: list[dict]) -> dict[str, str]:
    names = {_compact_key(b["name"]): b["name"] for b in benchmarks}
    return {
        "mmar": "MMAR",
        "mmau": names.get("mmau", "MMAU"),
        "mmau_pro": names.get("mmaupro", "MMAU-Pro"),
        "muchomusic": names.get("muchomusic", "MuChoMusic"),
        "hummusqa": names.get("hummusqa", "HumMusQA"),
        "pitchbench": names.get("pitchbench", "PitchBench"),
        **names,
    }


def _stage_path(dataset_dir: Path) -> Path | None:
    name = dataset_dir.name
    fallback = None
    for suffix in (
        "normalized_selected_enhanced",
        "normalized_selected_annotated",
        "normalized_selected",
        "ready",
        "normalized",
    ):
        path = dataset_dir / f"{name}_{suffix}.csv"
        if path.exists():
            fallback = fallback or path
            try:
                with path.open(encoding="utf-8") as handle:
                    if next(csv.DictReader(handle), None) is not None:
                        return path
            except OSError:
                continue
    return fallback


def _benchmark_stage_paths() -> list[Path]:
    if not BENCHMARK_DATA.exists():
        return []
    paths = []
    for d in sorted(BENCHMARK_DATA.iterdir()):
        if not d.is_dir() or d.name == "overviews":
            continue
        path = _stage_path(d)
        if path:
            paths.append(path)
    return paths


def benchmark_question_counts(benchmarks: list[dict]) -> dict[str, int]:
    display_names = _display_name_map(benchmarks)
    counts: dict[str, int] = {}
    for path in _benchmark_stage_paths():
        dataset = path.parent.name
        benchmark = display_names.get(dataset, display_names.get(_compact_key(dataset), dataset))
        try:
            with path.open(encoding="utf-8") as f:
                n = sum(1 for _ in csv.DictReader(f))
        except OSError:
            continue
        counts[benchmark] = counts.get(benchmark, 0) + n
    return counts


def _audio_sources(audio_url: str) -> list[str]:
    return _parse_listish(audio_url)


def _audio_stems(audio_url: str) -> list[str]:
    stems = []
    for source in _audio_sources(audio_url):
        if ":" in source and "/" not in source:
            _, _, source = source.partition(":")
        stem = Path(source).name.rsplit(".", 1)[0]
        if stem:
            stems.append(stem)
    return stems


def _audio_stem(audio_url: str) -> str:
    stems = _audio_stems(audio_url)
    return stems[0] if stems else ""


def _skills_text(row: dict) -> str:
    action_content = row.get("action_content", "")
    if action_content:
        try:
            pairs = json.loads(action_content)
        except (json.JSONDecodeError, TypeError):
            pairs = []
        return ", ".join(
            f"{pair[0]}: {pair[1]}"
            for pair in pairs
            if isinstance(pair, list) and len(pair) == 2
        )
    if row.get("content") or row.get("skill"):
        content = ", ".join(_parse_listish(row.get("content", "")))
        operations = ", ".join(_parse_listish(row.get("skill", "")))
        return "; ".join(
            part for part in (
                f"content: {content}" if content else "",
                f"operations: {operations}" if operations else "",
            ) if part
        )
    if row.get("skills"):
        vals = _parse_listish(row["skills"])
        if not vals and _has_empty_list_marker(row["skills"]):
            return "none specified"
        return ", ".join(vals) if vals else row["skills"]
    vals = []
    for col in ("music_knowledge", "music_reasoning", "perceptual_skills", "reasoning_skills"):
        vals.extend(_parse_listish(row.get(col, "")))
    seen = []
    for val in vals:
        if val not in seen:
            seen.append(val)
    return ", ".join(seen)


def _is_empty_list_marker(raw: str) -> bool:
    return str(raw or "").strip().replace(" ", "") in {"[]", "[][]"}


def _has_empty_list_marker(raw: str) -> bool:
    return "[]" in str(raw or "").replace(" ", "")


def _category_cell_values(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        return _parse_listish(text)
    return [text]


def _category_values_for_row(dataset: str, row: dict) -> dict[str, list[str]]:
    category_columns = sorted(
        (key for key in row if re.fullmatch(r"category_[1-9][0-9]*_.+", key)),
        key=lambda key: (int(key.split("_", 2)[1]), key),
    )
    try:
        pairs = json.loads(
            row.get("action_content", "") or "[]"
        )
    except (json.JSONDecodeError, TypeError):
        pairs = []
    categories = {
        "focus": _parse_listish(row.get("focus", "")),
        "input_modality": _parse_listish(row.get("input_modality", "")),
        "output_modality": _parse_listish(row.get("output_modality", "")),
        **{
            key: _dedupe(_category_cell_values(row.get(key, "")))
            for key in category_columns
        },
        "action": _dedupe([pair[0] for pair in pairs if isinstance(pair, list) and len(pair) == 2]),
        "content": _dedupe([pair[1] for pair in pairs if isinstance(pair, list) and len(pair) == 2]),
    }
    return {key: values for key, values in categories.items() if values}


def _site_category_values(dataset: str, row: dict) -> dict[str, list[str]]:
    categories = _category_values_for_row(dataset, row)
    for key, values in list(categories.items()):
        categories[key] = [
            "none specified" if _is_empty_list_marker(value) else value
            for value in values
        ]
    if dataset == "mmau_pro" and _has_empty_list_marker(row.get("skills", "")) and not categories.get("action"):
        categories["action"] = ["none specified"]
    return categories


def _row_piac(row: dict) -> str:
    val = (row.get("piec") or row.get("category") or "").strip().lower()
    return val if val in PIAC_ORDER else ""


def _question_id(dataset: str, row: dict, idx: int) -> str:
    if row.get("qid"):
        return row["qid"]
    stem = _audio_stem(row.get("url", row.get("audio_url", "")))
    return stem or f"{dataset}:{idx + 1}"


def _existing_question_cache() -> dict[tuple[str, str], dict]:
    """Read generated question metadata so rebuilds without local audio keep stats."""
    cache: dict[tuple[str, str], dict] = {}
    paths = sorted(QUESTION_DATA_DIR.glob("*.json"))
    if not paths and (DATA_DIR / "questions.json").exists():
        paths = [DATA_DIR / "questions.json"]
    for path in paths:
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in rows:
            qid = str(row.get("qid") or "")
            benchmark = str(row.get("benchmark") or "")
            if qid and benchmark:
                cache[(benchmark, qid)] = row
                cache[("", qid)] = row
    return cache


def load_questions(benchmarks: list[dict], models: dict[str, dict]) -> tuple[list[dict], set[tuple[str, str]], dict[str, str], list[str]]:
    display_names = _display_name_map(benchmarks)
    questions: list[dict] = []
    stems: set[tuple[str, str]] = set()
    q_piac: dict[str, str] = {}
    eval_qids: list[str] = []
    audio_indexes: dict[str, dict] = {}
    question_cache = _existing_question_cache()

    def audio_durations(dataset: str, audio_url: str) -> list[float]:
        from src.analysis.statistics import (
            _audio_duration,
            _audio_names,
            _build_audio_index,
        )

        if dataset not in audio_indexes:
            audio_indexes[dataset] = _build_audio_index(dataset)
        index = audio_indexes[dataset]
        durations = []
        for audio_name in _audio_names(audio_url):
            path = index.get(audio_name) or index.get(Path(audio_name).stem)
            if not path:
                continue
            duration = _audio_duration(path)
            if duration is not None:
                durations.append(round(duration, 3))
        return durations

    for path in _benchmark_stage_paths():
        dataset = path.parent.name
        benchmark = display_names.get(dataset, display_names.get(_compact_key(dataset), dataset))
        with path.open(encoding="utf-8") as f:
            for idx, r in enumerate(csv.DictReader(f)):
                qid = _question_id(dataset, r, idx)
                source_urls = r.get("url", r.get("audio_url", ""))
                audio_stems = _audio_stems(source_urls)
                stem = audio_stems[0] if audio_stems else ""
                piac = _row_piac(r)
                stems.update((dataset, audio_stem) for audio_stem in audio_stems)
                if piac:
                    q_piac[qid] = piac
                cached = question_cache.get((benchmark, qid)) or question_cache.get(("", qid))
                if HOSTED_AUDIO_BASE_URL:
                    durations = (cached or {}).get("audio_duration_seconds") or []
                else:
                    durations = audio_durations(dataset, source_urls)
                    if not durations and cached:
                        durations = cached.get("audio_duration_seconds") or []
                rec = {
                    "qid": qid,
                    "benchmark": benchmark,
                    "audio_dataset": dataset,
                    "question": r.get("question", ""),
                    "question_type": r.get("question_nature", ""),
                    "piac": piac,
                    "skills": _skills_text(r),
                    "answer_format": r.get("answer_format", ""),
                    "correct_answer": ", ".join(_parse_distractors(r.get("answer", ""))),
                    "distractors": _parse_distractors(r.get("distractors", "")),
                    "audio_source": source_urls,
                    "audio_stem": stem,
                    "audio_stems": audio_stems,
                    "audio_duration_seconds": durations,
                    "categories": _site_category_values(dataset, r),
                    "_cached_audio_known": cached is not None and "audio" in cached,
                    "_cached_audio": cached.get("audio") if cached else None,
                }
                has_result = False
                for mid, data in models.items():
                    if qid in data["mcq"] or qid in data["ans"] or qid in data["jud"]:
                        meta = _result_metadata(data, qid)
                        if not rec["piac"]:
                            rec["piac"] = _row_piac(meta)
                            piac = rec["piac"]
                        if not rec["skills"] and meta.get("skills"):
                            rec["skills"] = meta["skills"]
                        if not rec["answer_format"] and meta.get("answer_format"):
                            rec["answer_format"] = meta["answer_format"]
                        rec[mid] = model_cell(data, qid)
                        has_result = True
                if has_result:
                    if piac:
                        q_piac[qid] = piac
                    eval_qids.append(qid)
                questions.append(rec)

    return questions, stems, q_piac, eval_qids


def load_model(m: dict) -> dict | None:
    paths = [ROOT / m[k] for k in ("mcq_csv", "oeq_answers", "oeq_judged") if m.get(k)]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"  results: skipping {m['id']} (missing {missing[0].relative_to(ROOT)})")
        return None
    return {
        "mcq": _read_csv(ROOT / m["mcq_csv"]),
        "ans": _read_jsonl(ROOT / m["oeq_answers"]),
        "jud": _read_jsonl(ROOT / m["oeq_judged"]),
    }


def model_cell(data: dict, qid: str) -> dict:
    mcq = data["mcq"].get(qid, {})
    ans = data["ans"].get(qid, {})
    jud = data["jud"].get(qid, {})
    return {
        "mcq_pred": (mcq.get("pred_answer") or "").strip(),
        "mcq_correct": str(mcq.get("correct")).strip().lower() == "true",
        "oeq_response": (ans.get("response") or "").strip(),
        "oeq_score": jud.get("score_norm"),
        "verdict": jud.get("verdict"),
        "confidence": jud.get("confidence"),
        "rationale": (jud.get("rationale") or "").strip(),
    }


def _result_metadata(data: dict, qid: str) -> dict:
    for section in ("ans", "jud", "mcq"):
        row = data.get(section, {}).get(qid)
        if row:
            return row
    return {}


def overview_for(data: dict, qids: list[str], q_piac: dict[str, str]) -> dict:
    def agg(rows):
        n = len(rows)
        if not n:
            return None
        mcq = sum(1 for r in rows if r["mcq_correct"]) / n
        oeq_mean = sum((r["oeq_score"] or 0) for r in rows) / n
        oeq_acc = sum(1 for r in rows if (r["oeq_score"] or 0) >= 0.5) / n
        return {"n": n, "mcq_acc": mcq, "oeq_mean": oeq_mean,
                "oeq_acc": oeq_acc}

    cells = {qid: model_cell(data, qid) for qid in qids}
    overall = agg(list(cells.values()))
    by_piac = {}
    for cat in PIAC_ORDER:
        rows = [cells[q] for q in qids if q_piac.get(q) == cat]
        if rows:
            by_piac[cat] = agg(rows)
    overall["by_piac"] = by_piac
    return overall


def build_prompts() -> list[dict]:
    """Pull the live prompt text from the pipeline modules so the tab stays true."""
    from src.evaluation.prompts import PIEC_JUDGE_PROMPT, build_mcq, build_oeq
    from src.experiments.variants import LETTER_AUDIO, OEQ_AUDIO
    from src.analysis.prompts import build_enhancement_prompt

    mcq = build_mcq(
        "What instrument plays the main melody?", "Violin",
        ["Piano", "Flute", "Trumpet"], "demo-qid", instruction=LETTER_AUDIO,
    )
    oeq_unguided_ex = build_oeq(
        "What does the music feel like?", "Melancholic", instruction=OEQ_AUDIO,
    )["prompt"]
    oeq_guided_ex = build_oeq(
        "What instrument plays the main melody?", "Violin",
        instruction=OEQ_AUDIO,
        answer_format="a single instrument name", example="Cello")["prompt"]

    mcq_options = "\n".join(
        f"{ltr}. {opt}" for ltr, opt in zip("ABCDEFGH", mcq["options"]))
    mcq_example = (
        f"Question: What instrument plays the main melody?\n\n{mcq_options}"
    )

    return [
        {
            "name": "MCQ prompt",
            "purpose": "The original multiple-choice form. Options are shuffled "
                       "deterministically per question and the model returns only a "
                       "letter; graded automatically against the correct option. This "
                       "is the 'apparent' score.",
            "variants": [
                {
                    "label": "Instruction",
                    "text": LETTER_AUDIO,
                    "example": mcq_example,
                },
            ],
        },
        {
            "name": "OEQ prompt",
            "purpose": "The same question with the options stripped away. The model "
                       "must produce the answer unaided. Graded by the PIAC judge "
                       "below; this is the 'actual' score. A per-question answer-format "
                       "hint steers only the form of the answer, never its content.",
            "variants": [
                {
                    "label": "Unguided",
                    "text": OEQ_AUDIO,
                    "example": oeq_unguided_ex,
                },
                {
                    "label": "Format-guided",
                    "text": OEQ_AUDIO,
                    "example": oeq_guided_ex,
                },
            ],
        },
        {
            "name": "PIEC judge prompt",
            "purpose": "A category-aware LLM-as-judge (local Qwen3) that grades each "
                       "open-ended answer as 0 or 1 with low/mid/high confidence. The "
                       "grading rubric injected into {rubric} depends on the question's "
                       "PIAC category.",
            "text": PIEC_JUDGE_PROMPT,
        },
        {
            "name": "Annotation prompt",
            "purpose": "Used offline to pre-populate each question's PIAC category and "
                       "answer-format hint (later reviewed by hand). Defines the four "
                       "categories and the rule of thumb by degree of ambiguity.",
            "text": build_enhancement_prompt({
                "question": "{question}",
                "answer": "{answer}",
                "distractors": "{distractors}",
            }),
        },
    ]


def _clean_bibtex(raw: str) -> str:
    """Drop local-only BibTeX fields (e.g. Zotero file paths)."""
    drop = frozenset({
        "file", "abstract", "urldate", "keywords", "langid", "copyright",
    })
    kept: list[str] = []
    for line in (raw or "").splitlines():
        m = re.match(r"\s*(\w+)\s*=", line)
        if m and m.group(1).lower() in drop:
            continue
        kept.append(line)
    text = "\n".join(kept).strip()
    if text and not text.endswith("}"):
        text += "\n}"
    return text


def _clean(v: str) -> str:
    v = (v or "").strip()
    return "" if v in {"?", "…", "-", "—"} else v


def _norm_url(tok: str) -> str:
    """Normalize a token to a URL, adding https:// to scheme-less domains."""
    tok = tok.strip().strip(";,")
    if tok.startswith("http"):
        return tok
    if re.match(r"^[\w.-]+\.\w{2,}(/|$)", tok):   # e.g. arxiv.org/abs/1234
        return "https://" + tok
    return ""


def _urls(cell: str) -> list[str]:
    out: list[str] = []
    for tok in _clean(cell).replace(";", " ").split():
        u = _norm_url(tok)
        if u and u not in out:
            out.append(u)
    return out


def _links(*cells: str) -> list[dict]:
    """Split possibly-multi-URL cells into {label, url} entries."""
    out, seen = [], set()
    for cell in cells:
        for url in _urls(cell):
            if url in seen:
                continue
            seen.add(url)
            host = url.split("/")[2].replace("www.", "")
            label = ("arXiv" if "arxiv" in host else
                     "Hugging Face" if "huggingface" in host else
                     "GitHub" if "github" in host else
                     "Airtable" if "airtable" in host else
                     "Nature" if "nature" in host else host)
            out.append({"label": label, "url": url})
    return out


def latest_benchmark_overview() -> Path | None:
    if not BENCH_OVERVIEWS.exists():
        return None
    files = sorted(BENCH_OVERVIEWS.glob("benchmark_overview_*.csv"))
    return files[-1] if files else None


def load_benchmarks() -> list[dict]:
    """Read the newest benchmark_overview_*.csv into benchmark dicts (source of truth)."""
    path = latest_benchmark_overview()
    if not path:
        raise FileNotFoundError(
            "no benchmark_overview_*.csv in data/benchmarks/overviews/")
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if _clean(r.get("Status", "")).lower() != "confirmed":
                continue
            year = _clean(r.get("Year", ""))
            if not year:
                continue
            name = _clean(r.get("Known name", ""))
            if not name:
                continue
            ext = _clean(r.get("Extended benchmark name", ""))
            paper = _clean(r.get("Paper title", ""))
            paper_link = r.get("Paper link", "")
            dataset_link = r.get("Dataset link", "")
            codebase_link = r.get("Codebase link", "")
            rows.append({
                "name": name,
                "extended": ext or paper,
                "paper_title": paper,
                "domain": _clean(r.get("Type", "")),
                "format": _clean(r.get("Q type", "")),
                "year": year,
                "modalities": _clean(r.get("Modalities", "")),
                "skills": _clean(r.get("Skills and categories", "")),
                "sources": _clean(r.get("Data sources", "")),
                "size": _clean(r.get("Size", "")),
                "models": "",
                "links": _links(paper_link, dataset_link, codebase_link),
                "paper_url": next(iter(_urls(paper_link)), ""),
                "hf_url": next(
                    (u for u in _urls(dataset_link) if "huggingface" in u), ""),
                "code_url": next(
                    (u for u in _urls(codebase_link) if "github" in u),
                    next(iter(_urls(codebase_link)), "")),
                "bibtex": _clean(_clean_bibtex(r.get("Citation", ""))),
                "status": _clean(r.get("Status", "")),
            })
    rows.sort(key=lambda b: (b["year"], b["name"].lower()))
    question_counts = benchmark_question_counts(rows)
    for row in rows:
        row["question_count"] = question_counts.get(row["name"], 0)
        row["has_questions"] = row["question_count"] > 0
        row["questions_url"] = f"data/questions/{_question_file_key(row['name'])}.json" if row["has_questions"] else ""
    return rows


def build_evaluation() -> dict:
    """PIAC taxonomy (the five-paragraph framing), concepts, from the live module."""
    from src.analysis.taxonomy import (
        MOTIVATION, PIEC_ORDER, RULE_OF_THUMB, RULE_OF_THUMB_ITEMS,
    )

    # Verbatim from paper/paper.tex §"PIAC Framework" so the site mirrors the paper.
    intro = (
        "To this end, we propose a listener-centered taxonomy organized around four "
        "modes of musical engagement, each corresponding to a distinct degree of "
        "ambiguity: Perceptual, Inferential, Emotional, and Contextual content. For "
        "each category we discuss (1) the nature of the information, (2) its "
        "epistemic status, in particular the degree to which consensus is expected, "
        "(3) representative examples, (4) an appropriate evaluation methodology, and "
        "(5) an illustrative question."
    )
    PAPER = {
        "perceptual": {
            "subtitle": "information directly measurable from the audio signal, "
                        "admitting a single ground truth",
            "information": "Perceptual content comprises anything that is measurable "
                           "from the audio itself. This category requires neither prior "
                           "knowledge nor active reasoning.",
            "ambiguity": "The defining characteristic is the absence of reasonable "
                         "disagreement, given a predefined answer format: a given note "
                         "corresponds to A4 or it does not; a note onset occurs at a "
                         "specific time or it does not.",
            "coverage": "This category includes objective signal-level attributes or "
                        "audio features, such as pitch, timing, duration, loudness, "
                        "instrumentation, and lyrics. Musical descriptors that don't "
                        "fall into this category include meter, as it is not physically "
                        "present in the signal and may be interpreted differently by "
                        "different listeners (such as 4/4 or 2/2), lacking a clear "
                        "ground truth.",
            "evaluation": "Evaluation within this category can proceed via exact "
                          "semantic match or within a predefined tolerance. A "
                          "constrained answer is often required to increase comparability "
                          "between prediction and reference.",
            "example_q": "What note is played by the violin at 0:31:23? Answer in "
                         "scientific pitch notation.",
            "example_a": "A4.",
        },
        "inferential": {
            "subtitle": "information derived from the audio through expert listening "
                        "and analytical reasoning, for which expert consensus is "
                        "expected, although limited disagreement may remain",
            "information": "Inferential content consists of musical properties that "
                           "can be derived from the audio through expert listening and "
                           "analytical reasoning.",
            "ambiguity": "The claims are intersubjective: trained listeners tend to "
                         "converge on an answer, but some degree of disagreement "
                         "remains possible.",
            "coverage": "This category includes harmonic function, formal "
                        "segmentation, phrase structure, genre attribution, voice "
                        "leading, and other aspects of musical organization.",
            "evaluation": "Evaluation at this level should account for justified "
                          "expert-annotated alternatives. Answers must be explicitly or "
                          "implicitly substantiable in perceptual content. A claim about "
                          "a theme's boundaries, for instance, should be traceable to "
                          "observable features such as recurring melodic material or "
                          "harmonic closure, even though identifying the theme itself "
                          "requires some degree of interpretation.",
            "example_q": "[In a situation where a B♭ is played as a grace note to "
                         "an A, above an A7 chord] What is the name of this chord?",
            "example_a": "A7, or A9.",
        },
        "experiential": {
            "subtitle": "information related to the subjective experience of the "
                        "listener, for which no consensus is expected or desirable",
            "information": "Experiential content captures a listener's personal experience "
                           "of mood, feeling, interpretation, tension, and direction.",
            "ambiguity": "By definition, these claims are subjective and should not be "
                         "resolved by consensus, as there is no single right answer.",
            "coverage": "This category includes felt mood, character, tension, direction, "
                        "intimacy, energy, aesthetic quality, and personal response. It "
                        "excludes a composer's inspiration or intention. Analysis for "
                        "which general agreement is desired is inferential.",
            "evaluation": "Evaluation should accommodate multiple correct answers by "
                          "focusing on core criteria: the plausibility of the experiential "
                          "description (whether it is musically reasonable), internal "
                          "consistency (ensuring different parts of the response cohere), "
                          "and grounding (verifying that experiential claims are supported "
                          "by perceptual or inferential references). For example, "
                          "describing a passage as “tender” gains substance if "
                          "it is supported by references to soft dynamics, legato "
                          "articulation, and sustained harmonic resolution.",
            "example_q": "Where does the audio feel most dramatic to you?",
            "example_a": "Any spot that can be conceived as the most dramatic spot in "
                         "the audio by an engaged human listener.",
        },
        "contextual": {
            "subtitle": "factual knowledge about the music external to the audio "
                        "signal, admitting a single ground truth",
            "information": "Contextual content consists of factual information that is "
                           "associated with the music through historical or physical "
                           "context and admits a single ground truth.",
            "ambiguity": "Contextual claims are not ambiguous in principle: they admit "
                         "a single ground truth. When contextual information is unknown "
                         "or unavailable, the correct response is to acknowledge that "
                         "uncertainty.",
            "coverage": "This includes the composer, performer, name, date of "
                        "recording, or the audio's reception and influence. In contrast, "
                        "detecting genre from audio is inferential and ambiguous.",
            "evaluation": "Evaluation should proceed via exact semantic match.",
            "example_q": "Who is the composer of the piece I just played?",
            "example_a": "Mozart.",
        },
    }
    categories = [{"key": k, **PAPER[k]} for k in PIEC_ORDER]


    return {
        "intro": intro,
        "categories": categories,
        "rule_of_thumb": RULE_OF_THUMB,
        "rule_of_thumb_items": RULE_OF_THUMB_ITEMS,
        "motivation": MOTIVATION,
    }


def _convert_one(src: str, dst: str) -> None:
    """Worker: WAV -> mono OGG/Vorbis. Run in its own process so a native
    libsndfile crash on a malformed clip cannot take down the whole build."""
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(src)
    if getattr(audio, "ndim", 1) > 1:              # downmix to mono
        audio = audio.mean(axis=1)
    sf.write(dst, np.ascontiguousarray(audio, dtype=np.float32), sr,
             format="OGG", subtype="VORBIS")


def transcode_audio(stems: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    import multiprocessing as mp

    AUDIO_OUT.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    mapping: dict[tuple[str, str], str] = {}
    done = skipped = missing = failed = 0
    fails: list[str] = []
    for dataset, stem in sorted(stems):
        out = AUDIO_OUT / dataset / f"{stem}.ogg"
        out.parent.mkdir(parents=True, exist_ok=True)
        mapping[(dataset, stem)] = f"audio/{dataset}/{stem}.ogg"
        if out.exists() and out.stat().st_size > 0:
            skipped += 1
            continue
        src = AUDIO_SRC / f"{stem}.wav"
        if not src.exists():
            missing += 1
            mapping.pop((dataset, stem), None)
            continue
        tmp = out.with_suffix(".ogg.part")
        p = ctx.Process(target=_convert_one, args=(str(src), str(tmp)))
        p.start()
        p.join(60)
        if p.is_alive():
            p.terminate(); p.join()
        if p.exitcode == 0 and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(out)
            done += 1
        else:                                      # crashed/timed out on this clip
            tmp.unlink(missing_ok=True)
            mapping.pop((dataset, stem), None)
            failed += 1
            fails.append(f"{dataset}/{stem}")
    print(f"  audio: transcoded {done}, kept {skipped}, missing {missing}, failed {failed}")
    if fails:
        print("    failed clips (served without a player):", ", ".join(fails[:10]),
              "…" if len(fails) > 10 else "")
    return mapping


def existing_site_audio(stems: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Map stems to website audio files already present under docs/audio."""
    mapping: dict[tuple[str, str], str] = {}
    for dataset, stem in stems:
        organized = [
            (AUDIO_OUT / dataset / f"{stem}.ogg", f"audio/{dataset}/{stem}.ogg"),
            (AUDIO_OUT / dataset / f"{stem}.wav", f"audio/{dataset}/{stem}.wav"),
            (AUDIO_OUT / dataset / f"{stem}.mp3", f"audio/{dataset}/{stem}.mp3"),
            (AUDIO_OUT / dataset / "sdd" / f"{stem}.2min.mp3", f"audio/{dataset}/sdd/{stem}.2min.mp3"),
            (AUDIO_OUT / dataset / "musiccaps" / f"{stem}.wav", f"audio/{dataset}/musiccaps/{stem}.wav"),
        ]
        for path, rel in organized:
            if path.exists() and path.stat().st_size > 0:
                mapping[(dataset, stem)] = rel
                break
        if (dataset, stem) in mapping:
            continue
        ogg = AUDIO_OUT / f"{stem}.ogg"
        wav = AUDIO_OUT / f"{stem}.wav"
        if ogg.exists() and ogg.stat().st_size > 0:
            mapping[(dataset, stem)] = f"audio/{stem}.ogg"
        elif wav.exists() and wav.stat().st_size > 0:
            mapping[(dataset, stem)] = f"audio/{stem}.wav"
    return mapping


def _hosted_audio_rel(dataset: str, audio_source: str) -> str:
    """Return the hosted-audio path relative to AMI_AUDIO_BASE_URL."""
    sources = _audio_sources(audio_source)
    first = sources[0] if sources else ""
    if not first:
        return ""
    first = first.replace("\\", "/").lstrip("./")

    if dataset == "muchomusic" and ":" in first and "/" not in first:
        source, _, ident = first.partition(":")
        ident = ident.strip()
        if source == "sdd" and ident:
            return f"muchomusic/sdd/{ident}.2min.mp3"
        if source == "musiccaps" and ident:
            return f"muchomusic/musiccaps/{ident}.wav"

    if ":" in first and "/" not in first:
        _, _, first = first.partition(":")
    first = first.removeprefix("audio/").removeprefix("data/")
    return f"{dataset}/{first}" if first else ""


def hosted_audio_url(dataset: str, audio_source: str) -> str:
    if dataset in METADATA_ONLY_AUDIO_DATASETS:
        return ""
    rel = _hosted_audio_rel(dataset, audio_source)
    if not rel:
        return ""
    return f"{HOSTED_AUDIO_BASE_URL}/{quote(rel, safe='/')}"


def hosted_audio_urls(dataset: str, audio_source: str) -> list[str]:
    """Return one hosted URL for every clip referenced by a question."""
    return [
        url for source in _audio_sources(audio_source)
        if (url := hosted_audio_url(dataset, json.dumps([source])))
    ]


def write_json(name: str, payload, *, emit_js: bool = True) -> Path:
    """Write one generated site JSON payload."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8")
    if emit_js:
        key = path.relative_to(DATA_DIR).with_suffix("").as_posix()
        js = (
            "window.__AMI_DATA__ = window.__AMI_DATA__ || {};\n"
            f"window.__AMI_DATA__[{json.dumps(key)}] = {text}"
        )
        js_path = path.with_suffix(".js")
        js_path.write_text(js, encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)} ({len(text) / 1e6:.2f} MB)")
    return path


def ensure_docs() -> None:
    DOCS.mkdir(exist_ok=True)


def build_meta() -> None:
    questions_path = DATA_DIR / "questions.json"
    n_questions = 0
    if questions_path.exists():
        n_questions = len(json.loads(questions_path.read_text(encoding="utf-8")))
    write_json("meta.json", {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo_url": REPO_URL,
        "n_questions": n_questions,
        "piac_order": PIAC_ORDER,
    })


def build_news_target() -> None:
    write_json("news.json", NEWS)


def model_catalog_payload(all_models: list[dict] | None = None) -> list[dict]:
    all_models = all_models or load_models()
    return [
        {"id": m["id"], "label": m["label"], **{k: m.get(k, "") for k in MODEL_META}}
        for m in all_models
    ]


def build_models_target() -> None:
    write_json("models.json", model_catalog_payload())


def build_benchmarks_target() -> None:
    write_json("benchmarks.json", load_benchmarks())


def build_evaluation_target() -> None:
    write_json("evaluation.json", build_evaluation())


def build_prompts_target() -> None:
    write_json("prompts.json", build_prompts())


def question_payload(no_audio: bool) -> tuple[list[dict], set[tuple[str, str]], dict[str, str], list[str]]:
    all_models = load_models()
    eval_models = [m for m in all_models if m.get("mcq_csv")]
    models = {}
    for m in eval_models:
        data = load_model(m)
        if data:
            models[m["id"]] = data
    benchmarks = load_benchmarks()
    questions, stems, q_piac, eval_qids = load_questions(benchmarks, models)

    audio_map = {} if HOSTED_AUDIO_BASE_URL else existing_site_audio(stems)
    if not no_audio and not HOSTED_AUDIO_BASE_URL:
        missing_mmar = {pair for pair in stems if pair[0] == "mmar" and pair not in audio_map}
        audio_map = {**audio_map, **transcode_audio(missing_mmar)}
    hosted_pairs: set[tuple[str, str]] = set()
    for rec in questions:
        dataset = rec.get("audio_dataset") or _compact_key(rec["benchmark"])
        if HOSTED_AUDIO_BASE_URL:
            audio_urls = hosted_audio_urls(dataset, rec.get("audio_source", ""))
            rec["audio_urls"] = audio_urls
            rec["audio"] = audio_urls[0] if audio_urls else None
            hosted_pairs.update((dataset, stem) for stem in rec["audio_stems"][:len(audio_urls)])
        else:
            audio_urls = [
                audio_map[(dataset, stem)]
                for stem in rec["audio_stems"]
                if (dataset, stem) in audio_map
            ]
            rec["audio_urls"] = audio_urls
            rec["audio"] = audio_urls[0] if audio_urls else None
        del rec["audio_stem"]
        del rec["audio_stems"]
        del rec["audio_source"]
        del rec["_cached_audio_known"]
        del rec["_cached_audio"]
    if HOSTED_AUDIO_BASE_URL:
        print(
            f"  audio: hosted {len(hosted_pairs)}/{len(stems)} available clips "
            f"from {HOSTED_AUDIO_BASE_URL}"
        )
    return questions, stems, q_piac, eval_qids


def build_questions_target(no_audio: bool) -> None:
    questions, _, _, _ = question_payload(no_audio)
    write_json("questions.json", questions, emit_js=False)
    write_json("benchmark_questions.json", questions, emit_js=False)
    by_benchmark: dict[str, list[dict]] = {}
    for question in questions:
        by_benchmark.setdefault(question.get("benchmark") or "benchmark", []).append(question)
    QUESTION_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in list(QUESTION_DATA_DIR.glob("*.json")) + list(QUESTION_DATA_DIR.glob("*.js")):
        path.unlink()
    for benchmark, rows in sorted(by_benchmark.items()):
        write_json(f"questions/{_question_file_key(benchmark)}.json", rows)


def build_overview_target() -> None:
    all_models = load_models()
    eval_models = [m for m in all_models if m.get("mcq_csv")]
    models = {}
    for m in eval_models:
        data = load_model(m)
        if data:
            models[m["id"]] = data
    benchmarks = load_benchmarks()
    questions, _, q_piac, eval_qids = load_questions(benchmarks, models)
    del questions
    write_json("overview.json", {
        mid: overview_for(data, eval_qids, q_piac)
        for mid, data in models.items()
    })


def build_literature_results_target() -> None:
    from src.reporting.literature_results import rebuild_database, site_payload

    database = rebuild_database()
    write_json("literature_results.json", site_payload(database))


def build_paper_target() -> None:
    ensure_docs()
    if not PAPER_PDF.exists():
        raise FileNotFoundError(PAPER_PDF)
    target = DOCS / "paper.pdf"
    target.write_bytes(PAPER_PDF.read_bytes())
    print(f"  wrote {target.relative_to(ROOT)}")


def build_audio_target() -> None:
    benchmarks = load_benchmarks()
    questions, stems, _, _ = load_questions(benchmarks, {})
    del questions
    transcode_audio(stems)


def _print_targets() -> None:
    print("Available site build targets:")
    for target in DATA_TARGETS:
        print(f"  {target}")
    print("\nExamples:")
    print("  python renderers/site/build_site.py --target questions --no-audio")
    print("  python renderers/site/build_site.py --target benchmarks")


def main() -> None:
    ap = argparse.ArgumentParser(description="Update one specific generated website artifact.")
    ap.add_argument("--target", action="append", choices=DATA_TARGETS,
                    help="specific artifact to update; repeat for multiple targets")
    ap.add_argument("--no-audio", action="store_true", help="when targeting questions, keep existing audio links only")
    ap.add_argument("--list", action="store_true", help="list target names")
    args = ap.parse_args()

    if args.list or not args.target:
        _print_targets()
        return

    ensure_docs()
    handlers = {
        "meta": build_meta,
        "news": build_news_target,
        "models": build_models_target,
        "benchmarks": build_benchmarks_target,
        "evaluation": build_evaluation_target,
        "overview": build_overview_target,
        "literature-results": build_literature_results_target,
        "prompts": build_prompts_target,
        "questions": lambda: build_questions_target(args.no_audio),
        "paper": build_paper_target,
        "audio": build_audio_target,
    }
    for target in args.target:
        handlers[target]()


if __name__ == "__main__":
    main()

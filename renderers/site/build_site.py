"""Build the static GitHub Pages site for the music-understanding explorer.

Reads the normalized benchmark questions, available MCQ + PIAC-judged OEQ
results, and the live prompt sources, then emits a self-contained site under
``docs/``:

    docs/index.html  docs/styles.css  docs/app.js   (static, hand-written)
    docs/data/*.json                                (generated here)
    docs/audio/<dataset>/...                        (local audio, gitignored)

Audio can be served locally from gitignored ``docs/audio`` while developing, or
from an external static host by setting ``AMI_AUDIO_BASE_URL`` before building
the site JSON. The hosted layout mirrors ``data/audio/<dataset>/...`` so the
website can play all available benchmark clips without committing the audio.

    python renderers/site/build_site.py --list
    AMI_AUDIO_BASE_URL=https://example.com/audio python renderers/site/build_site.py --target questions --no-audio
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
AUDIO_OUT = DOCS / "audio"
AUDIO_DATA = ROOT / "data" / "audio"
BENCHMARK_DATA = ROOT / "data" / "benchmarks"
AUDIO_SRC = ROOT / "data" / "audio" / "mmar"
PAPER_PDF = ROOT / "paper" / "paper.pdf"
REPO_URL = "https://github.com/milan477/toward-ami"
HOSTED_AUDIO_BASE_URL = os.environ.get("AMI_AUDIO_BASE_URL", "").rstrip("/")
DATA_TARGETS = (
    "meta",
    "news",
    "models",
    "benchmarks",
    "evaluation",
    "overview",
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
                "affective, or contextual — by the nature of its ground truth — and let "
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

PIAC_ORDER = ["perceptual", "inferential", "affective", "contextual"]


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
    if _is_empty_list_marker(raw):
        return []
    try:
        val = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return [str(raw)] if raw else []
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip() and not _is_empty_list_marker(str(x))]
    return [str(val)] if str(val).strip() and not _is_empty_list_marker(str(val)) else []


def _compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _display_name_map(benchmarks: list[dict]) -> dict[str, str]:
    names = {_compact_key(b["name"]): b["name"] for b in benchmarks}
    return {
        "mmar": "MMAR",
        "mmau_pro": names.get("mmaupro", "MMAU-Pro"),
        "muchomusic": names.get("muchomusic", "MuChoMusic"),
        **names,
    }


def _stage_path(dataset_dir: Path) -> Path | None:
    name = dataset_dir.name
    for suffix in (
        "normalized_selected_annotated",
        "normalized_selected",
        "ready",
        "normalized",
    ):
        path = dataset_dir / f"{name}_{suffix}.csv"
        if path.exists():
            return path
    return None


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


def _audio_stem(audio_url: str) -> str:
    first = str(audio_url or "").split(";", 1)[0].strip()
    if not first:
        return ""
    if ":" in first and "/" not in first:
        _, _, ident = first.partition(":")
        return Path(ident).name.rsplit(".", 1)[0]
    return Path(first).name.rsplit(".", 1)[0]


def _skills_text(row: dict) -> str:
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


def _site_category_values(dataset: str, row: dict) -> dict[str, list[str]]:
    from src.analysis.statistics import category_values_for_row

    categories = category_values_for_row(dataset, row)
    for key, values in list(categories.items()):
        categories[key] = [
            "none specified" if _is_empty_list_marker(value) else value
            for value in values
        ]
    if dataset == "mmau_pro" and _has_empty_list_marker(row.get("skills", "")) and not categories.get("skill"):
        categories["skill"] = ["none specified"]
    return categories


def _row_piac(row: dict) -> str:
    val = (row.get("category") or row.get("piac") or "").strip().lower()
    return val if val in PIAC_ORDER else ""


def _question_id(dataset: str, row: dict, idx: int) -> str:
    if row.get("qid"):
        return row["qid"]
    stem = _audio_stem(row.get("audio_url", ""))
    return stem or f"{dataset}:{idx + 1}"


def load_questions(benchmarks: list[dict], models: dict[str, dict]) -> tuple[list[dict], set[tuple[str, str]], dict[str, str], list[str]]:
    from src.analysis.statistics import (
        _audio_duration,
        _audio_names,
        _build_audio_index,
    )

    display_names = _display_name_map(benchmarks)
    questions: list[dict] = []
    stems: set[tuple[str, str]] = set()
    q_piac: dict[str, str] = {}
    eval_qids: list[str] = []
    audio_indexes: dict[str, dict] = {}

    def audio_durations(dataset: str, audio_url: str) -> list[float]:
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
                stem = _audio_stem(r.get("audio_url", ""))
                piac = _row_piac(r)
                if stem:
                    stems.add((dataset, stem))
                if piac:
                    q_piac[qid] = piac
                rec = {
                    "qid": qid,
                    "benchmark": benchmark,
                    "audio_dataset": dataset,
                    "question": r.get("question", ""),
                    "question_type": r.get("question_type", ""),
                    "piac": piac,
                    "category_1": r.get("category_1", ""),
                    "category_2": r.get("category_2", ""),
                    "category_3": r.get("category_3", ""),
                    "category_4": r.get("category_4", ""),
                    "skills": _skills_text(r),
                    "answer_format": r.get("answer_format", ""),
                    "correct_answer": r.get("correct_answer", ""),
                    "distractors": _parse_distractors(r.get("distractors", "")),
                    "audio_stem": stem,
                    "audio_duration_seconds": audio_durations(dataset, r.get("audio_url", "")),
                    "categories": _site_category_values(dataset, r),
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
        "hallucinated": bool(jud.get("hallucinated")),
        "hallucination_level": jud.get("hallucination_level"),
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
        hall = sum(1 for r in rows if r["hallucinated"]) / n
        return {"n": n, "mcq_acc": mcq, "oeq_mean": oeq_mean,
                "oeq_acc": oeq_acc, "halluc_rate": hall}

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
    from src.evaluation.prompts import (
        INSTRUCTION_MCQ, INSTRUCTION_OEQ, INSTRUCTION_OEQ_GUIDED,
        PIAC_JUDGE_PROMPT, build_mcq, build_oeq,
    )
    from src.analysis.prompts import ANNOTATION_PROMPT, category_block
    from src.analysis.taxonomy import RULE_OF_THUMB

    mcq = build_mcq(
        "What instrument plays the main melody?",
        "Violin", ["Piano", "Flute", "Trumpet"], "demo-qid")
    oeq_unguided_ex = build_oeq(
        "What does the music feel like?", "Melancholic")["prompt"]
    oeq_guided_ex = build_oeq(
        "What instrument plays the main melody?", "Violin",
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
                    "text": INSTRUCTION_MCQ,
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
                    "text": INSTRUCTION_OEQ,
                    "example": oeq_unguided_ex,
                },
                {
                    "label": "Format-guided",
                    "text": INSTRUCTION_OEQ_GUIDED,
                    "example": oeq_guided_ex,
                },
            ],
        },
        {
            "name": "PIAC judge prompt",
            "purpose": "A category-aware LLM-as-judge (local Qwen3) that grades each "
                       "open-ended answer 0-4 and separately flags hallucination. The "
                       "grading rubric injected into {rubric} depends on the question's "
                       "PIAC category.",
            "text": PIAC_JUDGE_PROMPT,
        },
        {
            "name": "Annotation prompt",
            "purpose": "Used offline to pre-populate each question's PIAC category and "
                       "answer-format hint (later reviewed by hand). Defines the four "
                       "categories and the rule of thumb by degree of ambiguity.",
            "text": ANNOTATION_PROMPT.format(
                categories=category_block(),
                rule=RULE_OF_THUMB,
                question="{question}",
                qtype="{qtype}",
                answer="{answer}",
                options="{options}",
            ),
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
    return rows


def build_evaluation() -> dict:
    """PIAC taxonomy (the five-paragraph framing), concepts, from the live module."""
    from src.analysis.taxonomy import (
        MOTIVATION, PIAC_ORDER, RULE_OF_THUMB, RULE_OF_THUMB_ITEMS, SKILL_AXIS,
    )

    # Verbatim from paper/paper.tex §"PIAC Framework" so the site mirrors the paper.
    intro = (
        "To this end, we propose a listener-centered taxonomy organized around four "
        "modes of musical engagement, each corresponding to a distinct degree of "
        "ambiguity: Perceptual, Inferential, Affective, and Contextual content. For "
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
        "affective": {
            "subtitle": "information related to the subjective experience of the "
                        "listener, for which no consensus is expected or desirable",
            "information": "Affective content captures how music is experienced by a "
                           "listener and relates to expression and emotional response.",
            "ambiguity": "By definition, these claims are subjective and should not be "
                         "resolved by consensus, as there is no single right answer.",
            "coverage": "This category includes perceived mood, character, tension, "
                        "intimacy, energy, aesthetic quality, and personal response.",
            "evaluation": "Evaluation should accommodate multiple correct answers by "
                          "focusing on core criteria: the plausibility of the affective "
                          "description (whether it is musically reasonable), internal "
                          "consistency (ensuring different parts of the response cohere), "
                          "and grounding (verifying that affective claims are supported "
                          "by perceptual or inferential references). For example, "
                          "describing a passage as “tender” gains substance if "
                          "it is supported by references to soft dynamics, legato "
                          "articulation, and sustained harmonic resolution.",
            "example_q": "What is the most dramatic spot in the audio?",
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
    categories = [{"key": k, **PAPER[k]} for k in PIAC_ORDER]

    axis_label = {"tone": "Tone", "time": "Time", "tone_time": "Tone × Time",
                  "context": "Context", "other": "Other"}
    concepts: dict[str, list[str]] = {}
    for skill, axis in SKILL_AXIS.items():
        concepts.setdefault(axis_label.get(axis, axis), []).append(skill)

    return {
        "intro": intro,
        "categories": categories,
        "rule_of_thumb": RULE_OF_THUMB,
        "rule_of_thumb_items": RULE_OF_THUMB_ITEMS,
        "motivation": MOTIVATION,
        "concepts": concepts,
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


def _audio_lookup_keys(stem: str) -> tuple[str, ...]:
    return (
        stem,
        f"{stem}.wav",
        f"{stem}.mp3",
        f"{stem}.ogg",
        f"{stem}.flac",
        f"{stem}.m4a",
        f"{stem}.opus",
        f"{stem}.2min",
        f"{stem}.2min.mp3",
    )


def hosted_audio(stems: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Map stems to externally hosted audio URLs mirroring data/audio."""
    if not HOSTED_AUDIO_BASE_URL:
        return {}

    from src.analysis.statistics import _build_audio_index

    mapping: dict[tuple[str, str], str] = {}
    indexes: dict[str, dict[str, Path]] = {}
    for dataset, stem in stems:
        if dataset not in indexes:
            indexes[dataset] = _build_audio_index(dataset)
        index = indexes[dataset]
        path = None
        for key in _audio_lookup_keys(stem):
            path = index.get(key)
            if path:
                break
        if not path:
            continue
        try:
            rel = path.relative_to(AUDIO_DATA)
        except ValueError:
            rel = Path(dataset) / path.name
        mapping[(dataset, stem)] = f"{HOSTED_AUDIO_BASE_URL}/{quote(rel.as_posix(), safe='/')}"

    print(
        f"  audio: hosted {len(mapping)}/{len(stems)} available clips "
        f"from {HOSTED_AUDIO_BASE_URL}"
    )
    return mapping


def write_json(name: str, payload) -> Path:
    """Write one generated site JSON payload."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8")
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

    audio_map = hosted_audio(stems) if HOSTED_AUDIO_BASE_URL else existing_site_audio(stems)
    if not no_audio and not HOSTED_AUDIO_BASE_URL:
        missing_mmar = {pair for pair in stems if pair[0] == "mmar" and pair not in audio_map}
        audio_map = {**audio_map, **transcode_audio(missing_mmar)}
    for rec in questions:
        dataset = rec.get("audio_dataset") or _compact_key(rec["benchmark"])
        rec["audio"] = audio_map.get((dataset, rec["audio_stem"]))
        del rec["audio_stem"]
    return questions, stems, q_piac, eval_qids


def build_questions_target(no_audio: bool) -> None:
    questions, _, _, _ = question_payload(no_audio)
    write_json("questions.json", questions)
    write_json("benchmark_questions.json", questions)


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
        "prompts": build_prompts_target,
        "questions": lambda: build_questions_target(args.no_audio),
        "paper": build_paper_target,
        "audio": build_audio_target,
    }
    for target in args.target:
        handlers[target]()


if __name__ == "__main__":
    main()

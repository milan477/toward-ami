"""Build the static GitHub Pages site for the MMAR music-understanding explorer.

Reads the processed MMAR questions, both models' MCQ + PIAC-judged OEQ results,
and the live prompt sources, then emits a self-contained site under ``docs/``:

    docs/index.html  docs/styles.css  docs/app.js   (static, hand-written)
    docs/data/*.json                                (generated here)
    docs/audio/<stem>.ogg                           (transcoded from data/audio/mmar)

Audio is transcoded WAV -> mono OGG/Vorbis so the whole payload fits comfortably
on GitHub Pages (the source WAVs are ~1 GB; the OGGs are tens of MB).

    python site/build_site.py            # full build (data + audio)
    python site/build_site.py --no-audio # data only (fast, keeps existing oggs)

The model catalog is read from the newest
``data/models/overviews/model_overview_<date>.csv`` (source of truth) and written
out as ``docs/data/models.json``. Benchmarks likewise come from the newest
``data/benchmarks/overviews/benchmark_overview_<date>.csv`` → ``docs/data/benchmarks.json``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
DATA_DIR = DOCS / "data"
AUDIO_OUT = DOCS / "audio"
PROCESSED = ROOT / "data" / "benchmarks" / "mmar" / "mmar_ready.csv"
AUDIO_SRC = ROOT / "data" / "audio" / "mmar"
PAPER_PDF = ROOT / "paper" / "paper.pdf"
REPO_URL = "https://github.com/milan477/toward-ami"

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


def load_model(m: dict) -> dict:
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
    from src.piac.prompts import (
        INSTRUCTION_MCQ, INSTRUCTION_OEQ, INSTRUCTION_OEQ_GUIDED,
        build_mcq, build_oeq,
    )
    from src.piac.judge import JUDGE_TEMPLATE, STRATEGY_RUBRIC
    from src.piac.annotate import PROMPT_TEMPLATE as ANNOTATE_TEMPLATE

    mcq_ex = build_mcq(
        "What instrument plays the main melody?",
        "Violin", ["Piano", "Flute", "Trumpet"], "demo-qid")["prompt"]
    oeq_ex = build_oeq(
        "What instrument plays the main melody?", "Violin",
        answer_format="a single instrument name", example="Cello")["prompt"]

    rubric_block = "\n\n".join(
        f"[{k}]\n{v}" for k, v in STRATEGY_RUBRIC.items())

    return [
        {
            "name": "MCQ prompt",
            "purpose": "The original multiple-choice form. Options are shuffled "
                       "deterministically per question and the model returns only a "
                       "letter; graded automatically against the correct option. This "
                       "is the 'apparent' score.",
            "text": f"Instruction:\n{INSTRUCTION_MCQ}\n\nExample built prompt:\n{mcq_ex}",
        },
        {
            "name": "OEQ prompt",
            "purpose": "The same question with the options stripped away. The model "
                       "must produce the answer unaided, in 1-2 sentences. Graded by "
                       "the PIAC judge below; this is the 'actual' score. A per-question "
                       "answer-format hint steers only the form of the answer, never its "
                       "content.",
            "text": (f"Instruction (unguided):\n{INSTRUCTION_OEQ}\n\n"
                     f"Instruction (format-guided):\n{INSTRUCTION_OEQ_GUIDED}\n\n"
                     f"Example built prompt:\n{oeq_ex}"),
        },
        {
            "name": "PIAC judge prompt",
            "purpose": "A category-aware LLM-as-judge (local Qwen3) that grades each "
                       "open-ended answer 0-4 and separately flags hallucination. The "
                       "grading rubric injected into {rubric} depends on the question's "
                       "PIAC category (see the four rubrics below).",
            "text": JUDGE_TEMPLATE,
        },
        {
            "name": "Judge rubrics (per PIAC category)",
            "purpose": "The category-specific grading rule slotted into the judge "
                       "prompt. Perceptual/contextual/inferential are graded binary "
                       "(4 or 0); affective is graded 0-4 on plausibility, consistency "
                       "and grounding.",
            "text": rubric_block,
        },
        {
            "name": "Annotation prompt",
            "purpose": "Used offline to pre-populate each question's PIAC category and "
                       "answer-format hint (later reviewed by hand). Defines the four "
                       "categories and the rule of thumb by degree of ambiguity.",
            "text": ANNOTATE_TEMPLATE,
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
    return rows


def build_evaluation() -> dict:
    """PIAC taxonomy (the five-paragraph framing), concepts, from the live module."""
    from src.piac.taxonomy import (
        PIAC_ORDER, RULE_OF_THUMB, RULE_OF_THUMB_ITEMS, MOTIVATION, SKILL_AXIS,
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


def transcode_audio(stems: set[str]) -> dict[str, str]:
    import multiprocessing as mp

    AUDIO_OUT.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    mapping: dict[str, str] = {}
    done = skipped = missing = failed = 0
    fails: list[str] = []
    for stem in sorted(stems):
        out = AUDIO_OUT / f"{stem}.ogg"
        mapping[stem] = f"audio/{stem}.ogg"
        if out.exists() and out.stat().st_size > 0:
            skipped += 1
            continue
        src = AUDIO_SRC / f"{stem}.wav"
        if not src.exists():
            missing += 1
            mapping.pop(stem, None)
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
            mapping.pop(stem, None)
            failed += 1
            fails.append(stem)
    print(f"  audio: transcoded {done}, kept {skipped}, missing {missing}, failed {failed}")
    if fails:
        print("    failed clips (served without a player):", ", ".join(fails[:10]),
              "…" if len(fails) > 10 else "")
    return mapping


def write_site_data(bundle: dict) -> None:
    """Emit site payload as one JSON file per section under docs/data/."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "meta.json": {
            "generated": bundle["generated"],
            "repo_url": bundle["repo_url"],
            "n_questions": bundle["n_questions"],
            "piac_order": bundle["piac_order"],
        },
        "news.json": bundle["news"],
        "models.json": bundle["models"],
        "benchmarks.json": bundle["benchmarks"],
        "evaluation.json": bundle["evaluation"],
        "overview.json": bundle["overview"],
        "prompts.json": bundle["prompts"],
        "questions.json": bundle["questions"],
    }
    total = 0
    for name, payload in files.items():
        text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        (DATA_DIR / name).write_text(text, encoding="utf-8")
        total += len(text)
    legacy = DOCS / "data.json"
    if legacy.exists():
        legacy.unlink()
    print(f"  wrote docs/data/ ({total / 1e6:.2f} MB, {len(bundle['questions'])} questions)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-audio", action="store_true", help="skip audio transcoding")
    args = ap.parse_args()

    DOCS.mkdir(exist_ok=True)
    if PAPER_PDF.exists():                          # served at docs/paper.pdf
        (DOCS / "paper.pdf").write_bytes(PAPER_PDF.read_bytes())
    all_models = load_models()
    eval_models = [m for m in all_models if m.get("mcq_csv")]
    models = {m["id"]: load_model(m) for m in eval_models}

    questions: list[dict] = []
    stems: set[str] = set()
    q_piac: dict[str, str] = {}
    with PROCESSED.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # Result files are keyed by the audio stem, so we join on it (and use
            # it as the display id — the processed qid is an opaque hash).
            stem = r["audio_url"].split("/")[-1].rsplit(".", 1)[0]
            qid = stem
            stems.add(stem)
            q_piac[qid] = r.get("category") or r.get("piac") or ""
            rec = {
                "qid": qid,
                "question": r["question"],
                "piac": q_piac[qid],
                "category_1": r.get("category_1", ""),
                "category_2": r.get("category_2", ""),
                "category_3": r.get("category_3", ""),
                "skills": r.get("skills", ""),
                "answer_format": r.get("answer_format", ""),
                "correct_answer": r["correct_answer"],
                "distractors": _parse_distractors(r.get("distractors", "")),
                "audio_stem": stem,
            }
            for mid, data in models.items():
                rec[mid] = model_cell(data, qid)
            questions.append(rec)

    audio_map = ({} if args.no_audio else transcode_audio(stems))
    if args.no_audio:
        audio_map = {s: f"audio/{s}.ogg" for s in stems
                     if (AUDIO_OUT / f"{s}.ogg").exists()}
    for rec in questions:
        rec["audio"] = audio_map.get(rec["audio_stem"])
        del rec["audio_stem"]

    qids = [q["qid"] for q in questions]
    bundle = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo_url": REPO_URL,
        "news": NEWS,
        "benchmarks": load_benchmarks(),
        "evaluation": build_evaluation(),
        "n_questions": len(questions),
        "piac_order": PIAC_ORDER,
        "models": [{"id": m["id"], "label": m["label"],
                    **{k: m.get(k, "") for k in MODEL_META}} for m in all_models],
        "overview": {mid: overview_for(data, qids, q_piac)
                     for mid, data in models.items()},
        "questions": questions,
        "prompts": build_prompts(),
    }
    write_site_data(bundle)


if __name__ == "__main__":
    main()

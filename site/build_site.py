"""Build the static GitHub Pages site for the MMAR music-understanding explorer.

Reads the processed MMAR questions, both models' MCQ + PIAC-judged OEQ results,
and the live prompt sources, then emits a self-contained site under ``docs/``:

    docs/index.html  docs/styles.css  docs/app.js   (static, hand-written)
    docs/data.json                                  (generated here)
    docs/audio/<stem>.ogg                           (transcoded from data/audio/mmar)

Audio is transcoded WAV -> mono OGG/Vorbis so the whole payload fits comfortably
on GitHub Pages (the source WAVs are ~1 GB; the OGGs are tens of MB).

    python site/build_site.py            # full build (data + audio)
    python site/build_site.py --no-audio # data only (fast, keeps existing oggs)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
AUDIO_OUT = DOCS / "audio"
PROCESSED = ROOT / "data" / "processed" / "mmar.csv"
AUDIO_SRC = ROOT / "data" / "audio" / "mmar"

MODELS = [
    {
        "id": "af-next",
        "label": "Audio Flamingo Next",
        "mcq_csv": "results/mmar/af-next/music/2026-07-01_01-54-58_summary.csv",
        "oeq_answers": "results/mmar/af-next/music-oeq-piac/.oeq_answers.jsonl",
        "oeq_judged": "results/mmar/af-next/music-oeq-piac/.oeq_piac_judged.jsonl",
    },
    {
        "id": "gemini",
        "label": "Gemini 3 Flash",
        "mcq_csv": "results/mmar/gemini-3-flash-preview/music/2026-07-01_04-33-34_summary.csv",
        "oeq_answers": "results/mmar/gemini-3-flash-preview/music-oeq-piac/.oeq_answers.jsonl",
        "oeq_judged": "results/mmar/gemini-3-flash-preview/music-oeq-piac/.oeq_piac_judged.jsonl",
    },
]

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
    from experiments.oeq_mcq.prompts import (
        INSTRUCTION_MCQ, INSTRUCTION_OEQ, INSTRUCTION_OEQ_GUIDED,
        build_mcq, build_oeq,
    )
    from experiments.piac.judge import JUDGE_TEMPLATE, STRATEGY_RUBRIC
    from experiments.oeq_mcq.annotate import PROMPT_TEMPLATE as ANNOTATE_TEMPLATE

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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-audio", action="store_true", help="skip audio transcoding")
    args = ap.parse_args()

    DOCS.mkdir(exist_ok=True)
    models = {m["id"]: load_model(m) for m in MODELS}

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
        "n_questions": len(questions),
        "piac_order": PIAC_ORDER,
        "models": [{"id": m["id"], "label": m["label"]} for m in MODELS],
        "overview": {mid: overview_for(data, qids, q_piac)
                     for mid, data in models.items()},
        "questions": questions,
        "prompts": build_prompts(),
    }
    (DOCS / "data.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
    size = (DOCS / "data.json").stat().st_size / 1e6
    print(f"  wrote docs/data.json ({size:.2f} MB, {len(questions)} questions)")


if __name__ == "__main__":
    main()

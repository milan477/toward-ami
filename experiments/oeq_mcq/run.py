"""Step 4: run both prompt variants (MCQ + OEQ) on one model, with audio.

For every classified question the model is queried twice — once in multiple-choice
form (graded automatically) and once open-ended (free text, graded later by
judge.py). Results are saved under experiments/results/exp_3_oeq_vs_mcq/<ts>/.

Usage:
    python -m experiments.oeq_mcq.run --model flamingo
    python -m experiments.oeq_mcq.run --model openai:gpt-4o-audio-preview
    python -m experiments.oeq_mcq.run --model openrouter:google/gemini-2.0-flash-001 --limit 5
    python -m experiments.oeq_mcq.run --model flamingo --preview   # no API calls
"""

import argparse
import re
import string
from pathlib import Path

import pandas as pd

from experiments.helpers.models import make_client
from experiments.helpers.results import get_run_metadata, save_results

from .prompts import build_mcq, build_oeq, parse_distractors
from .sample import AUDIO_DIR, SHEET
from .taxonomy import KEYS

EXP_NAME = "exp_3_oeq_vs_mcq"


def _audio_path(audio_url: str) -> Path | None:
    p = AUDIO_DIR / str(audio_url).split("/")[-1]
    return p if p.exists() else None


def extract_letter(response: str, letter_map: dict) -> str | None:
    """Pull the chosen option letter from a free-form model reply."""
    letters = set(letter_map)
    # 1. a standalone letter, optionally like "B." / "(B)" / "B)"
    for m in re.finditer(r"\b([A-Z])\b[.):]?", response):
        if m.group(1) in letters:
            return m.group(1)
    # 2. fall back to exact option-text match
    low = response.strip().lower()
    for ltr, opt in letter_map.items():
        if opt.strip().lower() == low:
            return ltr
    return None


def load_sheet(require_level: bool) -> pd.DataFrame:
    if not SHEET.exists():
        raise SystemExit(f"No classification sheet at {SHEET}. Run: "
                         f"python -m experiments.oeq_mcq.sample")
    df = pd.read_csv(SHEET, dtype=str, keep_default_na=False)
    if require_level:
        labeled = df[df["level"].str.upper().isin(KEYS)]
        if len(labeled) < len(df):
            print(f"  {len(df) - len(labeled)} of {len(df)} rows have no valid level "
                  f"— skipping them. (valid: {', '.join(KEYS)})")
        df = labeled
    return df.reset_index(drop=True)


def run(model_spec: str, limit: int | None = None, preview: bool = False,
        require_level: bool = True) -> None:
    df = load_sheet(require_level)
    if limit:
        df = df.head(limit)

    client = make_client(model_spec)
    info = client.info()
    config = {"model_spec": model_spec, "n_questions": len(df),
              "supports_audio": client.supports_audio, "sheet": str(SHEET)}
    print(f"Model: {info}  |  questions: {len(df)}")

    items, n_skipped = [], 0
    for _, r in df.iterrows():
        audio = _audio_path(r["audio_url"])
        if audio is None:
            n_skipped += 1
            continue

        distractors = parse_distractors(r["distractors"])
        mcq = build_mcq(r["question"], r["correct_answer"], distractors, r["qid"])
        oeq = build_oeq(r["question"], r["correct_answer"])

        if preview:
            print(f"\n[{r['qid']}] level={r['level']}  audio={audio.name}")
            print("  MCQ:", mcq["prompt"].replace("\n", " ")[:140], "…")
            print("  OEQ:", oeq["prompt"].replace("\n", " ")[:140], "…")
            continue

        mcq_resp = client.generate(mcq["prompt"], str(audio), max_tokens=16)
        oeq_resp = client.generate(oeq["prompt"], str(audio), max_tokens=160)
        pred = extract_letter(mcq_resp, mcq["letter_map"])

        items.append({
            "qid": r["qid"], "level": r["level"].upper(), "question": r["question"],
            "audio": audio.name,
            "mcq": {
                "prompt": mcq["prompt"], "options": mcq["options"],
                "correct_letter": mcq["correct_letter"], "response": mcq_resp,
                "pred_letter": pred, "correct": pred == mcq["correct_letter"],
            },
            "oeq": {
                "prompt": oeq["prompt"], "reference_answer": oeq["reference_answer"],
                "response": oeq_resp,
            },
        })
        mark = "✓" if (pred == mcq["correct_letter"]) else "✗"
        print(f"  [{r['qid']}] {r['level']:<8} MCQ {mark} ({pred})  OEQ: {oeq_resp[:60]!r}")

    if preview:
        print(f"\nPreview only — {len(df)} questions, no model calls made.")
        return

    mcq_acc = sum(it["mcq"]["correct"] for it in items) / len(items) if items else 0.0
    summary = {"n_questions": len(items), "n_skipped_no_audio": n_skipped,
               "mcq_accuracy": round(mcq_acc, 4)}
    metadata = get_run_metadata(EXP_NAME, client.model_id, config)
    save_results(metadata, items, summary)
    print(f"\nMCQ accuracy: {mcq_acc:.1%}  ({len(items)} questions, {n_skipped} skipped)")
    print("Next: score the OEQ answers →  python -m experiments.oeq_mcq.judge --run <dir>")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, help="e.g. flamingo | openai:gpt-4o-audio-preview")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--preview", action="store_true", help="Show prompts, make no API calls.")
    ap.add_argument("--allow-unlabeled", action="store_true",
                    help="Run rows even if their level is blank.")
    args = ap.parse_args()
    run(args.model, limit=args.limit, preview=args.preview,
        require_level=not args.allow_unlabeled)


if __name__ == "__main__":
    main()

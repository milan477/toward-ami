"""Step 1-2: pull the MMAR music subset and build a manual-classification sheet.

Reads data/cleaned/mmar.csv (the music subset), draws a stratified sample of
~N questions, and writes a sheet you fill in by hand: assign each row a level
(HEAR / ANALYZE / FEEL / KNOW). A stable `qid` ties the sheet to every later
step, so re-sampling or re-cleaning never scrambles the labels you entered.

Usage:
    python -m experiments.oeq_mcq.sample            # 50 questions, seed 0
    python -m experiments.oeq_mcq.sample --n 60 --seed 1
"""

import argparse
import hashlib
from pathlib import Path

import pandas as pd

from .taxonomy import KEYS, describe

ROOT       = Path(__file__).parent.parent.parent
CLEANED    = ROOT / "data" / "cleaned" / "mmar.csv"
AUDIO_DIR  = ROOT / "data" / "audio" / "mmar"
OUT_DIR    = Path(__file__).parent / "data"
SHEET      = OUT_DIR / "classification.csv"
GUIDE      = OUT_DIR / "LEVELS.txt"

SHEET_COLUMNS = [
    "qid", "level", "question", "correct_answer", "distractors",
    "audio_url", "audio_available", "mmar_layer", "mmar_subcat",
]


def qid(audio_url: str, question: str) -> str:
    """Stable short id for a (clip, question) pair."""
    h = hashlib.sha1(f"{audio_url}||{question}".encode("utf-8")).hexdigest()
    return h[:12]


def _audio_available(audio_url: str) -> bool:
    name = str(audio_url).split("/")[-1]
    return (AUDIO_DIR / name).exists()


def build_sheet(n: int = 50, seed: int = 0, audio_only: bool = True) -> pd.DataFrame:
    df = pd.read_csv(CLEANED, dtype=str, keep_default_na=False)
    df = df.assign(
        qid=[qid(u, q) for u, q in zip(df["audio_url"], df["question"])],
        audio_available=df["audio_url"].map(_audio_available),
    )
    if audio_only:
        df = df[df["audio_available"]]

    # Stratify across MMAR's layers so the sample spans varied question kinds.
    strata = df.groupby("category_2", group_keys=False)
    per = max(1, n // max(1, df["category_2"].nunique()))
    picks = strata.apply(lambda g: g.sample(min(len(g), per), random_state=seed))
    if len(picks) < n:                       # top up to n from the remainder
        rest = df[~df["qid"].isin(picks["qid"])]
        picks = pd.concat([picks, rest.sample(min(len(rest), n - len(picks)),
                                              random_state=seed)])
    picks = picks.sample(min(n, len(picks)), random_state=seed).reset_index(drop=True)

    sheet = pd.DataFrame({
        "qid":             picks["qid"],
        "level":           "",                  # ← fill in by hand
        "question":        picks["question"],
        "correct_answer":  picks["correct_answer"],
        "distractors":     picks["distractors"],
        "audio_url":       picks["audio_url"],
        "audio_available": picks["audio_available"],
        "mmar_layer":      picks["category_2"],
        "mmar_subcat":     picks["category_3"],
    })
    return sheet[SHEET_COLUMNS]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--all-rows", action="store_true",
                    help="Include questions whose audio isn't downloaded.")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing sheet (default: refuse to clobber labels).")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if SHEET.exists() and not args.force:
        raise SystemExit(
            f"{SHEET} already exists — refusing to overwrite your labels. "
            f"Use --force to regenerate."
        )

    sheet = build_sheet(n=args.n, seed=args.seed, audio_only=not args.all_rows)
    sheet.to_csv(SHEET, index=False)
    GUIDE.write_text(
        "Fill the `level` column of classification.csv with one of: "
        f"{', '.join(KEYS)}\n\n{describe()}\n"
    )
    print(f"Wrote {SHEET}  ({len(sheet)} questions to classify)")
    print(f"Wrote {GUIDE}  (level definitions)")
    print(f"\nLayer spread:\n{sheet['mmar_layer'].value_counts().to_string()}")
    print(f"\nNext: open {SHEET.name} and fill the `level` column "
          f"({', '.join(KEYS)}).")


if __name__ == "__main__":
    main()

"""Filter normalized benchmarks down to their music parts.

Reads data/normalized/<name>.csv and writes data/cleaned/<name>.csv keeping
only rows whose modality is music or a mix that includes music (e.g.
"mix-music-speech", "sound_music"). The modality lives in a different column
per dataset, so each dataset declares which column to test.

Usage
-----
python download/clean.py mmar        # one dataset
python download/clean.py all         # every registered dataset
python download/clean.py --list      # show registered datasets
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from common import CLEAN_DIR, NORM_DIR

# Per-dataset: which normalized column holds the audio modality label.
MODALITY_COLUMN = {
    "mmar": "category_1",
    "mmau_pro": "category_1",
}


def _has_music(modality) -> bool:
    """True if the modality is music or a mix that includes music."""
    return "music" in str(modality).lower()


def clean_dataset(name: str) -> Path:
    if name == "all":
        for n in MODALITY_COLUMN:
            clean_dataset(n)
        return CLEAN_DIR
    if name not in MODALITY_COLUMN:
        raise ValueError(
            f"Dataset {name!r} not found. Available: {', '.join(sorted(MODALITY_COLUMN))}"
        )

    column = MODALITY_COLUMN[name]
    df = pd.read_csv(NORM_DIR / f"{name}.csv")
    music = df[df[column].map(_has_music)]

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    path = CLEAN_DIR / f"{name}.csv"
    music.to_csv(path, index=False)
    print(f"  cleaned    → {path}  ({len(music)} of {len(df)} rows kept)")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", help="Dataset name, or 'all'")
    parser.add_argument("--list", action="store_true", help="List registered datasets")
    args = parser.parse_args()

    if args.list or not args.dataset:
        print("Registered datasets:")
        for name in sorted(MODALITY_COLUMN):
            print(f"  {name}")
        sys.exit(0)

    clean_dataset(args.dataset)

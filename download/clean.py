"""Filter normalized benchmarks down to their music parts.

Reads data/benchmarks/<name>/<name>_normalized.csv and writes
data/benchmarks/<name>/<name>_normalized_selected.csv keeping
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

from common import BENCH_DIR, bench_dir, bench_path

# Per-dataset: which normalized column holds the audio modality label.
# None = the whole dataset is music; keep every row.
MODALITY_COLUMN = {
    "mmar": "category_1",
    "mmau_pro": "category_1",
    "muchomusic": None,
}


def _has_music(modality) -> bool:
    """True if the modality is music or a mix that includes music."""
    return "music" in str(modality).lower()


def clean_dataset(name: str) -> Path:
    if name == "all":
        for n in MODALITY_COLUMN:
            clean_dataset(n)
        return BENCH_DIR
    if name not in MODALITY_COLUMN:
        raise ValueError(
            f"Dataset {name!r} not found. Available: {', '.join(sorted(MODALITY_COLUMN))}"
        )

    df = pd.read_csv(bench_path(name, "normalized"))
    column = MODALITY_COLUMN[name]
    music = df if column is None else df[df[column].map(_has_music)]

    bench_dir(name)
    path = bench_path(name, "selected")
    music.to_csv(path, index=False)
    print(f"  selected   → {path}  ({len(music)} of {len(df)} rows kept)")
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

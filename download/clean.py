"""Filter normalized benchmarks down to their music parts.

Reads data/benchmarks/<name>/<name>_normalized.csv and writes
data/benchmarks/<name>/<name>_normalized_selected.csv keeping
only rows whose normalized ``focus`` list contains music.

Usage
-----
python download/clean.py mmar        # one dataset
python download/clean.py all         # every registered dataset
python download/clean.py --list      # show registered datasets
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import BENCH_DIR, bench_dir, bench_path

DATASETS = (
    "aha", "hummusqa", "mmau", "mmar", "mmau_pro", "muchomusic",
    "parsa_bench", "pitchbench",
)


def _has_music(modality) -> bool:
    """True if the modality is music or a mix that includes music."""
    return "music" in str(modality).lower()


def clean_dataset(name: str) -> Path:
    if name == "all":
        for n in DATASETS:
            if not bench_path(n, "normalized").exists():
                print(f"[{n}] SKIPPED — missing normalized CSV")
                continue
            clean_dataset(n)
        return BENCH_DIR
    if name not in DATASETS:
        raise ValueError(
            f"Dataset {name!r} not found. Available: {', '.join(sorted(DATASETS))}"
        )

    with bench_path(name, "normalized").open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = list(reader)
    music = [row for row in rows if _has_music(row.get("focus", ""))]

    bench_dir(name)
    path = bench_path(name, "selected")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(music)
    print(f"  selected   → {path}  ({len(music)} of {len(rows)} rows kept)")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", help="Dataset name, or 'all'")
    parser.add_argument("--list", action="store_true", help="List registered datasets")
    args = parser.parse_args()

    if args.list or not args.dataset:
        print("Registered datasets:")
        for name in sorted(DATASETS):
            print(f"  {name}")
        sys.exit(0)

    clean_dataset(args.dataset)

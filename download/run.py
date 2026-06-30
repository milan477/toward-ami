"""Download + normalize benchmark datasets.

Each dataset has a specialized download function that writes two CSVs:
  data/raw/<name>.csv          source dataset, exactly as is
  data/normalized/<name>.csv   canonical schema (see download/common.py)

Usage
-----
python download/run.py mmar        # one dataset
python download/run.py all         # every registered dataset
python download/run.py --list      # show registered datasets
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mmar import download_mmar
from mmau_pro import download_mmau_pro
from muchomusic import download_muchomusic

# Register one download function per dataset here.
DATASETS = {
    "mmar": download_mmar,
    "mmau_pro": download_mmau_pro,
    "muchomusic": download_muchomusic,
}


def download_dataset(name: str) -> None:
    if name == "all":
        for fn in DATASETS.values():
            fn()
        return
    if name not in DATASETS:
        raise ValueError(
            f"Dataset {name!r} not found. Available: {', '.join(sorted(DATASETS))}"
        )
    DATASETS[name]()


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

    download_dataset(args.dataset)

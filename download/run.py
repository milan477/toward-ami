"""Download + normalize + select + fetch audio for benchmark datasets.

For each dataset this writes:

  data/benchmarks/<name>/<name>_raw.csv
  data/benchmarks/<name>/<name>_normalized.csv
  data/benchmarks/<name>/<name>_normalized_selected.csv

then downloads the audio clips referenced by ``normalized_selected`` into
``data/audio/<name>/``.

Usage
-----
python download/run.py mmar        # one dataset
python download/run.py all         # every registered dataset
python download/run.py --list      # show registered datasets
"""

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from audio import DATASETS as AUDIO_DATASETS, download_audio
from clean import MODALITY_COLUMN, clean_dataset

# Register one metadata download function per dataset here.
DATASETS = {
    "aha": ("benchmark_aha", "download_aha"),
    "hummusqa": ("benchmark_hummusqa", "download_hummusqa"),
    "mmau": ("benchmark_mmau", "download_mmau"),
    "mmar": ("benchmark_mmar", "download_mmar"),
    "mmau_pro": ("benchmark_mmau_pro", "download_mmau_pro"),
    "muchomusic": ("benchmark_muchomusic", "download_muchomusic"),
    "parsa_bench": ("benchmark_parsa_bench", "download_parsa_bench"),
    "pitchbench": ("benchmark_pitchbench", "download_pitchbench"),
}


def _load_download(name: str):
    module_name, fn_name = DATASETS[name]
    return getattr(importlib.import_module(module_name), fn_name)


def download_dataset(name: str) -> None:
    """raw → normalized → normalized_selected → audio (from selected)."""
    if name == "all":
        for dataset in DATASETS:
            download_dataset(dataset)
        return
    if name not in DATASETS:
        raise ValueError(
            f"Dataset {name!r} not found. Available: {', '.join(sorted(DATASETS))}"
        )

    _load_download(name)()

    if name in MODALITY_COLUMN:
        clean_dataset(name)
    else:
        print(f"[{name}] no music-selection rule registered; skipping normalized_selected")

    if name in AUDIO_DATASETS:
        download_audio(name)
    else:
        print(f"[{name}] no audio downloader registered; skipping audio")


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

"""Rebuild normalized benchmark CSVs from the local raw CSVs.

This stage performs only deterministic, benchmark-specific mappings. It never
downloads data and never calls an LLM. The enhancement stage lives under
``src.analysis``.

Usage
-----
python download/normalize.py mmar
python download/normalize.py all
python download/normalize.py --list
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from download.common import bench_path


NORMALIZERS = {
    "aha": ("download.benchmark_aha", "normalize_aha"),
    "hummusqa": ("download.benchmark_hummusqa", "normalize_hummusqa"),
    "mmau": ("download.benchmark_mmau", "normalize_mmau"),
    "mmar": ("download.benchmark_mmar", "normalize_mmar"),
    "mmau_pro": ("download.benchmark_mmau_pro", "normalize_mmau_pro"),
    "muchomusic": ("download.benchmark_muchomusic", "normalize_muchomusic"),
    "parsa_bench": ("download.benchmark_parsa_bench", "normalize_parsa_bench"),
    "pitchbench": ("download.benchmark_pitchbench", "normalize_pitchbench"),
}


def normalize_dataset(name: str) -> None:
    if name == "all":
        for dataset in NORMALIZERS:
            raw = bench_path(dataset, "raw")
            if not raw.exists():
                print(f"[{dataset}] SKIPPED — missing local raw CSV: {raw}")
                continue
            normalize_dataset(dataset)
        return
    if name not in NORMALIZERS:
        raise ValueError(
            f"Dataset {name!r} not found. Available: {', '.join(sorted(NORMALIZERS))}"
        )
    module_name, function_name = NORMALIZERS[name]
    getattr(importlib.import_module(module_name), function_name)()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", help="Dataset name, or 'all'")
    parser.add_argument("--list", action="store_true", help="List registered datasets")
    args = parser.parse_args()
    if args.list or not args.dataset:
        print("Registered datasets:")
        for dataset in sorted(NORMALIZERS):
            print(f"  {dataset}")
    else:
        normalize_dataset(args.dataset)

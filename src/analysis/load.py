"""Data access for benchmark CSVs."""

from pathlib import Path

import pandas as pd

from src.config import BENCHMARK_ITEM_COLS

BENCH_DIR = Path(__file__).resolve().parents[2] / "data" / "benchmarks"


def _normalized_path(name: str) -> Path:
    return BENCH_DIR / name / f"{name}_normalized.csv"


def _selected_path(name: str) -> Path:
    return BENCH_DIR / name / f"{name}_normalized_selected.csv"


def benchmark_path(name: str) -> Path:
    """Prefer normalized_selected; fall back to normalized."""
    selected = _selected_path(name)
    return selected if selected.exists() else _normalized_path(name)


def available_benchmarks() -> list[str]:
    """Names of every benchmark with selected or normalized CSV data."""
    if not BENCH_DIR.exists():
        return []
    return sorted(p.name for p in BENCH_DIR.iterdir()
                  if p.is_dir() and benchmark_path(p.name).exists())


def _row_to_item(row: dict) -> dict:
    """Return the normalized benchmark row with the expected canonical fields."""
    return {col: row.get(col, "") for col in BENCHMARK_ITEM_COLS}


def load_items(name: str | None = None) -> list[dict]:
    """Question-level items for one benchmark, or all benchmarks if name is None."""
    names = [name.lower()] if name else available_benchmarks()
    items: list[dict] = []
    for n in names:
        path = benchmark_path(n)
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        items.extend(_row_to_item(r) for r in df.to_dict("records"))
    return items

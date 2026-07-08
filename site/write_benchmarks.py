"""Write docs/data/benchmarks.json from the newest benchmark overview CSV.

Reads data/benchmarks/overviews/benchmark_overview_<date>.csv (confirmed rows
with a year) and writes docs/data/benchmarks.json.

    python site/write_benchmarks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderers" / "site"))

from build_site import latest_benchmark_overview, load_benchmarks  # noqa: E402

OUT = ROOT / "docs" / "data" / "benchmarks.json"


def main() -> int:
    src = latest_benchmark_overview()
    if not src:
        print(
            "No benchmark_overview_*.csv found in data/benchmarks/overviews/",
            file=sys.stderr,
        )
        return 1
    rows = load_benchmarks()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} benchmark(s) → {OUT.relative_to(ROOT)}")
    print(f"source: {src.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

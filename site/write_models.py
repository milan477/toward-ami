"""Write docs/data/models.json from the newest model overview CSV.

Reads data/models/overviews/model_overview_<date>.csv and writes
docs/data/models.json.

    python site/write_models.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderers" / "site"))

from build_site import latest_model_overview, load_models  # noqa: E402

OUT = ROOT / "docs" / "data" / "models.json"


def main() -> int:
    src = latest_model_overview()
    if not src:
        print(
            "No model_overview_*.csv found in data/models/overviews/",
            file=sys.stderr,
        )
        return 1
    rows = load_models()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} model(s) → {OUT.relative_to(ROOT)}")
    print(f"source: {src.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

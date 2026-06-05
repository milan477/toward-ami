"""Load and validate the benchmark catalog."""

from pathlib import Path
import yaml

CATALOG_DIR = Path(__file__).parent.parent / "catalog" / "benchmarks"


def load_all() -> list[dict]:
    entries = []
    for path in sorted(CATALOG_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        with path.open() as f:
            entry = yaml.safe_load(f)
        entry["_source"] = path.name
        entries.append(entry)
    return entries


def load_by_name(name: str) -> dict:
    matches = [e for e in load_all() if e["name"] == name]
    if not matches:
        raise KeyError(f"No benchmark named {name!r}")
    return matches[0]

"""Refresh benchmark BibTeX entries from paper/mybib.bib by paper title.

Matches each benchmark row in the newest
``data/benchmarks/overviews/benchmark_overview_<date>.csv`` (rows with a year)
against the bibliography by normalized title, then writes the cleaned entry into
the CSV and docs/data/benchmarks.json.

    python site/update_citation.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MYBIB = ROOT / "paper" / "mybib.bib"
BENCH_OVERVIEWS = ROOT / "data" / "benchmarks" / "overviews"
DATA_DIR = ROOT / "docs" / "data"
BENCHMARKS_JSON = DATA_DIR / "benchmarks.json"

DROP_FIELDS = frozenset({
    "file", "abstract", "urldate", "keywords", "langid", "copyright",
})


def latest_benchmark_overview() -> Path | None:
    if not BENCH_OVERVIEWS.exists():
        return None
    files = sorted(BENCH_OVERVIEWS.glob("benchmark_overview_*.csv"))
    return files[-1] if files else None


def display_title(text: str) -> str:
    return re.sub(r"\{+\{*|\}+\}*", "", text).strip()


def norm_title(text: str) -> str:
    text = re.sub(r"\{+\{*|\}+\}*", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def extract_braced_field(text: str, field: str) -> str:
    m = re.search(rf"^\s*{re.escape(field)}\s*=\s*\{{", text, re.M | re.I)
    if not m:
        return ""
    i = m.end()
    depth = 1
    start = i
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start : i - 1]


def clean_bibtex(raw: str) -> str:
    kept: list[str] = []
    for line in raw.splitlines():
        m = re.match(r"\s*(\w+)\s*=", line)
        if m and m.group(1).lower() in DROP_FIELDS:
            continue
        kept.append(line)
    text = "\n".join(kept).strip()
    if text and not text.endswith("}"):
        text += "\n}"
    return text + "\n"


def load_bib_entries(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    chunks = re.split(r"\n(?=@)", raw.strip())
    entries: list[dict] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"@(\w+)\{([^,]+),", chunk)
        if not m:
            continue
        title = extract_braced_field(chunk, "title")
        entries.append({
            "type": m.group(1),
            "key": m.group(2).strip(),
            "title": title,
            "raw": clean_bibtex(chunk),
        })
    return entries


def match_entry(title: str, entries: list[dict]) -> dict | None:
    nt = norm_title(title)
    if not nt:
        return None

    exact = [e for e in entries if norm_title(e["title"]) == nt]
    if len(exact) == 1:
        return exact[0]

    subs = [
        e for e in entries
        if nt in norm_title(e["title"]) or norm_title(e["title"]) in nt
    ]
    if len(subs) == 1:
        return subs[0]

    nt_tokens = set(nt.split())
    best: dict | None = None
    best_score = 0.0
    for e in entries:
        et = set(norm_title(e["title"]).split())
        if not et:
            continue
        score = len(nt_tokens & et) / len(nt_tokens | et)
        if score > best_score:
            best_score = score
            best = e
    return best if best_score >= 0.6 else None


def read_benchmark_rows(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    return header, rows


def write_benchmark_rows(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def update_site_benchmarks(updates: dict[str, str]) -> int:
    if not BENCHMARKS_JSON.exists():
        return 0
    benchmarks = json.loads(BENCHMARKS_JSON.read_text(encoding="utf-8"))
    changed = 0
    for bench in benchmarks:
        name = bench.get("name", "")
        if name not in updates:
            continue
        new_bib = updates[name]
        if bench.get("bibtex", "").strip() != new_bib.strip():
            bench["bibtex"] = new_bib
            changed += 1
    if changed:
        BENCHMARKS_JSON.write_text(
            json.dumps(benchmarks, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
    return changed


def main() -> int:
    if not MYBIB.exists():
        print("Bibliography not found.", file=sys.stderr)
        return 1

    bench_csv = latest_benchmark_overview()
    if not bench_csv:
        print("Benchmark list not found.", file=sys.stderr)
        return 1

    entries = load_bib_entries(MYBIB)
    header, rows = read_benchmark_rows(bench_csv)

    updates: dict[str, str] = {}
    matched = 0
    skipped = 0
    missing: list[str] = []

    for row in rows:
        name = (row.get("Known name") or "").strip()
        year = (row.get("Year") or "").strip()
        paper_title = (row.get("Paper title") or "").strip()
        if not year or not paper_title:
            continue

        entry = match_entry(paper_title, entries)
        if not entry:
            missing.append(f"{name}: {paper_title}")
            continue

        bibtex = entry["raw"].strip()
        old = (row.get("Citation") or "").strip()
        if old != bibtex:
            row["Citation"] = bibtex
            updates[name] = bibtex
            matched += 1
            print(f"updated {name} ← {display_title(entry['title'])}")
        else:
            skipped += 1
            print(f"unchanged {name} ← {display_title(entry['title'])}")

    if updates:
        write_benchmark_rows(bench_csv, header, rows)
        json_changed = update_site_benchmarks(updates)
        print(f"\n{matched} citation(s) updated, {skipped} already current.")
        if json_changed:
            print(f"{json_changed} site benchmark(s) refreshed.")
    else:
        print(f"No changes needed ({skipped} already current).")

    if missing:
        print(f"\n{len(missing)} benchmark(s) without a bibliography match:")
        for line in missing:
            print(f"  • {line}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Timeline: benchmark citation frequency and SOTA score evolution over time.
Year and SOTA score are not in the normalized CSVs (the curated catalog was
removed), so these plots are empty until that metadata is sourced elsewhere.
"""

from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt
from catalog import load_all

_DEFAULT_OUT = Path(__file__).parent.parent / "paper" / "figures"


def publication_timeline(benchmarks: list[dict], out_dir: Path = _DEFAULT_OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    year_counts: dict[int, int] = defaultdict(int)
    for b in benchmarks:
        if b.get("year"):
            year_counts[b["year"]] += 1

    if not year_counts:
        print("No year data available (publication year is not in the normalized CSVs).")
        return

    years = sorted(year_counts)
    counts = [year_counts[y] for y in years]

    fig, ax = plt.subplots(figsize=(7, 3))
    ax.bar(years, counts)
    ax.set_xlabel("Year")
    ax.set_ylabel("Benchmarks published")
    ax.set_title("ALM music benchmark publications over time")
    ax.set_xticks(years)
    plt.tight_layout()
    fig.savefig(out_dir / "publication_timeline.pdf")
    plt.close(fig)
    print("Saved publication_timeline.pdf")


def sota_score_evolution(benchmarks: list[dict], out_dir: Path = _DEFAULT_OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = [
        (b["year"], b["sota_score"], b["name"])
        for b in benchmarks
        if b.get("year") and b.get("sota_score") is not None
    ]
    if not data:
        print("No SOTA score data available (not in the normalized CSVs).")
        return

    data.sort()
    years, scores, names = zip(*data)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.scatter(years, scores, zorder=3)
    for y, s, n in zip(years, scores, names):
        ax.annotate(n, (y, s), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.set_xlabel("Year benchmark published")
    ax.set_ylabel("SOTA score reported")
    ax.set_title("SOTA performance vs benchmark publication year")
    plt.tight_layout()
    fig.savefig(out_dir / "sota_evolution.pdf")
    plt.close(fig)
    print("Saved sota_evolution.pdf")


if __name__ == "__main__":
    benchmarks = load_all()
    publication_timeline(benchmarks)
    sota_score_evolution(benchmarks)

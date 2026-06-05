"""
Benchmark taxonomy: skill distribution, question format, and audio coverage.
Outputs figures to paper/figures/.
"""

from collections import Counter
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from catalog import load_all

FIGURES = Path(__file__).parent.parent / "paper" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


def skill_distribution(benchmarks: list[dict]) -> None:
    counts = Counter()
    for b in benchmarks:
        for skill in b.get("primary_skill") or []:
            counts[skill] += 1

    skills, freqs = zip(*counts.most_common()) if counts else ([], [])
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(skills, freqs)
    ax.set_xlabel("Number of benchmarks")
    ax.set_title("Skill coverage across benchmarks")
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    plt.tight_layout()
    fig.savefig(FIGURES / "skill_distribution.pdf")
    plt.close(fig)
    print(f"Saved skill_distribution.pdf ({len(benchmarks)} benchmarks)")


def format_breakdown(benchmarks: list[dict]) -> None:
    mcq = sum(1 for b in benchmarks if "MCQ" in (b.get("question_format") or []))
    open_ = sum(1 for b in benchmarks if "open-ended" in (b.get("question_format") or []))
    both = sum(
        1 for b in benchmarks
        if "MCQ" in (b.get("question_format") or [])
        and "open-ended" in (b.get("question_format") or [])
    )
    labels = ["MCQ only", "Open-ended only", "Both"]
    sizes = [mcq - both, open_ - both, both]
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie([max(s, 0) for s in sizes], labels=labels, autopct="%1.0f%%", startangle=90)
    ax.set_title("Question format distribution")
    plt.tight_layout()
    fig.savefig(FIGURES / "question_format.pdf")
    plt.close(fig)
    print("Saved question_format.pdf")


if __name__ == "__main__":
    benchmarks = load_all()
    print(f"Loaded {len(benchmarks)} benchmark entries")
    skill_distribution(benchmarks)
    format_breakdown(benchmarks)

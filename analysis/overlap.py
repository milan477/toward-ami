"""
Benchmark overlap: how many skills are shared between benchmarks.
Outputs an overlap heatmap to paper/figures/.
"""

from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from catalog import load_all

FIGURES = Path(__file__).parent.parent / "paper" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


def skill_overlap_matrix(benchmarks: list[dict]) -> None:
    names = [b["name"] for b in benchmarks]
    skills = [set(b.get("primary_skill") or []) for b in benchmarks]

    n = len(benchmarks)
    mat = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            union = skills[i] | skills[j]
            inter = skills[i] & skills[j]
            mat[i, j] = len(inter) / len(union) if union else 0.0

    fig, ax = plt.subplots(figsize=(max(6, n), max(5, n - 1)))
    im = ax.imshow(mat, vmin=0, vmax=1, cmap="YlOrRd")
    plt.colorbar(im, ax=ax, label="Jaccard similarity (skills)")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_title("Skill overlap between benchmarks (Jaccard)")
    plt.tight_layout()
    fig.savefig(FIGURES / "skill_overlap.pdf")
    plt.close(fig)
    print(f"Saved skill_overlap.pdf ({n}×{n})")


if __name__ == "__main__":
    benchmarks = load_all()
    skill_overlap_matrix(benchmarks)

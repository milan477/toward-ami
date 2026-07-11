"""STEP 5 — hallucination analysis + the "apparent ≠ actual acquisition" proof.

Joins three per-question sources on the audio-stem qid (no model calls):
  - annotated benchmark labels
  - OEQ + PIAC judge summary
  - MCQ summary (apparent acquisition)

Produces:
  - hallucination rate overall, per PIAC category, per skill, and by failing PIAC level
    (the intercategorical diagnostic — fluent higher-level answers on weak perceptual ground).
  - MCQ accuracy (apparent) vs OEQ correctness & (1 − hallucination) (actual), per skill and
    per PIAC category → skills that look acquired in MCQ but aren't in OEQ.
  - analysis.csv (merged per question), analysis_report.txt, and two figures under
    paper/figures/.

    python -m src.evaluation.piac_analyze
    python -m src.evaluation.piac_analyze --oeq <summary.csv> --mcq <summary.csv>
"""

from __future__ import annotations

import argparse
import glob
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.config import (
    DEFAULT_ANNOTATED_DATA,
    DEFAULT_DATASET,
    DEFAULT_MODALITY,
    DEFAULT_RUNNER_MODEL,
    FIGURES_DIR,
)
from src.querying.common import model_slug, result_dir, resolve_path

FIG_DIR = FIGURES_DIR
PIAC_ORDER = ["perceptual", "inferential", "affective", "contextual"]


def _latest(pattern: str) -> Path | None:
    m = sorted(glob.glob(pattern))
    return Path(m[-1]) if m else None


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def _stem(audio_url: str) -> str:
    return str(audio_url).split("/")[-1].rsplit(".", 1)[0]


def load_merged(annotated_path: Path, oeq_path: Path, mcq_path: Path) -> pd.DataFrame:
    proc = pd.read_csv(annotated_path, dtype=str, keep_default_na=False)
    proc["qid"] = proc["audio_url"].map(_stem)
    proc = proc[["qid", "category", "skills"]].rename(columns={"category": "piac"})

    oeq = pd.read_csv(oeq_path, dtype=str, keep_default_na=False)
    oeq = oeq.rename(columns={"category": "piac_oeq"})
    oeq["oeq_norm"] = pd.to_numeric(oeq["judge_score_norm"], errors="coerce")
    oeq["oeq_correct"] = (oeq["oeq_norm"] == 1.0).astype("float")
    oeq["hallucinated"] = oeq["hallucinated"].map(_truthy)
    oeq = oeq[["qid", "question", "reference_answer", "response", "oeq_norm", "oeq_correct",
               "hallucinated", "hallucination_level", "judge_rationale"]]

    mcq = pd.read_csv(mcq_path, dtype=str, keep_default_na=False)
    mcq["mcq_correct"] = mcq["correct"].map(_truthy).astype("float")
    mcq = mcq[["qid", "mcq_correct"]]

    m = proc.merge(oeq, on="qid", how="inner").merge(mcq, on="qid", how="left")
    return m


def _rate(series) -> float:
    s = series.dropna()
    return float(s.mean()) if len(s) else float("nan")


def _breakdown(df: pd.DataFrame, group: str) -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(group):
        rows.append({
            group: key, "n": len(g),
            "mcq_acc": _rate(g["mcq_correct"]),
            "oeq_acc": _rate(g["oeq_correct"]),
            "oeq_mean": _rate(g["oeq_norm"]),
            "halluc_rate": _rate(g["hallucinated"].astype(float)),
        })
    out = pd.DataFrame(rows)
    out["apparent_minus_actual"] = out["mcq_acc"] - out["oeq_acc"]
    return out


def _explode_skills(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        for s in [s.strip() for s in str(r["skills"]).split(",") if s.strip()] or ["(none)"]:
            rows.append({**r.to_dict(), "skill": s})
    return pd.DataFrame(rows)


def _fmt(v) -> str:
    return "—" if v != v else f"{v:.0%}"


def make_figures(by_piac: pd.DataFrame, by_skill: pd.DataFrame, slug: str = "") -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    pre = f"piac_{slug}_" if slug else "piac_"
    saved = []

    # 1. hallucination rate by PIAC category
    p = by_piac.set_index("piac").reindex([c for c in PIAC_ORDER if c in set(by_piac["piac"])])
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(p.index, p["halluc_rate"], color="#e5534b")
    ax.set_ylabel("Hallucination rate")
    ax.set_title("OEQ hallucination rate by PIAC category")
    ax.set_ylim(0, 1)
    for i, v in enumerate(p["halluc_rate"]):
        ax.text(i, v + 0.02, f"{v:.0%}", ha="center", fontsize=9)
    plt.tight_layout()
    f1 = FIG_DIR / f"{pre}hallucination_by_category.pdf"
    fig.savefig(f1); fig.savefig(f1.with_suffix(".png"), dpi=120); plt.close(fig)
    saved.append(f1)

    # 2. MCQ (apparent) vs OEQ (actual) accuracy by skill
    s = by_skill[by_skill["n"] >= 3].sort_values("apparent_minus_actual", ascending=False)
    if len(s):
        fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(s) + 1)))
        y = range(len(s))
        ax.barh([i + 0.2 for i in y], s["mcq_acc"], height=0.4, label="MCQ (apparent)", color="#6ea8fe")
        ax.barh([i - 0.2 for i in y], s["oeq_acc"], height=0.4, label="OEQ (actual)", color="#54c98a")
        ax.set_yticks(list(y))
        ax.set_yticklabels([f"{r.skill} (n={r.n})" for r in s.itertuples()])
        ax.set_xlabel("Accuracy")
        ax.set_title("Apparent (MCQ) vs actual (OEQ) accuracy by skill")
        ax.set_xlim(0, 1); ax.legend(loc="lower right", fontsize=8)
        ax.invert_yaxis()
        plt.tight_layout()
        f2 = FIG_DIR / f"{pre}mcq_vs_oeq_by_skill.pdf"
        fig.savefig(f2); fig.savefig(f2.with_suffix(".png"), dpi=120); plt.close(fig)
        saved.append(f2)
    return saved


def write_report(df, by_piac, by_skill, halluc_levels, oeq_path, mcq_path, out_dir: Path) -> Path:
    n = len(df)
    lines = [
        "PIAC analysis — hallucination & apparent-vs-actual acquisition",
        "=" * 64,
        f"OEQ source: {oeq_path.name}",
        f"MCQ source: {mcq_path.name}",
        f"Questions merged: {n}",
        "",
        "Overall",
        "-" * 64,
        f"  MCQ accuracy (apparent):   {_rate(df['mcq_correct']):.1%}",
        f"  OEQ accuracy (actual):     {_rate(df['oeq_correct']):.1%}",
        f"  OEQ mean score (0-1):      {_rate(df['oeq_norm']):.3f}",
        f"  Hallucination rate (OEQ):  {_rate(df['hallucinated'].astype(float)):.1%}",
        f"  Hallucination by failing PIAC level: {halluc_levels}",
        "",
        "By PIAC category   (n | MCQ apparent | OEQ actual | OEQ mean | halluc | apparent−actual)",
        "-" * 64,
    ]
    pv = by_piac.set_index("piac")
    for c in [*PIAC_ORDER, *[x for x in pv.index if x not in PIAC_ORDER]]:
        if c in pv.index:
            r = pv.loc[c]
            lines.append(f"  {c:<12} {int(r['n']):>3} | {_fmt(r['mcq_acc']):>6} | "
                         f"{_fmt(r['oeq_acc']):>6} | {r['oeq_mean']:.2f} | "
                         f"{_fmt(r['halluc_rate']):>5} | {_fmt(r['apparent_minus_actual']):>6}")
    lines += ["", "By skill (n≥3), sorted by apparent−actual gap (the proof)",
              "-" * 64,
              "  skill            n | MCQ | OEQ | halluc | gap"]
    for r in by_skill[by_skill["n"] >= 3].sort_values(
            "apparent_minus_actual", ascending=False).itertuples():
        lines.append(f"  {r.skill:<15} {r.n:>3} | {_fmt(r.mcq_acc):>4} | {_fmt(r.oeq_acc):>4} | "
                     f"{_fmt(r.halluc_rate):>5} | {_fmt(r.apparent_minus_actual):>5}")
    lines += ["",
              "Reading: a large positive gap = the skill looks acquired in MCQ but collapses in",
              "open-ended answering (often via hallucination) — apparent, not actual, acquisition."]
    out = out_dir / "analysis_report.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def run(annotated_path: Path, oeq_path: Path | None, mcq_path: Path | None,
        benchmark: str, model_spec: str, modality: str) -> None:
    annotated_path = resolve_path(annotated_path)
    oeq_glob = str(result_dir(benchmark, model_spec, f"{modality}-oeq-piac") / "*_summary.csv")
    mcq_glob = str(result_dir(benchmark, model_spec, modality) / "*_summary.csv")
    oeq_path = oeq_path or _latest(oeq_glob)
    mcq_path = mcq_path or _latest(mcq_glob)
    if not oeq_path or not mcq_path:
        raise SystemExit(f"Need both an OEQ-PIAC summary ({oeq_glob}) and an MCQ summary "
                         f"({mcq_glob}). Run `python -m src.run experiments mcq-oeq` first.")
    df = load_merged(annotated_path, oeq_path, mcq_path)
    out_dir = oeq_path.parent            # write next to the OEQ summary being analyzed
    slug = model_slug(model_spec)

    halluc_levels = (df[df["hallucinated"]]["hallucination_level"]
                     .value_counts().to_dict())
    by_piac = _breakdown(df, "piac")
    by_skill = _breakdown(_explode_skills(df), "skill")

    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "analysis.csv", index=False)
    by_piac.to_csv(out_dir / "analysis_by_piac.csv", index=False)
    by_skill.to_csv(out_dir / "analysis_by_skill.csv", index=False)
    report = write_report(df, by_piac, by_skill, halluc_levels, oeq_path, mcq_path, out_dir)
    figs = make_figures(by_piac, by_skill, slug)

    print(report.read_text())
    print(f"Wrote {out_dir/'analysis.csv'} + by_piac/by_skill CSVs")
    print("Figures:", ", ".join(str(f) for f in figs))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--annotated", default=str(DEFAULT_ANNOTATED_DATA))
    ap.add_argument("--benchmark", default=DEFAULT_DATASET)
    ap.add_argument("--model", default=DEFAULT_RUNNER_MODEL)
    ap.add_argument("--modality", default=DEFAULT_MODALITY)
    ap.add_argument("--oeq", default=None, help="OEQ-PIAC summary CSV (default: latest)")
    ap.add_argument("--mcq", default=None, help="MCQ summary CSV (default: latest)")
    args = ap.parse_args()
    run(
        Path(args.annotated),
        Path(args.oeq) if args.oeq else None,
        Path(args.mcq) if args.mcq else None,
        args.benchmark,
        args.model,
        args.modality,
    )


if __name__ == "__main__":
    main()

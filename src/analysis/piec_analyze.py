"""Analyze binary PIEC judgments and the apparent-vs-actual acquisition gap.

Joins three per-question sources on the audio-stem qid (no model calls):
  - annotated benchmark labels
  - OEQ + PIEC judge summary
  - MCQ summary (apparent acquisition)

Produces:
  - binary OEQ accuracy and low/mid/high judge-confidence counts by PIEC category.
  - MCQ accuracy (apparent) vs OEQ accuracy (actual), per skill and PIEC category.
  - analysis.csv (merged per question), analysis_report.txt, and two figures under
    paper/figures/.

    python -m src.run analysis piec
    python -m src.run analysis piec --oeq <summary.csv> --mcq <summary.csv>
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.config import (
    DEFAULT_ANNOTATED_DATA,
    DEFAULT_DATASET,
    DEFAULT_MODALITY,
    DEFAULT_RUNNER_MODEL,
    FIGURES_DIR,
    RESULTS_DIR,
)
from src.querying.common import latest_result_dir, model_slug, resolve_path

FIG_DIR = FIGURES_DIR
PIEC_ORDER = ["perceptual", "inferential", "experiential", "contextual"]


def _latest(pattern: str) -> Path | None:
    m = sorted(glob.glob(pattern))
    return Path(m[-1]) if m else None


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def _stem(audio_url: str) -> str:
    return str(audio_url).split("/")[-1].rsplit(".", 1)[0]


def load_merged(annotated_path: Path, oeq_path: Path, mcq_path: Path) -> pd.DataFrame:
    proc = pd.read_csv(annotated_path, dtype=str, keep_default_na=False)
    if "qid" not in proc:
        source = proc["url"] if "url" in proc else proc["audio_url"]
        proc["qid"] = source.map(_stem)
    piac_col = "piec" if "piec" in proc else ("piac" if "piac" in proc else "category")
    skills_col = (
        "action_content" if "action_content" in proc
        else "content_skill" if "content_skill" in proc
        else "content" if "content" in proc
        else "skills"
    )
    proc = proc[["qid", piac_col, skills_col]].rename(
        columns={piac_col: "piec", skills_col: "skills"}
    )

    oeq = pd.read_csv(oeq_path, dtype=str, keep_default_na=False)
    oeq["oeq_norm"] = pd.to_numeric(oeq["judge_score_norm"], errors="coerce")
    oeq["oeq_correct"] = (oeq["oeq_norm"] == 1.0).astype("float")
    oeq = oeq[["qid", "question", "reference_answer", "response", "oeq_norm", "oeq_correct",
               "judge_confidence", "judge_rationale"]]

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
            "confidence_low": int((g["judge_confidence"] == "low").sum()),
            "confidence_mid": int((g["judge_confidence"] == "mid").sum()),
            "confidence_high": int((g["judge_confidence"] == "high").sum()),
        })
    out = pd.DataFrame(rows)
    out["apparent_minus_actual"] = out["mcq_acc"] - out["oeq_acc"]
    return out


def _explode_skills(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        raw = str(r["skills"] or "").strip()
        try:
            parsed = json.loads(raw) if raw.startswith("[") else None
        except json.JSONDecodeError:
            parsed = None
        values = parsed if isinstance(parsed, list) else raw.split(",")
        for s in [str(s).strip() for s in values if str(s).strip()] or ["(none)"]:
            rows.append({**r.to_dict(), "skill": s})
    return pd.DataFrame(rows)


def _fmt(v) -> str:
    return "—" if v != v else f"{v:.0%}"


def make_figures(by_piec: pd.DataFrame, by_skill: pd.DataFrame, slug: str = "") -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    pre = f"piec_{slug}_" if slug else "piec_"
    saved = []

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


def write_report(df, by_piec, by_skill, oeq_path, mcq_path, out_dir: Path) -> Path:
    n = len(df)
    lines = [
        "PIEC analysis — binary OEQ evaluation & apparent-vs-actual acquisition",
        "=" * 64,
        f"OEQ source: {oeq_path.name}",
        f"MCQ source: {mcq_path.name}",
        f"Questions merged: {n}",
        "",
        "Overall",
        "-" * 64,
        f"  MCQ accuracy (apparent):   {_rate(df['mcq_correct']):.1%}",
        f"  OEQ accuracy (actual):     {_rate(df['oeq_correct']):.1%}",
        f"  OEQ binary mean (0-1):     {_rate(df['oeq_norm']):.3f}",
        f"  Judge confidence:          {df['judge_confidence'].value_counts().to_dict()}",
        "",
        "By PIEC category   (n | MCQ apparent | OEQ actual | low/mid/high | gap)",
        "-" * 64,
    ]
    pv = by_piec.set_index("piec")
    for c in [*PIEC_ORDER, *[x for x in pv.index if x not in PIEC_ORDER]]:
        if c in pv.index:
            r = pv.loc[c]
            lines.append(f"  {c:<12} {int(r['n']):>3} | {_fmt(r['mcq_acc']):>6} | "
                         f"{_fmt(r['oeq_acc']):>6} | {int(r['confidence_low'])}/"
                         f"{int(r['confidence_mid'])}/{int(r['confidence_high'])} | "
                         f"{_fmt(r['apparent_minus_actual']):>6}")
    lines += ["", "By skill (n≥3), sorted by apparent−actual gap (the proof)",
              "-" * 64,
              "  skill            n | MCQ | OEQ | gap"]
    for r in by_skill[by_skill["n"] >= 3].sort_values(
            "apparent_minus_actual", ascending=False).itertuples():
        lines.append(f"  {r.skill:<15} {r.n:>3} | {_fmt(r.mcq_acc):>4} | {_fmt(r.oeq_acc):>4} | "
                     f"{_fmt(r.apparent_minus_actual):>5}")
    lines += ["",
              "Reading: a large positive gap = the skill looks acquired in MCQ but collapses in",
              "open-ended answering — apparent, not actual, acquisition."]
    out = out_dir / "analysis_report.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def run(annotated_path: Path, oeq_path: Path | None, mcq_path: Path | None,
        benchmark: str, model_spec: str, modality: str) -> None:
    annotated_path = resolve_path(annotated_path)
    run_dir = latest_result_dir("exp_7_mcq_oeq", benchmark, model_spec)
    new_oeq = run_dir / "oeq" / "summary.csv" if run_dir else None
    new_mcq = run_dir / "mcq" / "summary.csv" if run_dir else None

    # Read legacy variant-based runs when no dated run exists yet.
    legacy_root = RESULTS_DIR / "mcq-oeq" / benchmark / model_slug(model_spec)
    oeq_glob = str(legacy_root / f"{modality}-oeq" / "*_summary.csv")
    mcq_glob = str(legacy_root / modality / "*_summary.csv")
    oeq_path = oeq_path or (new_oeq if new_oeq and new_oeq.exists() else _latest(oeq_glob))
    mcq_path = mcq_path or (new_mcq if new_mcq and new_mcq.exists() else _latest(mcq_glob))
    if not oeq_path or not mcq_path:
        expected = (run_dir or RESULTS_DIR / "exp_7_mcq_oeq" / benchmark
                    / model_slug(model_spec))
        raise SystemExit(f"Need both MCQ and OEQ summaries below {expected}. "
                         "Run `python -m src.run experiments mcq-oeq` first.")
    df = load_merged(annotated_path, oeq_path, mcq_path)
    out_dir = (run_dir / "analysis" if run_dir and oeq_path == new_oeq
               else oeq_path.parent)
    slug = model_slug(model_spec)

    by_piec = _breakdown(df, "piec")
    by_skill = _breakdown(_explode_skills(df), "skill")

    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "analysis.csv", index=False)
    by_piec.to_csv(out_dir / "analysis_by_piec.csv", index=False)
    by_skill.to_csv(out_dir / "analysis_by_skill.csv", index=False)
    report = write_report(df, by_piec, by_skill, oeq_path, mcq_path, out_dir)
    figs = make_figures(by_piec, by_skill, slug)

    print(report.read_text())
    print(f"Wrote {out_dir/'analysis.csv'} + by_piec/by_skill CSVs")
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

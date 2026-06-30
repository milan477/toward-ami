"""Step 6: build the MCQ-vs-OEQ comparison table, broken down by level.

Reads a judged run and reports, per level (and overall):
    MCQ accuracy        auto-graded multiple choice
    OEQ accuracy        LLM-judged open-ended
    OEQ grounding       LLM-judged grounding in audio features
    Gap                 MCQ accuracy − OEQ accuracy  (how much MCQ inflates)

Writes table.md and table.csv into the run directory.

Usage:
    python -m experiments.oeq_mcq.table --run experiments/results/exp_3_oeq_vs_mcq/<ts>
    python -m experiments.oeq_mcq.table              # latest run
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from .judge import EXP_DIR, _latest_run
from .taxonomy import KEYS


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def build_table(run_dir: Path) -> pd.DataFrame:
    judged = sorted(run_dir.glob("judged_*.json"))
    src = judged[-1] if judged else None
    if src is None:
        src = sorted(run_dir.glob("results_*.json"))[0]
        print("(no judged file — OEQ columns will be blank; run judge.py first)")
    payload = json.loads(src.read_text())
    items = payload["items"]

    order = [*KEYS, "Overall"]
    rows = []
    for level in order:
        sel = items if level == "Overall" else [it for it in items if it["level"] == level]
        if not sel:
            continue
        mcq_acc = _mean([it["mcq"]["correct"] for it in sel])
        oeq_acc = _mean([it["oeq"].get("judge", {}).get("accuracy") for it in sel])
        oeq_gnd = _mean([it["oeq"].get("judge", {}).get("grounding") for it in sel])
        gap = (mcq_acc - oeq_acc) if (mcq_acc is not None and oeq_acc is not None) else None
        rows.append({
            "level": level, "n": len(sel),
            "mcq_accuracy": mcq_acc, "oeq_accuracy": oeq_acc,
            "oeq_grounding": oeq_gnd, "gap_mcq_minus_oeq": gap,
        })
    df = pd.DataFrame(rows)
    df.attrs["model"] = payload.get("model", "?")
    df.attrs["judge"] = payload.get("judge_model", "—")
    return df


def _fmt(v, pct=True):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:.0%}" if pct else f"{v:.2f}"


def to_markdown(df: pd.DataFrame) -> str:
    head = (f"## MCQ vs OEQ by level — model: {df.attrs.get('model')}  "
            f"(judge: {df.attrs.get('judge')})\n")
    cols = ["Level", "n", "MCQ acc", "OEQ acc", "OEQ grounding", "Gap (MCQ−OEQ)"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join([
            r["level"], str(r["n"]),
            _fmt(r["mcq_accuracy"]), _fmt(r["oeq_accuracy"]),
            _fmt(r["oeq_grounding"], pct=False), _fmt(r["gap_mcq_minus_oeq"]),
        ]) + " |")
    return head + "\n" + "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default=None, help="Run directory (default: latest).")
    args = ap.parse_args()
    run_dir = Path(args.run) if args.run else _latest_run()

    df = build_table(run_dir)
    md = to_markdown(df)
    (run_dir / "table.md").write_text(md)
    df.to_csv(run_dir / "table.csv", index=False)
    print(md)
    print(f"Saved {run_dir/'table.md'} and {run_dir/'table.csv'}")


if __name__ == "__main__":
    main()

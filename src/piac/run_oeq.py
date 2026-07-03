"""STEP 4 — AF-Next open-ended answers on the processed MMAR music set, graded by the
PIAC-aware judge (category-specific rules + hallucination flags).

Reuses the AF-Next generation phase from ``run_mmar_af_next_oeq`` (guided OEQ prompt with
answer_format/example, no truncation, multi-window patch) and replaces the judging phase
with ``src.piac.judge.PIACJudge``. Both models run sequentially (VRAM): AF-Next
answers, GPU is freed, then Qwen3 judges.

    python -m src.piac.run_oeq            # full 206 music questions
    python -m src.piac.run_oeq --limit 20 # POC gate

Outputs (datetime-prefixed) in results/mmar/af-next/music-oeq-piac/ :
    <stamp>_comparison.json / _summary.csv / _report.txt
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "scripts"))

from src.helpers.results import git_commit  # noqa: E402
from src.piac.judge import PIACJudge  # noqa: E402
from src.piac.taxonomy import PIAC_ORDER  # noqa: E402
from run_mmar_af_next_oeq import (  # noqa: E402
    _read_jsonl, build_audio_index, phase1_answers,
)

DEFAULT_DATA = ROOT / "data" / "benchmarks" / "mmar" / "mmar_ready.csv"
DEFAULT_OUTDIR = ROOT / "results" / "mmar" / "af-next" / "music-oeq-piac"


def _stem(audio_url: str) -> str:
    return audio_url.split("/")[-1].rsplit(".", 1)[0]


def phase2_piac(answers: dict[str, dict], judged_path: Path) -> dict[str, dict]:
    done = _read_jsonl(judged_path)
    todo = [qid for qid, a in answers.items() if qid not in done and not a.get("skipped")]
    if not todo:
        print(f"[phase2] all judged ({len(done)} present); skipping.")
        return done
    judge = PIACJudge()
    print(f"[phase2] PIAC judging with {judge.model_id}: {len(todo)} answers")
    fh = judged_path.open("a", encoding="utf-8")
    for i, qid in enumerate(todo, 1):
        a = answers[qid]
        v = judge.score(a.get("category", ""), a["question"], a["reference_answer"],
                        a.get("response", ""), a.get("answer_format", ""))
        rec = {"qid": qid, **v}
        done[qid] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        h = "HALL" if v["hallucinated"] else "    "
        print(f"  [{i}/{len(todo)}] {qid[:24]:<24} {a.get('category','?'):<11} "
              f"score={v['score']} norm={v['score_norm']} {h} {v['hallucination_level']}")
    fh.close()
    return done


def run(data_path: Path, out_dir: Path, limit: int | None) -> None:
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    df = pd.read_csv(data_path, dtype=str, keep_default_na=False)
    df = df[df["category_1"].str.lower() == "music"].reset_index(drop=True)
    if limit:
        df = df.head(limit)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_index = build_audio_index()
    started = datetime.now(timezone.utc).isoformat()
    print(f"Data: {data_path.name}  music questions: {len(df)}")

    skills_by_stem = {_stem(r["audio_url"]): r.get("skills", "") for _, r in df.iterrows()}
    cat_by_stem = {_stem(r["audio_url"]): r.get("category", "") for _, r in df.iterrows()}

    answers = phase1_answers(df, audio_index, out_dir / ".oeq_answers.jsonl")
    # The processed CSV is authoritative for the PIAC category (it may have been
    # recomputed after answers were generated); override the cached label so the
    # judge applies the current category's rubric.
    for qid, a in answers.items():
        if cat_by_stem.get(qid):
            a["category"] = cat_by_stem[qid]

    judged = phase2_piac(answers, out_dir / ".oeq_piac_judged.jsonl")

    finished = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    records = []
    for _, r in df.iterrows():
        qid = _stem(r["audio_url"])
        a = answers.get(qid, {"qid": qid})
        j = judged.get(qid, {})
        records.append({
            **a, "skills": r.get("skills", ""),
            "judge_score": j.get("score"), "judge_score_norm": j.get("score_norm"),
            "verdict": j.get("verdict"), "grounded": j.get("grounded"),
            "hallucinated": j.get("hallucinated"),
            "hallucination_level": j.get("hallucination_level"),
            "judge_rationale": j.get("rationale"),
        })

    scored = [r for r in records if r.get("judge_score_norm") is not None]
    mean = sum(r["judge_score_norm"] for r in scored) / len(scored) if scored else 0.0
    halluc = [r for r in scored if r.get("hallucinated")]
    by_piac, by_piac_h = defaultdict(list), defaultdict(list)
    for r in scored:
        c = r.get("category") or "(unclassified)"
        by_piac[c].append(r["judge_score_norm"])
        by_piac_h[c].append(1 if r.get("hallucinated") else 0)
    halluc_by_level = defaultdict(int)
    for r in halluc:
        halluc_by_level[r.get("hallucination_level") or "none"] += 1

    metadata = {
        "experiment": "mmar_af_next_oeq_piac",
        "answer_model": "nvidia/audio-flamingo-next-hf",
        "judge_model": "Qwen/Qwen3-8B (local, PIAC category-specific)",
        "config": {"data": str(data_path.relative_to(ROOT)), "question_form": "oeq_guided",
                   "n_questions": len(df), "judge": "PIAC category-specific + hallucination",
                   "judge_scale": "0-4 → /4", "audio_truncation": None},
        "git_commit": git_commit(), "run_started": started, "run_finished": finished,
        "run_local_datetime": stamp,
    }
    summary = {
        "n_questions": len(records),
        "n_answered": sum(1 for r in records if not r.get("skipped")),
        "n_judged": len(scored),
        "mean_score_norm": round(mean, 4),
        "hallucination_rate": round(len(halluc) / len(scored), 4) if scored else 0.0,
        "n_hallucinated": len(halluc),
        "hallucination_by_level": dict(halluc_by_level),
        "mean_score_norm_by_piac": {k: round(sum(v) / len(v), 4) for k, v in by_piac.items()},
        "hallucination_rate_by_piac": {
            k: round(sum(v) / len(v), 4) for k, v in by_piac_h.items()},
    }

    _write_comparison(out_dir, stamp, metadata, summary, records)
    _write_summary_csv(out_dir, stamp, records)
    _write_report(out_dir, stamp, metadata, summary)
    print(f"\nDone. mean norm {mean:.3f}  |  hallucination {summary['hallucination_rate']:.1%} "
          f"({len(halluc)}/{len(scored)})")
    print(f"Wrote results to {out_dir} (prefix {stamp})")


def _write_comparison(out_dir, stamp, metadata, summary, records) -> None:
    (out_dir / f"{stamp}_comparison.json").write_text(
        json.dumps({**metadata, "summary": summary, "items": records},
                   indent=2, ensure_ascii=False), encoding="utf-8")


def _write_summary_csv(out_dir, stamp, records) -> None:
    cols = ["qid", "category", "skills", "category_1", "category_2", "category_3", "question",
            "answer_format", "example_answer", "prompt", "reference_answer", "response",
            "judge_score", "judge_score_norm", "verdict", "grounded", "hallucinated",
            "hallucination_level", "judge_rationale", "skipped", "error"]
    with (out_dir / f"{stamp}_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in records:
            row = dict(r)
            row["response"] = (r.get("response") or "").replace("\n", " ").strip()
            w.writerow(row)


def _write_report(out_dir, stamp, metadata, summary) -> None:
    lines = [
        "Audio Flamingo Next — MMAR music OEQ, PIAC-judged (+ hallucination)",
        "=" * 62,
        f"Answer model: {metadata['answer_model']}",
        f"Judge model:  {metadata['judge_model']}  (category-specific rubric)",
        f"Git commit:   {metadata['git_commit']}",
        f"Run datetime: {metadata['run_local_datetime']} (local)",
        "",
        "Overall",
        "-" * 62,
        f"  questions / answered / judged:  {summary['n_questions']} / "
        f"{summary['n_answered']} / {summary['n_judged']}",
        f"  mean score (0-1):               {summary['mean_score_norm']:.4f}",
        f"  hallucination rate:             {summary['hallucination_rate']:.2%} "
        f"({summary['n_hallucinated']})",
        f"  hallucination by failing level: {summary['hallucination_by_level']}",
        "",
        "Per PIAC category:  mean score (0-1)   |   hallucination rate",
        "-" * 62,
    ]
    ms = summary["mean_score_norm_by_piac"]
    hr = summary["hallucination_rate_by_piac"]
    for c in [*PIAC_ORDER, *[k for k in ms if k not in PIAC_ORDER]]:
        if c in ms:
            lines.append(f"  {c:<14} {ms[c]:.4f}                {hr.get(c, 0):.2%}")
    (out_dir / f"{stamp}_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run(Path(args.data), Path(args.outdir), args.limit)


if __name__ == "__main__":
    main()

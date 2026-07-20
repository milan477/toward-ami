"""Reusable result writers for experiment outputs."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from src.analysis.taxonomy import PIAC_ORDER
from src.querying.common import audio_stem

MCQ_COLS = [
    "qid", "category", "skills", "category_1", "category_2", "category_3", "category_4",
    "question", "prompt", "correct_answer", "correct_letter", "pred_letter", "pred_answer",
    "response", "correct", "skipped", "error",
]

OEQ_COLS = [
    "qid", "category", "skills", "category_1", "category_2", "category_3", "category_4",
    "question", "answer_format", "example_answer", "prompt", "reference_answer",
    "response", "judge_score", "judge_score_norm", "verdict", "grounded",
    "hallucinated", "hallucination_level", "judge_rationale", "skipped", "error",
]

PROBE_COLS = [
    "qid", "probe_idx", "level", "target_category", "question", "probe_question",
    "expected", "response", "judge_score", "judge_score_norm", "verdict",
    "hallucinated", "skipped", "error",
]


def records_for_rows(df, answers: dict[str, dict]) -> list[dict]:
    records = []
    for _, row in df.iterrows():
        qid = audio_stem(row["audio_url"])
        records.append(answers.get(qid, {"qid": qid}))
    return records


def write_mcq_outputs(out_dir: Path, stamp: str, metadata: dict,
                      df, answers: dict[str, dict]) -> dict:
    records = records_for_rows(df, answers)
    scored = [r for r in records if not r.get("skipped") and not r.get("error")]
    correct = sum(1 for r in scored if r.get("correct"))
    accuracy = correct / len(scored) if scored else 0.0
    by_piac: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for record in scored:
        category = record.get("category") or "?"
        by_piac[category][0] += int(bool(record.get("correct")))
        by_piac[category][1] += 1

    summary = {
        "n": len(records),
        "n_scored": len(scored),
        "accuracy": round(accuracy, 4),
        "accuracy_by_piac": {
            k: round(v[0] / v[1], 4) for k, v in by_piac.items() if v[1]
        },
    }
    _write_csv(out_dir / "summary.csv", MCQ_COLS, records)
    _write_json(out_dir / "comparison.json",
                {**metadata, "form": "mcq", "summary": summary, "items": records})
    _write_text(out_dir / "report.txt", _mcq_report(metadata, stamp, accuracy, correct, scored, by_piac))
    return summary


def write_oeq_outputs(out_dir: Path, stamp: str, metadata: dict,
                      records: list[dict]) -> dict:
    scored = [r for r in records if r.get("judge_score_norm") is not None]
    mean = sum(r["judge_score_norm"] for r in scored) / len(scored) if scored else 0.0
    hallucinated = [r for r in scored if r.get("hallucinated")]
    by_piac: dict[str, list[float]] = defaultdict(list)
    for record in scored:
        by_piac[record.get("category") or "?"].append(record["judge_score_norm"])

    summary = {
        "n": len(records),
        "n_judged": len(scored),
        "mean_score_norm": round(mean, 4),
        "hallucination_rate": round(len(hallucinated) / len(scored), 4) if scored else 0.0,
        "mean_score_norm_by_piac": {
            k: round(sum(v) / len(v), 4) for k, v in by_piac.items()
        },
    }
    _write_csv(out_dir / "summary.csv", OEQ_COLS, records)
    _write_json(out_dir / "comparison.json", {
        **metadata,
        "form": "oeq",
        "judge": "PIAC category-specific",
        "summary": summary,
        "items": records,
    })
    _write_text(out_dir / "report.txt", _oeq_report(metadata, stamp, mean, hallucinated, scored, by_piac, summary))
    return summary


def write_probe_outputs(out_dir: Path, stamp: str, metadata: dict,
                        records: list[dict]) -> dict:
    scored = [r for r in records if r.get("judge_score_norm") is not None]
    by_level_correct: dict[str, list[int]] = defaultdict(list)
    by_level_score: dict[str, list[float]] = defaultdict(list)
    for record in scored:
        by_level_correct[record["level"]].append(1 if record["judge_score_norm"] == 1.0 else 0)
        by_level_score[record["level"]].append(record["judge_score_norm"])

    chain = _chain_summary(scored)
    summary = {
        "n_questions": metadata["config"]["n_questions"],
        "n_probes": len(records),
        "n_judged": len(scored),
        "accuracy_by_level": {
            level: round(sum(vals) / len(vals), 4) for level, vals in by_level_correct.items()
        },
        "mean_score_by_level": {
            level: round(sum(vals) / len(vals), 4) for level, vals in by_level_score.items()
        },
        "n_by_level": {level: len(vals) for level, vals in by_level_correct.items()},
        "chain": chain,
    }
    _write_csv(out_dir / "summary.csv", PROBE_COLS, records)
    _write_json(out_dir / "comparison.json",
                {**metadata, "summary": summary, "items": records})
    _write_text(out_dir / "report.txt", _probe_report(metadata, summary))
    return summary


def _write_csv(path: Path, cols: list[str], records: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["response"] = (record.get("response") or "").replace("\n", " ").strip()
            writer.writerow(row)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mcq_report(metadata, stamp, accuracy, correct, scored, by_piac) -> list[str]:
    lines = [
        f"{metadata['model']} - {metadata['benchmark']} {metadata['modality']} MCQ",
        "=" * 48,
        f"Run: {stamp}   commit {metadata['git_commit']}",
        f"accuracy: {accuracy:.2%}  ({correct}/{len(scored)})",
        "",
        "By PIAC category:",
    ]
    for category in [*PIAC_ORDER, *[k for k in by_piac if k not in PIAC_ORDER]]:
        if category in by_piac and by_piac[category][1]:
            lines.append(f"  {category:<12} {by_piac[category][0] / by_piac[category][1]:.2%}  "
                         f"(n={by_piac[category][1]})")
    return lines


def _oeq_report(metadata, stamp, mean, hallucinated, scored, by_piac, summary) -> list[str]:
    lines = [
        f"{metadata['model']} - {metadata['benchmark']} {metadata['modality']} OEQ (PIAC-judged)",
        "=" * 48,
        f"Run: {stamp}   commit {metadata['git_commit']}",
        f"mean score (0-1): {mean:.4f}   hallucination: {summary['hallucination_rate']:.2%} "
        f"({len(hallucinated)}/{len(scored)})",
        "",
        "By PIAC category (mean score | n):",
    ]
    for category in [*PIAC_ORDER, *[k for k in by_piac if k not in PIAC_ORDER]]:
        if category in by_piac:
            vals = by_piac[category]
            lines.append(f"  {category:<12} {sum(vals) / len(vals):.4f}  (n={len(vals)})")
    return lines


def _chain_summary(scored: list[dict]) -> dict:
    chains: dict[str, list[dict]] = defaultdict(list)
    for record in scored:
        chains[record["qid"]].append(record)
    quad: dict[tuple[bool, bool], int] = defaultdict(int)
    base_correct = final_correct = n_chains = 0
    for probes in chains.values():
        probes = sorted(probes, key=lambda item: item["probe_idx"])
        if not probes:
            continue
        n_chains += 1
        base_ok = probes[0]["judge_score_norm"] == 1.0
        final_ok = probes[-1]["judge_score_norm"] == 1.0
        base_correct += base_ok
        final_correct += final_ok
        quad[(base_ok, final_ok)] += 1
    return {
        "n_chains": n_chains,
        "perceptual_base_correct": round(base_correct / n_chains, 4) if n_chains else 0,
        "final_correct": round(final_correct / n_chains, 4) if n_chains else 0,
        "base_ok_final_ok": quad[(True, True)],
        "base_ok_final_wrong": quad[(True, False)],
        "base_wrong_final_ok": quad[(False, True)],
        "base_wrong_final_wrong": quad[(False, False)],
    }


def _probe_report(metadata, summary) -> list[str]:
    cfg = metadata["config"]
    acc = summary["accuracy_by_level"]
    mean = summary["mean_score_by_level"]
    counts = summary["n_by_level"]
    chain = summary["chain"]
    lines = [
        f"{metadata['answer_model']} - {metadata['benchmark']} {metadata['modality']} probe chains",
        "=" * 66,
        f"Answer model: {metadata['answer_model']}",
        f"Judge model:  {metadata['judge_model']}",
        f"Git commit:   {metadata['git_commit']}",
        f"Run datetime: {metadata['run_local_datetime']} (local)",
        f"Questions: {cfg['n_questions']}   probes: {cfg['n_probes']}   judged: {summary['n_judged']}",
        "",
        "Accuracy by PIAC probe level  (correct = judge score 4/4; affective also shows mean)",
        "-" * 66,
    ]
    for level in PIAC_ORDER:
        if level in acc:
            extra = f"   mean {mean[level]:.2f}" if level == "affective" else ""
            lines.append(f"  {level:<14} {acc[level]:6.1%}   (n={counts[level]}){extra}")
    lines += [
        "",
        "Chain diagnostic - does the FINAL answer rest on a correct PERCEPTUAL base?",
        "-" * 66,
        f"  chains analysed:            {chain['n_chains']}",
        f"  perceptual base correct:    {chain['perceptual_base_correct']:.1%}",
        f"  final (target) correct:     {chain['final_correct']:.1%}",
        "",
        f"  base OK & final OK:         {chain['base_ok_final_ok']:>4}   (grounded success)",
        f"  base OK & final wrong:      {chain['base_ok_final_wrong']:>4}   (lost it higher up)",
        f"  base wrong & final OK:      {chain['base_wrong_final_ok']:>4}   (right answer, wrong ground)",
        f"  base wrong & final wrong:   {chain['base_wrong_final_wrong']:>4}   (broken from the base)",
    ]
    return lines

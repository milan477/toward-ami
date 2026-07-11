"""Experiment 4: query and judge decomposed probe chains."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from models.client import make_client
from src.config import DEFAULT_ANNOTATED_DATA, DEFAULT_MODALITY, DEFAULT_RUNNER_MODEL
from src.evaluation.prompts import INSTRUCTION_OEQ_GUIDED
from src.evaluation.scoring import judge_probe_answers, merge_probe_records
from src.helpers.results import git_commit
from src.querying.common import audio_stem, build_audio_index, infer_benchmark_name, resolve_path, result_dir
from src.querying.probes import query_probe_answers
from src.reporting.results import write_probe_outputs


def probe_key(qid: str, idx: int) -> str:
    return f"{qid}#{idx}"


def iter_probe_units(df) -> list[dict]:
    units = []
    for _, row in df.iterrows():
        qid = audio_stem(row["audio_url"])
        try:
            probes = json.loads(row.get("probes") or "[]")
        except json.JSONDecodeError:
            probes = []
        for idx, probe in enumerate(probes):
            if not isinstance(probe, dict) or not probe.get("question"):
                continue
            question = probe["question"]
            units.append({
                "key": probe_key(qid, idx),
                "qid": qid,
                "probe_idx": idx,
                "audio_url": row["audio_url"],
                "level": probe.get("level", ""),
                "probe_question": question,
                "expected": probe.get("expected", ""),
                "prompt": f"{INSTRUCTION_OEQ_GUIDED}\n\nQuestion: {question}",
                "n_probes": row.get("n_probes", ""),
                "category": row.get("category", ""),
                "question": row.get("question", ""),
            })
    return units


def run(model_spec: str, data_path: Path, modality: str | None, out_dir: Path | None,
        limit: int | None) -> None:
    data_path = resolve_path(data_path)
    df = pd.read_csv(data_path, dtype=str, keep_default_na=False)
    if modality:
        df = df[df["category_1"].str.lower() == modality.lower()].reset_index(drop=True)
    if "probes" not in df.columns:
        raise SystemExit("No `probes` column. Run: python -m src.run decomposition decompose mmar")
    if limit:
        df = df.head(limit)

    benchmark = infer_benchmark_name(data_path)
    label = modality or "all"
    out_dir = out_dir or result_dir(benchmark, model_spec, f"{label}-probes")
    out_dir.mkdir(parents=True, exist_ok=True)

    client = make_client(model_spec)
    audio_index = build_audio_index()
    probe_units = iter_probe_units(df)
    started = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    print(f"Model: {model_spec}  |  {benchmark} {label} questions: {len(df)}  probes: {len(probe_units)}")

    answers = query_probe_answers(probe_units, audio_index, client, out_dir / ".probe_answers.jsonl")
    judged = judge_probe_answers(answers, out_dir / ".probe_judged.jsonl")
    records = merge_probe_records(probe_units, answers, judged)

    metadata = {
        "experiment": "probe_eval",
        "benchmark": benchmark,
        "modality": label,
        "answer_model": getattr(client, "model_id", model_spec),
        "judge_model": "PIACJudge",
        "config": {
            "data": str(data_path),
            "unit": "probe",
            "n_questions": len(df),
            "n_probes": len(probe_units),
            "model": model_spec,
        },
        "git_commit": git_commit(),
        "run_started": started,
        "run_finished": datetime.now(timezone.utc).isoformat(),
        "run_local_datetime": stamp,
    }
    summary = write_probe_outputs(out_dir, stamp, metadata, records)
    print(f"\nDone. {summary['n_judged']} probes judged over {summary['chain']['n_chains']} chains.")
    print("Accuracy by level:", summary["accuracy_by_level"])
    print(f"Wrote results to {out_dir} (prefix {stamp})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_RUNNER_MODEL)
    parser.add_argument("--data", default=str(DEFAULT_ANNOTATED_DATA))
    parser.add_argument("--modality", default=DEFAULT_MODALITY,
                        help="filter category_1 (default: music; pass '' for all)")
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(args.model, Path(args.data), args.modality or None,
        Path(args.outdir) if args.outdir else None, args.limit)


if __name__ == "__main__":
    main()

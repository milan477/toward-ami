"""Experiment 0: MCQ plus OEQ benchmark evaluation for one model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from models.client import make_client
from src.config import DEFAULT_ANNOTATED_DATA, DEFAULT_MODALITY, DEFAULT_RUNNER_MODEL
from src.evaluation.scoring import judge_piac_answers, merge_oeq_records
from src.helpers.results import git_commit
from src.querying.common import (
    audio_stem,
    build_audio_index,
    infer_benchmark_name,
    read_jsonl,
    resolve_path,
    result_dir,
)
from src.querying.model_eval import query_answers
from src.reporting.results import write_mcq_outputs, write_oeq_outputs


def run(model_spec: str, data_path: Path, modality: str | None, limit: int | None) -> None:
    data_path = resolve_path(data_path)
    df = pd.read_csv(data_path, dtype=str, keep_default_na=False)
    if modality:
        df = df[df["category_1"].str.lower() == modality.lower()].reset_index(drop=True)
    if limit:
        df = df.head(limit)

    benchmark = infer_benchmark_name(data_path)
    label = modality or "all"
    mcq_dir = result_dir(benchmark, model_spec, label)
    oeq_dir = result_dir(benchmark, model_spec, f"{label}-oeq-piac")
    mcq_dir.mkdir(parents=True, exist_ok=True)
    oeq_dir.mkdir(parents=True, exist_ok=True)

    client = make_client(model_spec)
    audio_index = build_audio_index()
    started = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    metadata = {
        "model": model_spec,
        "benchmark": benchmark,
        "modality": label,
        "git_commit": git_commit(),
        "run_started": started,
        "run_local_datetime": stamp,
    }
    print(f"Model: {model_spec}  |  {benchmark} {label} questions: {len(df)}")

    mcq_answers = query_answers(df, audio_index, client, mcq_dir / ".mcq.jsonl", "mcq")
    write_mcq_outputs(mcq_dir, stamp, metadata, df, mcq_answers)
    print(f"Wrote MCQ -> {mcq_dir}  (prefix {stamp})")

    oeq_answers = query_answers(df, audio_index, client, oeq_dir / ".oeq_answers.jsonl", "oeq")
    judged_path = oeq_dir / ".oeq_piac_judged.jsonl"
    try:
        judged = judge_piac_answers(oeq_answers, judged_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[judge] FAILED ({type(exc).__name__}: {str(exc)[:140]}) - writing OEQ "
              f"answers without scores; re-run to finish judging.")
        judged = read_jsonl(judged_path)
    oeq_records = merge_oeq_records(df, oeq_answers, judged, lambda row: audio_stem(row["audio_url"]))
    write_oeq_outputs(oeq_dir, stamp, metadata, oeq_records)
    print(f"Wrote OEQ -> {oeq_dir}  (prefix {stamp}, {len(judged)}/{len(oeq_answers)} judged)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_RUNNER_MODEL)
    parser.add_argument("--data", default=str(DEFAULT_ANNOTATED_DATA))
    parser.add_argument("--modality", default=DEFAULT_MODALITY,
                        help="filter category_1 (default: music; pass '' for all)")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(args.model, Path(args.data), args.modality or None, args.limit)


if __name__ == "__main__":
    main()

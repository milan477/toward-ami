"""Experiment 7: legacy MCQ plus OEQ benchmark evaluation for one model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from models.client import make_client
from src.config import DEFAULT_ANNOTATED_DATA, DEFAULT_MODALITY, DEFAULT_RUNNER_MODEL, DEFAULT_SELECTED_DATA
from src.evaluation.scoring import judge_piec_answers, merge_oeq_records
from src.helpers.results import git_commit
from src.querying.common import (
    build_audio_index,
    create_result_dir,
    infer_benchmark_name,
    read_jsonl,
    resolve_path,
    row_qid,
)
from src.querying.model_eval import query_answers
from src.reporting.results import write_mcq_outputs, write_oeq_outputs

EXPERIMENT_NAME = Path(__file__).stem


def run(
    model_spec: str,
    data_path: Path,
    modality: str | None,
    limit: int | None,
    *,
    no_judge: bool = False,
) -> None:
    data_path = resolve_path(data_path)
    if not data_path.exists():
        raise SystemExit(f"Data not found: {data_path}")
    df = pd.read_csv(data_path, dtype=str, keep_default_na=False)
    if modality:
        df = df[df["focus"].str.lower().str.contains(modality.lower(), regex=False)].reset_index(drop=True)
    if limit:
        df = df.head(limit)

    benchmark = infer_benchmark_name(data_path)
    label = modality or "all"
    run_dir = create_result_dir(EXPERIMENT_NAME, benchmark, model_spec)
    mcq_dir = run_dir / "mcq"
    oeq_dir = run_dir / "oeq"
    mcq_dir.mkdir()
    oeq_dir.mkdir()

    client = make_client(model_spec)
    audio_index = build_audio_index()
    started = datetime.now(timezone.utc).isoformat()
    stamp = run_dir.name
    metadata = {
        "experiment": EXPERIMENT_NAME,
        "model": model_spec,
        "benchmark": benchmark,
        "modality": label,
        "data": str(data_path),
        "limit": limit,
        "judge": None if no_judge else "piac",
        "git_commit": git_commit(),
        "run_started": started,
        "run_local_datetime": stamp,
        "result_dir": str(run_dir),
    }
    print(f"Model: {model_spec}  |  {benchmark} {label} questions: {len(df)}")
    print(f"Run -> {run_dir}")
    print(f"MCQ -> {mcq_dir}")
    print(f"OEQ -> {oeq_dir}")

    mcq_answers = query_answers(df, audio_index, client, mcq_dir / ".mcq.jsonl", "mcq")
    write_mcq_outputs(mcq_dir, stamp, metadata, df, mcq_answers)
    print(f"Wrote MCQ -> {mcq_dir}")

    oeq_answers = query_answers(df, audio_index, client, oeq_dir / ".oeq_answers.jsonl", "oeq")
    judged: dict[str, dict] = {}
    if no_judge:
        print("[judge] skipped (--no-judge); writing OEQ responses only.")
    else:
        judged_path = oeq_dir / ".oeq_piac_judged.jsonl"
        try:
            judged = judge_piec_answers(oeq_answers, judged_path)
        except Exception as exc:  # noqa: BLE001
            print(f"[judge] unavailable ({type(exc).__name__}: {str(exc)[:140]}) - "
                  f"writing OEQ responses without scores.")
            judged = read_jsonl(judged_path)
    oeq_records = merge_oeq_records(df, oeq_answers, judged, row_qid)
    write_oeq_outputs(oeq_dir, stamp, metadata, oeq_records)
    n_judged = sum(1 for r in oeq_records if r.get("judge_score_norm") is not None)
    print(f"Wrote OEQ -> {oeq_dir}  ({n_judged}/{len(oeq_answers)} judged)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_RUNNER_MODEL)
    parser.add_argument(
        "--data",
        default=str(DEFAULT_ANNOTATED_DATA if DEFAULT_ANNOTATED_DATA.exists() else DEFAULT_SELECTED_DATA),
    )
    parser.add_argument("--modality", default=DEFAULT_MODALITY,
                        help="filter normalized focus (default: music; pass '' for all)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-judge", action="store_true",
                        help="record OEQ responses only; skip PIAC judge scoring")
    args = parser.parse_args()
    run(args.model, Path(args.data), args.modality or None, args.limit, no_judge=args.no_judge)


if __name__ == "__main__":
    main()

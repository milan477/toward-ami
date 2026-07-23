"""Shared execution engine for the benchmark experiment variants."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from models.client import make_client
from src.analysis.taxonomy import row_piec
from src.config import (
    DATA_DIR,
    DEFAULT_DATASET,
    DEFAULT_RUNNER_MODEL,
    MCQ_MAX_TOKENS,
    OEQ_MAX_TOKENS,
)
from src.evaluation.prompts import extract_letter
from src.evaluation.scoring import judge_piec_answers, merge_oeq_records
from src.experiments.variants import (
    ExperimentVariant,
    build_variant_item,
    extract_option_text,
    get_variant,
    prompt_configuration,
    required_columns,
)
from src.helpers.results import git_commit
from src.querying.common import (
    audio_name,
    build_audio_index,
    create_result_dir,
    creator_categories,
    infer_benchmark_name,
    read_jsonl,
    resolve_path,
    row_audio,
    row_has_focus,
    row_qid,
)
from src.querying.model_eval import generate_with_retries
from src.reporting.results import write_mcq_outputs, write_oeq_outputs


def _append_jsonl(path: Path, record: dict) -> None:
    """Append one immutable acquisition attempt; readers keep the latest qid."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _needs_query(record: dict | None) -> bool:
    if not record:
        return True
    if record.get("skipped"):
        return False
    return bool(record.get("error")) or not str(record.get("response", "")).strip()


def query_variant_answers(
    df,
    audio_index: dict[str, Path],
    client,
    cache: Path,
    variant: ExperimentVariant,
    *,
    provenance: dict | None = None,
) -> dict[str, dict]:
    """Run one configured benchmark representation, caching after every row."""
    done = read_jsonl(cache)
    todo = [row for _, row in df.iterrows() if _needs_query(done.get(row_qid(row)))]
    print(f"[{variant.experiment_name}] {client.model_id}: {len(todo)} to answer")

    for index, row in enumerate(todo, 1):
        qid = row_qid(row)
        audio = audio_index.get(audio_name(row_audio(row))) if variant.use_audio else None
        transcription = str(row.get("transcription", ""))
        item = build_variant_item(
            row,
            variant,
            transcription=transcription if variant.use_stt else "",
        )
        if variant.use_audio and audio is None:
            record = {
                **_result_record(
                    row, variant, item, "", None, None, transcription
                ),
                "skipped": "no_audio",
            }
        else:
            response, error = generate_with_retries(
                client,
                item["prompt"],
                audio,
                MCQ_MAX_TOKENS
                if variant.response_mode in {"letter", "option_text"}
                else OEQ_MAX_TOKENS,
            )
            record = _result_record(
                row, variant, item, response, error, audio, transcription
            )

        record.update(provenance or {})

        done[qid] = record
        _append_jsonl(cache, record)
        status = "ERR" if record.get("error") else (
            "SKIP" if record.get("skipped") else "OK"
        )
        print(
            f"  [{index}/{len(todo)}] {qid[:28]:<28} {status} "
            f"{str(record.get('response', record.get('skipped', '')))[:60]!r}"
        )
    return done


def _result_record(
    row,
    variant: ExperimentVariant,
    item: dict,
    response: str,
    error: str | None,
    audio: Path | None,
    transcription: str,
) -> dict:
    categories = creator_categories(row)
    base = {
        "qid": row_qid(row),
        "experiment_variant": variant.experiment_name,
        "audio_used": audio.name if audio else "",
        "transcription": transcription,
        "task_rewrite_model": row.get("task_rewrite_model", ""),
        "task_rewrite_model_spec": row.get("task_rewrite_model_spec", ""),
        "task_rewrite_model_info": row.get("task_rewrite_model_info", ""),
        "task_rewrite_equivalent": row.get("task_rewrite_equivalent", ""),
        "task_rewrite_imperative": row.get("task_rewrite_imperative", ""),
        "task_rewrite_rationale": row.get("task_rewrite_rationale", ""),
        "task_rewrite_prompt": row.get("task_rewrite_prompt", ""),
        "task_rewrite_raw": row.get("task_rewrite_raw", ""),
        "task_verification_prompt": row.get("task_verification_prompt", ""),
        "task_verification_raw": row.get("task_verification_raw", ""),
        "original_question": item["original_question"],
        "original_answer": row.get("answer", ""),
        "distractors": row.get("distractors", ""),
        "question": item["question"],
        "question_nature": row.get("question_nature", ""),
        "category": row_piec(row),
        "piec": row_piec(row),
        "action_content": row.get("action_content", ""),
        "creator_categories": json.dumps(categories, ensure_ascii=False),
        "prompt": item["prompt"],
        "response": response,
        "error": error,
    }
    if variant.response_mode == "letter":
        prediction = extract_letter(response, item["letter_map"]) if not error else None
        return {
            **base,
            "correct_answer": item["correct_answer"],
            "correct_letter": item["correct_letter"],
            "pred_letter": prediction,
            "pred_answer": item["letter_map"].get(prediction) if prediction else None,
            "correct": prediction == item["correct_letter"] if prediction else False,
        }
    if variant.response_mode == "option_text":
        prediction = extract_option_text(response, item["options"]) if not error else None
        prediction_letter = next(
            (letter for letter, option in item["letter_map"].items() if option == prediction),
            None,
        )
        return {
            **base,
            "correct_answer": item["correct_answer"],
            "correct_letter": item["correct_letter"],
            "pred_letter": prediction_letter,
            "pred_answer": prediction,
            "correct": prediction == item["correct_answer"] if prediction else False,
        }
    return {
        **base,
        "answer_format": item["answer_format"],
        "reference_answer": item["reference_answer"],
    }


def run_variant(
    number: int,
    model_spec: str,
    data_path: Path | None,
    modality: str | None,
    limit: int | None,
    *,
    benchmark_name: str | None = None,
    no_judge: bool = False,
    qid_subset: list[str] | None = None,
    run_dir_override: Path | None = None,
) -> Path:
    variant = get_variant(number)
    if data_path is None:
        benchmark_name = benchmark_name or DEFAULT_DATASET
        stage = (
            "normalized_selected_enhanced"
            if variant.requires_enhanced
            else "normalized_selected"
        )
        data_path = (
            DATA_DIR / "benchmarks" / benchmark_name / f"{benchmark_name}_{stage}.csv"
        )
    resolved_data = resolve_path(data_path)
    if not resolved_data.exists():
        stage = "enhanced" if variant.requires_enhanced else "selected"
        raise SystemExit(f"Required {stage} benchmark data not found: {resolved_data}")

    df = pd.read_csv(resolved_data, dtype=str, keep_default_na=False)
    missing = sorted(required_columns(variant) - set(df.columns))
    if missing:
        raise SystemExit(
            f"{resolved_data} is missing columns required by {variant.experiment_name}: "
            + ", ".join(missing)
        )
    if modality:
        df = df[df.apply(lambda row: row_has_focus(row, modality), axis=1)].reset_index(drop=True)
    if qid_subset is not None:
        positions = {qid: index for index, qid in enumerate(qid_subset)}
        df = df[df["qid"].isin(positions)].copy()
        df["_campaign_order"] = df["qid"].map(positions)
        df = df.sort_values("_campaign_order").drop(columns="_campaign_order").reset_index(drop=True)
        missing_qids = [qid for qid in qid_subset if qid not in set(df["qid"])]
        if missing_qids:
            raise SystemExit(
                f"{resolved_data} is missing campaign qids: " + ", ".join(missing_qids)
            )
    elif limit is not None:
        df = df.head(limit)

    benchmark = benchmark_name or infer_benchmark_name(resolved_data)
    client = make_client(model_spec)
    if run_dir_override is None:
        run_dir = create_result_dir(variant.experiment_name, benchmark, model_spec)
    else:
        run_dir = resolve_path(run_dir_override)
        run_dir.mkdir(parents=True, exist_ok=True)
    stamp = run_dir.name
    run_config = {
        "variant": variant.metadata(),
        "prompt_configuration": prompt_configuration(variant),
        "modality": modality or "all",
        "data": str(resolved_data),
        "limit": limit,
        "qid_subset": qid_subset,
        "transcription_source": "enhanced.csv" if variant.use_stt else None,
        "judge": None if no_judge or variant.response_mode != "open_text" else "piec",
    }
    model_info = client.info()
    commit = git_commit()
    metadata = {
        "experiment": variant.experiment_name,
        "variant": variant.metadata(),
        "prompt_configuration": prompt_configuration(variant),
        "config": run_config,
        "model": model_spec,
        "model_info": model_info,
        "benchmark": benchmark,
        "modality": modality or "all",
        "data": str(resolved_data),
        "limit": limit,
        "transcription_source": "enhanced.csv" if variant.use_stt else None,
        "judge": None if no_judge or variant.response_mode != "open_text" else "piec",
        "git_commit": commit,
        "run_started": datetime.now(timezone.utc).isoformat(),
        "run_local_datetime": stamp,
        "result_dir": str(run_dir),
    }
    print(f"Experiment: {variant.experiment_name} - {variant.description}")
    print(f"Model: {model_spec} | {benchmark} {metadata['modality']}: {len(df)} questions")
    print(f"Run -> {run_dir}")

    answers = query_variant_answers(
        df,
        build_audio_index(DATA_DIR / "audio" / benchmark),
        client,
        run_dir / "items.jsonl",
        variant,
        provenance={
            "model": model_spec,
            "model_info": json.dumps(model_info, ensure_ascii=False, sort_keys=True),
            "git_commit": commit,
            "run_config": json.dumps(run_config, ensure_ascii=False, sort_keys=True),
        },
    )

    if variant.response_mode != "open_text":
        write_mcq_outputs(run_dir, stamp, metadata, df, answers)
    else:
        judged = {}
        if not no_judge:
            judged = judge_piec_answers(answers, run_dir / ".judged.jsonl")
        records = merge_oeq_records(df, answers, judged, row_qid)
        write_oeq_outputs(run_dir, stamp, metadata, records)
    print(f"Wrote results -> {run_dir}")
    return run_dir


def main_for(number: int) -> None:
    variant = get_variant(number)
    parser = argparse.ArgumentParser(description=variant.description)
    parser.add_argument("benchmark", nargs="?", default=DEFAULT_DATASET)
    parser.add_argument("--model", default=DEFAULT_RUNNER_MODEL)
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument(
        "--modality",
        default="",
        help="optional exact normalized focus filter (default: run the full benchmark)",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-judge", action="store_true")
    args = parser.parse_args()
    run_variant(
        number,
        args.model,
        args.data,
        args.modality or None,
        args.limit,
        benchmark_name=args.benchmark,
        no_judge=args.no_judge,
    )

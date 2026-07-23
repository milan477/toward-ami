"""Enhance selected normalized questions with five standardized LLM-derived fields."""

from __future__ import annotations

import csv
from collections import Counter
import json
from pathlib import Path

from download.common import bench_dir, bench_path
from src.config import ANALYSIS_COLS, DEFAULT_JUDGE_SPEC
from src.analysis.annotators import build_annotators
from src.analysis.transcribe import (
    AudioTranscriber,
    TRANSCRIPTION_COLUMN,
    should_transcribe,
)
from src.analysis.rewrite_questions import (
    ANSWER_OEQ_COLUMN,
    QUESTION_OEQ_COLUMN,
    QuestionRewriter,
)
from src.analysis.task_rewrite import (
    TASK_QUESTION_COLUMN,
    TASK_REWRITE_COLUMNS,
    TaskQuestionRewriter,
)
from src.helpers.results import git_commit


def _analysis_path(name: str) -> Path:
    return bench_dir(name) / f".{name}.normalized_selected.enhancement.jsonl"


def _read_jsonl(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        records[rec["qid"]] = rec
    return records


def _prior_enhanced(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {
            row["qid"]: row for row in csv.DictReader(handle) if row.get("qid")
        }


def _matches_focus(raw: str, wanted: str) -> bool:
    try:
        values = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        values = [raw]
    return wanted.casefold() in {str(value).casefold() for value in values}


def _field_is_required(column: str, values: dict) -> bool:
    return not (
        column == "example_incorrect_answer"
        and values.get("question_nature") == "true_false"
    )


def _analysis_complete(values: dict) -> bool:
    """Treat the intentionally blank true/false incorrect example as complete."""
    return all(
        not _field_is_required(column, values)
        or bool(str(values.get(column, "")).strip())
        for column in ANALYSIS_COLS
    )


def _enhancement_complete(values: dict) -> bool:
    return (
        _analysis_complete(values)
        and bool(str(values.get(QUESTION_OEQ_COLUMN, "")).strip())
        and bool(str(values.get(ANSWER_OEQ_COLUMN, "")).strip())
        and bool(str(values.get(TASK_QUESTION_COLUMN, "")).strip())
    )


def _annotator_is_missing(annotator, values: dict) -> bool:
    return any(
        _field_is_required(column, values)
        and not str(values.get(column, "")).strip()
        for column in annotator.output_columns
    )


def enhance(
    name: str,
    modality: str | None = None,
    limit: int | None = None,
    *,
    judge_spec: str = DEFAULT_JUDGE_SPEC,
    transcriber_spec: str | None = None,
    rewriter_spec: str | None = None,
    task_rewriter_spec: str | None = None,
    overwrite: bool = False,
) -> Path:
    source = bench_path(name, "selected")
    if not source.exists():
        raise SystemExit(
            f"No selected normalized dataset at {source}. Run: python download/clean.py {name}"
        )

    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        source_cols = reader.fieldnames or []
        records = list(reader)
    if modality:
        if "focus" not in source_cols:
            raise SystemExit(f"{source} has no focus column; rebuild it with download/normalize.py")
        records = [row for row in records if _matches_focus(row.get("focus", ""), modality)]
        print(f"Filtered to focus containing {modality!r}: {len(records)} rows")

    out_path = bench_path(name, "enhanced")

    prior_enhanced = {} if overwrite else _prior_enhanced(out_path)
    cache_path = _analysis_path(name)
    cached = {} if overwrite else _read_jsonl(cache_path)

    annotators = build_annotators(judge_spec)
    transcriber = None
    if transcriber_spec or getattr(annotators[0].client, "supports_audio", False):
        transcriber = AudioTranscriber(
            name, transcriber_spec or judge_spec, overwrite=overwrite
        )
    rewrite_model_spec = rewriter_spec or judge_spec
    rewrite_client = annotators[0].client if not rewriter_spec else None
    rewriter = QuestionRewriter(
        name, rewrite_model_spec, overwrite=overwrite, client=rewrite_client
    )
    task_model_spec = task_rewriter_spec or rewrite_model_spec
    task_client = rewriter.client if task_model_spec == rewrite_model_spec else None
    task_rewriter = TaskQuestionRewriter(
        name,
        task_model_spec,
        overwrite=overwrite,
        client=task_client,
    )
    model_id = annotators[0].client.model_id
    commit = git_commit()
    run_config = json.dumps(
        {
            "judge_spec": judge_spec,
            "transcriber_spec": transcriber.model_spec if transcriber else "",
            "rewriter_spec": rewriter.model_spec,
            "task_rewriter_spec": task_rewriter.model_spec,
            "source_stage": "normalized_selected",
            "focus_filter": modality or "",
            "limit": limit,
            "overwrite": overwrite,
            "annotators": [annotator.name for annotator in annotators],
            "max_tokens": {
                annotator.name: annotator.max_tokens for annotator in annotators
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    print(f"[analysis] {source.name}: {len(records)} rows with {model_id}")
    print(f"[analysis] cache: {cache_path}")

    cache_fh = cache_path.open("w" if overwrite else "a", encoding="utf-8")
    rows: list[dict] = []
    n_new = 0
    n_kept = 0

    for idx, row in enumerate(records, 1):
        rec = dict(row)
        qid = rec["qid"]
        prior = prior_enhanced.get(qid)
        if (
            prior
            and _enhancement_complete(prior)
            and task_rewriter.has_verified_rewrite(
                rec, prior.get(TASK_QUESTION_COLUMN, "")
            )
        ):
            rec[QUESTION_OEQ_COLUMN] = prior.get(QUESTION_OEQ_COLUMN, "")
            rec[ANSWER_OEQ_COLUMN] = prior.get(ANSWER_OEQ_COLUMN, "")
            rec[TRANSCRIPTION_COLUMN] = prior.get(TRANSCRIPTION_COLUMN, "")
            for col in ANALYSIS_COLS:
                rec[col] = prior.get(col, "")
            for col in TASK_REWRITE_COLUMNS:
                rec[col] = prior.get(col, "")
            n_kept += 1
        else:
            result = {
                "qid": qid,
                **cached.get(qid, {}),
                "enhancement_model": model_id,
                "enhancement_git_commit": commit,
                "enhancement_config": run_config,
            }
            for col in [
                QUESTION_OEQ_COLUMN,
                ANSWER_OEQ_COLUMN,
                TRANSCRIPTION_COLUMN,
                *ANALYSIS_COLS,
                *TASK_REWRITE_COLUMNS,
            ]:
                rec[col] = (
                    prior.get(col, result.get(col, ""))
                    if prior
                    else result.get(col, "")
                )
            missing = [a for a in annotators if _annotator_is_missing(a, rec)]
            needs_oeq = not rec[QUESTION_OEQ_COLUMN] or not rec[ANSWER_OEQ_COLUMN]
            needs_task = not task_rewriter.has_verified_rewrite(
                rec, rec[TASK_QUESTION_COLUMN]
            )
            if (missing or needs_oeq or needs_task) and (
                limit is None or n_new < limit
            ):
                # Dependency order: transcription -> classification -> rewrites.
                # Both classifiers and question rewrites may use speech evidence;
                # OEQ rewriting additionally benefits from the standardized labels.
                # A task-only backfill is independent of the transcript. Avoid
                # requiring an audio-capable client when classification and the
                # OEQ rewrite are already complete.
                needs_transcription = (
                    bool(missing or needs_oeq) and should_transcribe(name, rec)
                )
                if needs_transcription and transcriber is None:
                    cache_fh.close()
                    raise ValueError(
                        f"{judge_spec!r} cannot transcribe audio. Pass --transcriber "
                        "with an audio-capable model before running analysis."
                    )
                if needs_transcription and not rec[TRANSCRIPTION_COLUMN]:
                    rec[TRANSCRIPTION_COLUMN] = transcriber.transcribe(rec)
                for annotator in missing:
                    inferred = annotator.annotate(rec)
                    for col, value in inferred.items():
                        # One structured call produces a coherent annotation set.
                        # If that call is needed, do not mix its new fields with
                        # stale values from an older schema/prompt cache.
                        result[col] = value
                        rec[col] = value
                if needs_oeq:
                    rec.update(rewriter.rewrite(rec))
                if needs_task:
                    rec.update(task_rewriter.rewrite(rec))
                result.update({
                    col: rec.get(col, "")
                    for col in [
                        QUESTION_OEQ_COLUMN,
                        ANSWER_OEQ_COLUMN,
                        TRANSCRIPTION_COLUMN,
                        *ANALYSIS_COLS,
                        *TASK_REWRITE_COLUMNS,
                    ]
                })
                cached[qid] = result
                cache_fh.write(json.dumps(result, ensure_ascii=False) + "\n")
                cache_fh.flush()
                n_new += 1
                print(f"  [{idx}/{len(records)}] {qid} "
                      f"{result.get('question_nature','?'):<11} "
                      f"{result.get('piec','?'):<11} "
                      f"action_content={result.get('action_content', '')}")

            rec.update({
                col: result.get(col, rec.get(col, ""))
                for col in [
                    QUESTION_OEQ_COLUMN,
                    ANSWER_OEQ_COLUMN,
                    TRANSCRIPTION_COLUMN,
                    *ANALYSIS_COLS,
                    *TASK_REWRITE_COLUMNS,
                ]
            })
        rows.append(rec)

    cache_fh.close()
    if transcriber is not None:
        transcriber.close()
    rewriter.close()
    task_rewriter.close()

    source_cols = [
        column for column in source_cols
        if column not in {
            *ANALYSIS_COLS, TRANSCRIPTION_COLUMN, QUESTION_OEQ_COLUMN,
            ANSWER_OEQ_COLUMN, *TASK_REWRITE_COLUMNS,
        }
    ]
    question_index = source_cols.index("question") + 1
    source_cols.insert(question_index, QUESTION_OEQ_COLUMN)
    source_cols.insert(question_index + 1, TASK_QUESTION_COLUMN)
    source_cols.insert(source_cols.index("answer") + 1, ANSWER_OEQ_COLUMN)
    ordered = [
        *source_cols,
        TRANSCRIPTION_COLUMN,
        *ANALYSIS_COLS,
    ]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=ordered, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. Wrote {out_path}")
    print(f"New enhancements: {n_new}; preserved enhanced rows: {n_kept}")
    print("PIEC:", dict(Counter(row.get("piec", "") for row in rows if row.get("piec"))))
    print("Question nature:", dict(Counter(
        row.get("question_nature", "") for row in rows if row.get("question_nature")
    )))
    return out_path

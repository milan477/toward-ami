"""AI rewriting of benchmark questions into maximally open-ended questions."""

from __future__ import annotations

import json
import csv
from pathlib import Path

from download.common import bench_dir, bench_path
from src.config import ANALYSIS_COLS
from src.analysis.transcribe import TRANSCRIPTION_COLUMN
from src.analysis.task_rewrite import (
    TASK_QUESTION_COLUMN,
    TASK_REWRITE_COLUMNS,
)
from src.analysis.dimensions import creator_context
from src.helpers.answer_parsers import extract_json_object
from src.helpers.results import git_commit
from src.analysis.prompts import build_rewrite_prompt


QUESTION_OEQ_COLUMN = "question_oeq"
ANSWER_OEQ_COLUMN = "answer_oeq"


def rewrite_path(name: str) -> Path:
    return bench_dir(name) / f".{name}.normalized_selected.question_oeq.jsonl"


def load_rewrites(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["qid"]] = record
    return records


class QuestionRewriter:
    """Rewrite and cache questions with full prompt/model provenance."""

    def __init__(
        self, name: str, model_spec: str, *, overwrite: bool = False, client=None
    ):
        self.name = name
        self.model_spec = model_spec
        if client is None:
            from models.client import make_client
            client = make_client(model_spec)
        self.client = client
        self.path = rewrite_path(name)
        self.records = {} if overwrite else load_rewrites(self.path)
        self.handle = self.path.open("w" if overwrite else "a", encoding="utf-8")

    def close(self) -> None:
        self.handle.close()

    def rewrite(self, row: dict) -> dict:
        qid = row["qid"]
        prior = self.records.get(qid)
        if prior is not None and prior.get(ANSWER_OEQ_COLUMN):
            return {
                QUESTION_OEQ_COLUMN: str(prior.get(QUESTION_OEQ_COLUMN, "")),
                ANSWER_OEQ_COLUMN: str(prior.get(ANSWER_OEQ_COLUMN, "")),
            }
        prompt = build_rewrite_prompt(row)
        raw = self.client.generate(prompt, max_tokens=300)
        value = extract_json_object(raw).get(QUESTION_OEQ_COLUMN, "")
        question_oeq = " ".join(str(value).split())
        answer_value = extract_json_object(raw).get(ANSWER_OEQ_COLUMN, [])
        if isinstance(answer_value, str):
            answer_value = [answer_value]
        answer_oeq = [" ".join(str(item).split()) for item in answer_value if str(item).strip()]
        if not question_oeq or not answer_oeq:
            raise ValueError(f"Question rewriter returned an incomplete OEQ pair for {qid}")
        record = {
            "qid": qid,
            QUESTION_OEQ_COLUMN: question_oeq,
            ANSWER_OEQ_COLUMN: json.dumps(answer_oeq, ensure_ascii=False),
            "rewrite_model": self.client.model_id,
            "rewrite_model_spec": self.model_spec,
            "rewrite_git_commit": git_commit(),
            "rewrite_prompt": prompt,
            "rewrite_raw_response": raw.strip(),
        }
        self.records[qid] = record
        self.handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.handle.flush()
        return {
            QUESTION_OEQ_COLUMN: question_oeq,
            ANSWER_OEQ_COLUMN: record[ANSWER_OEQ_COLUMN],
        }


def rewrite_enhanced_questions(
    name: str, model_spec: str, limit: int | None = None, *, overwrite: bool = False
) -> Path:
    """Backfill question_oeq while preserving every existing enhanced field."""
    source = bench_path(name, "selected")
    output = bench_path(name, "enhanced")
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        source_columns = reader.fieldnames or []
        source_rows = list(reader)
    prior: dict[str, dict] = {}
    if output.exists():
        with output.open(newline="", encoding="utf-8-sig") as handle:
            prior = {row["qid"]: row for row in csv.DictReader(handle)}

    rewriter = QuestionRewriter(name, model_spec, overwrite=overwrite)
    rows: list[dict] = []
    new = 0
    for row in source_rows:
        rec = dict(row)
        old = prior.get(rec["qid"], {})
        rec[TRANSCRIPTION_COLUMN] = old.get(TRANSCRIPTION_COLUMN, "")
        for column in ANALYSIS_COLS:
            rec[column] = old.get(column, "")
        rec[QUESTION_OEQ_COLUMN] = "" if overwrite else old.get(QUESTION_OEQ_COLUMN, "")
        rec[ANSWER_OEQ_COLUMN] = "" if overwrite else old.get(ANSWER_OEQ_COLUMN, "")
        for column in TASK_REWRITE_COLUMNS:
            rec[column] = old.get(column, "")
        if (not rec[QUESTION_OEQ_COLUMN] or not rec[ANSWER_OEQ_COLUMN]) and (
            limit is None or new < limit
        ):
            rec.update(rewriter.rewrite(rec))
            new += 1
            print(f"  [{new}] {rec['qid']} {rec[QUESTION_OEQ_COLUMN]}")
        rows.append(rec)
    rewriter.close()

    columns = [
        column for column in source_columns
        if column not in {QUESTION_OEQ_COLUMN, *TASK_REWRITE_COLUMNS}
    ]
    columns.insert(columns.index("question") + 1, QUESTION_OEQ_COLUMN)
    columns.insert(columns.index(QUESTION_OEQ_COLUMN) + 1, TASK_QUESTION_COLUMN)
    columns.insert(columns.index("answer") + 1, ANSWER_OEQ_COLUMN)
    columns.extend([
        TRANSCRIPTION_COLUMN,
        *ANALYSIS_COLS,
    ])
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Done. Added {new} OEQ rewrites to {output}")
    return output

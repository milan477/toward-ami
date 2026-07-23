"""Analysis-time conversion of questions into meaning-preserving imperative tasks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from download.common import bench_dir
from src.helpers.answer_parsers import extract_json_object
from src.helpers.results import git_commit
from src.querying.common import model_slug
from src.analysis.prompts import (
    TASK_REWRITE_PROMPT,
    TASK_REWRITE_VERIFICATION_PROMPT,
)


TASK_QUESTION_COLUMN = "question_task"
TASK_REWRITE_PROVENANCE_COLUMNS = [
    "task_rewrite_model",
    "task_rewrite_model_spec",
    "task_rewrite_model_info",
    "task_rewrite_git_commit",
    "task_rewrite_equivalent",
    "task_rewrite_imperative",
    "task_rewrite_answer_preserved",
    "task_rewrite_rationale",
    "task_rewrite_prompt",
    "task_rewrite_raw",
    "task_verification_prompt",
    "task_verification_raw",
]
# Only the rewritten question belongs in the enhanced benchmark CSV. Full model,
# prompt, response, and verification provenance remains in the JSONL sidecar.
TASK_REWRITE_COLUMNS = [TASK_QUESTION_COLUMN]
MAX_REWRITE_ATTEMPTS = 3


def task_rewrite_path(benchmark: str, model_spec: str) -> Path:
    slug = model_slug(model_spec)
    fingerprint = hashlib.sha256(model_spec.encode("utf-8")).hexdigest()[:10]
    return bench_dir(benchmark) / (
        f".{benchmark}.normalized_selected.question_task.{slug}.{fingerprint}.jsonl"
    )


def _load(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["qid"]] = record
    return records


def _normalized_json_list(value) -> str:
    """Represent normalized answer fields consistently in verification prompts."""
    if isinstance(value, list):
        values = value
    else:
        raw = str(value or "").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        values = parsed if isinstance(parsed, list) else [parsed]
    cleaned = [" ".join(str(item).split()) for item in values if str(item).strip()]
    return json.dumps(cleaned, ensure_ascii=False)


class TaskQuestionRewriter:
    """Rewrite, verify, and cache imperative question formulations."""

    def __init__(
        self,
        benchmark: str,
        model_spec: str,
        *,
        client=None,
        cache_path: Path | None = None,
        overwrite: bool = False,
    ):
        if client is None:
            from models.client import make_client

            client = make_client(model_spec)
        self.benchmark = benchmark
        self.model_spec = model_spec
        self.client = client
        self.path = cache_path or task_rewrite_path(benchmark, model_spec)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records = {} if overwrite else _load(self.path)
        self.handle = self.path.open("w" if overwrite else "a", encoding="utf-8")

    def close(self) -> None:
        self.handle.close()

    def has_verified_rewrite(self, row: dict, rewritten: str | None = None) -> bool:
        """Return whether the sidecar proves this exact row has a valid rewrite."""
        qid = str(row["qid"])
        question = " ".join(str(row.get("question", "")).split())
        answer = _normalized_json_list(row.get("answer", ""))
        distractors = _normalized_json_list(row.get("distractors", ""))
        prior = self.records.get(qid)
        cached_task = " ".join(
            str((prior or {}).get(TASK_QUESTION_COLUMN, "")).split()
        )
        expected_task = None if rewritten is None else " ".join(str(rewritten).split())
        return bool(
            prior
            and prior.get("original_question") == question
            and cached_task
            and (expected_task is None or cached_task == expected_task)
            and prior.get("task_rewrite_equivalent") is True
            and prior.get("task_rewrite_imperative") is True
            and prior.get("task_rewrite_answer_preserved") is True
            and prior.get("verification_answer") == answer
            and prior.get("verification_distractors") == distractors
        )

    def rewrite(self, row: dict) -> dict:
        qid = str(row["qid"])
        question = " ".join(str(row.get("question", "")).split())
        answer = _normalized_json_list(row.get("answer", ""))
        distractors = _normalized_json_list(row.get("distractors", ""))
        prior = self.records.get(qid)
        if self.has_verified_rewrite(row):
            return self._row_values(prior)

        feedback = ""
        attempts = []
        for attempt in range(1, MAX_REWRITE_ATTEMPTS + 1):
            rewrite_prompt = TASK_REWRITE_PROMPT.format(
                question=question,
                feedback=(f"Previous verification feedback: {feedback}" if feedback else ""),
            )
            rewrite_raw = self.client.generate(rewrite_prompt, max_tokens=220)
            rewritten = " ".join(
                str(extract_json_object(rewrite_raw).get("rewritten_question", "")).split()
            )
            if not rewritten or rewritten.casefold() == question.casefold():
                feedback = "The rewrite was empty or did not substantially reformulate the question."
                attempts.append({"rewrite_prompt": rewrite_prompt, "rewrite_raw": rewrite_raw})
                continue

            verification_prompt = TASK_REWRITE_VERIFICATION_PROMPT.format(
                question=question,
                rewritten=rewritten,
                answer=answer,
                distractors=distractors,
            )
            verification_raw = self.client.generate(verification_prompt, max_tokens=160)
            verification = extract_json_object(verification_raw)
            equivalent = verification.get("equivalent") is True
            imperative = verification.get("imperative") is True
            answer_preserved = verification.get("answer_preserved") is True
            rationale = " ".join(str(verification.get("rationale", "")).split())
            attempts.append(
                {
                    "rewrite_prompt": rewrite_prompt,
                    "rewrite_raw": rewrite_raw,
                    "rewritten_question": rewritten,
                    "verification_prompt": verification_prompt,
                    "verification_raw": verification_raw,
                    "equivalent": equivalent,
                    "imperative": imperative,
                    "answer_preserved": answer_preserved,
                    "rationale": rationale,
                }
            )
            if equivalent and imperative and answer_preserved:
                record = {
                    "qid": qid,
                    "original_question": question,
                    "verification_answer": answer,
                    "verification_distractors": distractors,
                    TASK_QUESTION_COLUMN: rewritten,
                    "task_rewrite_equivalent": True,
                    "task_rewrite_imperative": True,
                    "task_rewrite_answer_preserved": True,
                    "task_rewrite_rationale": rationale,
                    "task_rewrite_model": self.client.model_id,
                    "task_rewrite_model_spec": self.model_spec,
                    "task_rewrite_model_info": self.client.info(),
                    "task_rewrite_git_commit": git_commit(),
                    "task_rewrite_attempts": attempts,
                }
                self.records[qid] = record
                self.handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                self.handle.flush()
                return self._row_values(record)
            feedback = rationale or (
                "The rewrite did not preserve the exact meaning and desired answer "
                "while expressing the question as an imperative task."
            )

        raise ValueError(
            f"Could not produce a verified meaning-preserving task rewrite for {qid}: "
            f"{feedback}"
        )

    @staticmethod
    def _row_values(record: dict) -> dict:
        return {TASK_QUESTION_COLUMN: record.get(TASK_QUESTION_COLUMN, "")}

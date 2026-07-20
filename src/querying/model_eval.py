"""Model-query helpers for MCQ/OEQ benchmark evaluation."""

from __future__ import annotations

import json
import time
from pathlib import Path

from src.config import API_RETRIES, MCQ_MAX_TOKENS, OEQ_MAX_TOKENS
from src.evaluation.prompts import build_mcq, build_oeq, extract_letter, parse_distractors
from src.querying.common import audio_name, audio_stem, read_jsonl


def generate_with_retries(client, prompt: str, audio: Path, max_tokens: int) -> tuple[str, str | None]:
    """One model call with a few retries for transient errors."""
    last = None
    for attempt in range(API_RETRIES):
        try:
            return client.generate(prompt, str(audio), max_tokens=max_tokens), None
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            resp = getattr(exc, "response", None)
            if resp is not None:
                body = (getattr(resp, "text", None) or "")[:200]
                detail = f"{detail} | {body}" if body else detail
            last = detail[:400]
            time.sleep(min(2 ** attempt, 8))
    return "", last


def _needs_query(rec: dict | None) -> bool:
    """True if this qid is missing or only has a failed/error attempt."""
    if not rec:
        return True
    if rec.get("skipped"):
        return False
    return bool(rec.get("error")) or not (rec.get("response") or "").strip()


def _rewrite_jsonl(path: Path, records: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records.values():
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def query_answers(df, audio_index: dict[str, Path], client, cache: Path, form: str) -> dict[str, dict]:
    """Query ``client`` for all uncached (or previously failed) rows in MCQ/OEQ form."""
    done = read_jsonl(cache)
    todo = [row for _, row in df.iterrows() if _needs_query(done.get(audio_stem(row["audio_url"])))]
    if not todo:
        print(f"[{form}] all {len(done)} answers present; skipping.")
        return done

    n_ok = sum(1 for r in done.values() if not _needs_query(r))
    print(f"[{form}] {client.model_id}: {len(todo)} to answer ({n_ok} ok cached)")
    for i, row in enumerate(todo, 1):
        qid = audio_stem(row["audio_url"])
        audio = audio_index.get(audio_name(row["audio_url"]))
        if audio is None:
            rec = {"qid": qid, "skipped": "no_audio"}
        elif form == "mcq":
            rec = _query_mcq(row, qid, audio, client)
        elif form == "oeq":
            rec = _query_oeq(row, qid, audio, client)
        else:
            raise ValueError(f"Unknown query form {form!r}; expected 'mcq' or 'oeq'.")

        done[qid] = rec
        _rewrite_jsonl(cache, done)
        tag = ("ERR" if rec.get("error") else
               (("✓" if rec.get("correct") else "✗") if form == "mcq" else "OK"))
        preview = (rec.get("response") or rec.get("skipped") or rec.get("error") or "")[:60]
        print(f"  [{i}/{len(todo)}] {qid[:24]:<24} {tag} {preview!r}")
    return done


def _query_mcq(row, qid: str, audio: Path, client) -> dict:
    distractors = parse_distractors(row["distractors"])
    mcq = build_mcq(row["question"], row["correct_answer"], distractors, qid)
    response, error = generate_with_retries(client, mcq["prompt"], audio, MCQ_MAX_TOKENS)
    pred = extract_letter(response, mcq["letter_map"]) if not error else None
    return {
        "qid": qid,
        "question": row["question"],
        "audio": audio.name,
        "category": row.get("category", ""),
        "skills": row.get("skills", ""),
        "category_1": row["category_1"],
        "category_2": row["category_2"],
        "category_3": row["category_3"],
        "category_4": row.get("category_4", ""),
        "prompt": mcq["prompt"],
        "correct_answer": mcq["correct_answer"],
        "correct_letter": mcq["correct_letter"],
        "response": response,
        "pred_letter": pred,
        "pred_answer": mcq["letter_map"].get(pred) if pred else None,
        "correct": (pred == mcq["correct_letter"]) if pred else False,
        "error": error,
    }


def _query_oeq(row, qid: str, audio: Path, client) -> dict:
    oeq = build_oeq(
        row["question"],
        row["correct_answer"],
        answer_format=row.get("answer_format", ""),
        example=row.get("example_answer", ""),
    )
    response, error = generate_with_retries(client, oeq["prompt"], audio, OEQ_MAX_TOKENS)
    return {
        "qid": qid,
        "question": row["question"],
        "audio": audio.name,
        "category": row.get("category", ""),
        "skills": row.get("skills", ""),
        "category_1": row["category_1"],
        "category_2": row["category_2"],
        "category_3": row["category_3"],
        "category_4": row.get("category_4", ""),
        "answer_format": row.get("answer_format", ""),
        "example_answer": row.get("example_answer", ""),
        "prompt": oeq["prompt"],
        "reference_answer": row["correct_answer"],
        "response": response,
        "error": error,
    }

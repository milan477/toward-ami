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
    for _ in range(API_RETRIES):
        try:
            return client.generate(prompt, str(audio), max_tokens=max_tokens), None
        except Exception as exc:  # noqa: BLE001
            last = str(exc)[:300]
            time.sleep(0)
    return "", last


def query_answers(df, audio_index: dict[str, Path], client, cache: Path, form: str) -> dict[str, dict]:
    """Query ``client`` for all uncached rows in MCQ or OEQ form."""
    done = read_jsonl(cache)
    todo = [row for _, row in df.iterrows() if audio_stem(row["audio_url"]) not in done]
    if not todo:
        print(f"[{form}] all {len(done)} answers present; skipping.")
        return done

    print(f"[{form}] {client.model_id}: {len(todo)} to answer ({len(done)} cached)")
    fh = cache.open("a", encoding="utf-8")
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
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        tag = ("ERR" if rec.get("error") else
               (("✓" if rec.get("correct") else "✗") if form == "mcq" else "OK"))
        print(f"  [{i}/{len(todo)}] {qid[:24]:<24} {tag} "
              f"{(rec.get('response') or rec.get('skipped') or '')[:44]!r}")
    fh.close()
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

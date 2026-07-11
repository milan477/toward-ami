"""Evaluation passes over cached model answers."""

from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.judge import PIACJudge
from src.querying.common import read_jsonl


def judge_piac_answers(answers: dict[str, dict], cache: Path) -> dict[str, dict]:
    """Judge OEQ answers with the PIAC-aware rubric."""
    done = read_jsonl(cache)
    todo = [qid for qid, answer in answers.items()
            if qid not in done and not answer.get("skipped")]
    if not todo:
        print(f"[judge] all judged ({len(done)}); skipping.")
        return done

    judge = PIACJudge()
    print(f"[judge] PIAC judging with {judge.model_id}: {len(todo)} answers")
    fh = cache.open("a", encoding="utf-8")
    for i, qid in enumerate(todo, 1):
        answer = answers[qid]
        verdict = judge.score(
            answer.get("category", ""),
            answer["question"],
            answer["reference_answer"],
            answer.get("response", ""),
            answer.get("answer_format", ""),
        )
        rec = {"qid": qid, **verdict}
        done[qid] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        h = "HALL" if verdict["hallucinated"] else "    "
        print(f"  [{i}/{len(todo)}] {qid[:22]:<22} {answer.get('category','?'):<11} "
              f"score={verdict['score']} {h} {verdict['hallucination_level']}")
    fh.close()
    return done


def judge_probe_answers(answers: dict[str, dict], cache: Path) -> dict[str, dict]:
    """Judge decomposed probe answers with each probe's PIAC level."""
    done = read_jsonl(cache, key="key")
    todo = [key for key, answer in answers.items()
            if key not in done and not answer.get("skipped")]
    if not todo:
        print(f"[probe-judge] all judged ({len(done)} present); skipping.")
        return done

    judge = PIACJudge()
    print(f"[probe-judge] PIAC judging {len(todo)} probe answers with {judge.model_id}")
    fh = cache.open("a", encoding="utf-8")
    for i, key in enumerate(todo, 1):
        answer = answers[key]
        verdict = judge.score(
            answer.get("level", ""),
            answer["probe_question"],
            answer.get("expected", ""),
            answer.get("response", ""),
        )
        rec = {"key": key, **verdict}
        done[key] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        h = "HALL" if verdict["hallucinated"] else "    "
        print(f"  [{i}/{len(todo)}] {key:<32} {answer.get('level',''):<11} "
              f"score={verdict['score']} norm={verdict['score_norm']} {h}")
    fh.close()
    return done


def merge_oeq_records(df, answers: dict[str, dict], judged: dict[str, dict],
                      qid_for_row) -> list[dict]:
    records = []
    for _, row in df.iterrows():
        qid = qid_for_row(row)
        answer = answers.get(qid, {"qid": qid})
        verdict = judged.get(qid, {})
        records.append({
            **answer,
            "judge_score": verdict.get("score"),
            "judge_score_norm": verdict.get("score_norm"),
            "verdict": verdict.get("verdict"),
            "grounded": verdict.get("grounded"),
            "hallucinated": verdict.get("hallucinated"),
            "hallucination_level": verdict.get("hallucination_level"),
            "judge_rationale": verdict.get("rationale"),
        })
    return records


def merge_probe_records(probe_units: list[dict], answers: dict[str, dict],
                        judged: dict[str, dict]) -> list[dict]:
    records = []
    for unit in probe_units:
        answer = answers.get(unit["key"], {})
        verdict = judged.get(unit["key"], {})
        records.append({
            "qid": unit["qid"],
            "probe_idx": unit["probe_idx"],
            "level": unit["level"],
            "target_category": unit.get("category", ""),
            "question": unit.get("question", ""),
            "probe_question": unit["probe_question"],
            "expected": unit["expected"],
            "response": (answer.get("response") or "").replace("\n", " ").strip(),
            "judge_score": verdict.get("score"),
            "judge_score_norm": verdict.get("score_norm"),
            "verdict": verdict.get("verdict"),
            "hallucinated": verdict.get("hallucinated"),
            "skipped": answer.get("skipped"),
            "error": answer.get("error"),
        })
    return records

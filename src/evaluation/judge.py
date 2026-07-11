"""LLM-as-judge utilities.

This module contains both the generic 0-4 correctness judge and the PIAC-aware
category-specific judge with hallucination detection.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.analysis.taxonomy import CATEGORIES, eval_strategy
from src.config import DEFAULT_JUDGE_SPEC, PIAC_JUDGE_MAX_TOKENS
from .prompts import PIAC_JUDGE_PROMPT, STRATEGY_RUBRIC

SCALE = [
    "fully incorrect",
    "mostly incorrect",
    "neither correct nor incorrect",
    "mostly correct",
    "fully correct",
]
MIN_SCORE, MAX_SCORE = 0, len(SCALE) - 1
_RUBRIC = "\n".join(f"    {i} - {label}" for i, label in enumerate(SCALE))

JUDGE_TEMPLATE = f"""You are a strict, fair grader. Compare a model's answer to a \
reference (ground-truth) answer for the same question and rate how correct the \
model's answer is on this 0-4 scale:

{_RUBRIC}

Judge meaning, not wording: an answer that conveys the reference's content in \
different words is fully correct; 0 for answers that are wrong, empty, or off-topic.

Grading rules (apply strictly):
- A single number or single discrete value (a count, a note, yes/no, one name) is either \
right or wrong: 4 if it matches, 0 if not. NEVER partial credit for a close-but-wrong value \
(e.g. 20 when the reference is 26 scores 0).
- Ignore extra information: an answer that includes everything the reference requires PLUS \
extra details is still fully correct (4).
- The middle scores apply ONLY to a multi-part reference where the answer is incomplete \
(some required parts present, others missing), never to a single value that is merely close.

Question: {{question}}
Reference answer (ground truth): {{reference}}
Model's answer: {{answer}}

Reply with ONLY a JSON object and nothing else:
{{{{"score": <integer 0-4>, "rationale": "<one short sentence>"}}}}"""

PIAC_SCORE_MAX = 4

_LEVELS = set(CATEGORIES) | {"none"}


def build_generic_prompt(question: str, reference: str, answer: str) -> str:
    return JUDGE_TEMPLATE.format(
        question=question.strip(),
        reference=str(reference).strip(),
        answer=str(answer).strip() or "(no answer given)",
    )


def build_prompt(category: str, question: str, reference: str, answer: str,
                 answer_format: str = "") -> str:
    strat = eval_strategy(category) or "graded_affective"
    return PIAC_JUDGE_PROMPT.format(
        category=category or "unclassified",
        rubric=STRATEGY_RUBRIC.get(strat, STRATEGY_RUBRIC["graded_affective"]),
        question=str(question).strip(),
        answer_format=(answer_format or "a short answer").strip(),
        reference=str(reference).strip(),
        answer=str(answer).strip() or "(no answer given)",
    )


def _clamp_int(v, lo, hi):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _clamp_score(v) -> int | None:
    return _clamp_int(v, MIN_SCORE, MAX_SCORE)


def _clamp_float(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def parse_generic_judge(text: str) -> dict:
    """Pull {score, label, rationale} out of a generic judge reply."""
    score, rationale = None, ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            score = _clamp_score(obj.get("score"))
            rationale = str(obj.get("rationale", "")).strip()
        except json.JSONDecodeError:
            pass
    if score is None:
        d = re.search(r"\b([0-4])\b", text)
        score = int(d.group(1)) if d else None
    return {
        "score": score,
        "label": SCALE[score] if score is not None else "unparsed",
        "rationale": rationale or (text.strip()[:200] if score is None else ""),
        "raw": text.strip(),
    }


def parse_judge(text: str) -> dict:
    score = grounded = None
    hallucinated, level, rationale = None, "none", ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            score = _clamp_int(obj.get("score"), 0, PIAC_SCORE_MAX)
            grounded = _clamp_float(obj.get("grounded"))
            hv = obj.get("hallucinated")
            hallucinated = (bool(hv) if isinstance(hv, bool)
                            else str(hv).strip().lower() in ("true", "yes", "1"))
            lv = str(obj.get("hallucination_level", "none")).strip().lower()
            level = lv if lv in _LEVELS else "none"
            rationale = str(obj.get("rationale", "")).strip()[:300]
        except json.JSONDecodeError:
            pass
    if score is None:  # fall back to first standalone 0-4 digit
        d = re.search(r"\b([0-4])\b", text)
        score = int(d.group(1)) if d else None
    if not hallucinated:
        level = "none"
    norm = round(score / PIAC_SCORE_MAX, 4) if score is not None else None
    verdict = ("correct" if norm == 1.0 else
               "incorrect" if norm in (0.0, None) else "partial")
    return {"score": score, "score_norm": norm, "verdict": verdict,
            "grounded": grounded, "hallucinated": bool(hallucinated),
            "hallucination_level": level, "rationale": rationale,
            "raw": text.strip()[:300]}


class Judge:
    """A generic 0-4 correctness judge backed by any model spec."""

    def __init__(self, judge_spec: str = DEFAULT_JUDGE_SPEC, max_tokens: int = 200):
        from models.client import make_client

        self.client = make_client(judge_spec)
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return self.client.model_id

    def score(self, question: str, reference: str, answer: str) -> dict:
        reply = self.client.generate(
            build_generic_prompt(question, reference, answer),
            max_tokens=self.max_tokens,
        )
        return parse_generic_judge(reply)


class PIACJudge:
    """Category-aware 0-4 judge + hallucination flag, backed by local Qwen3."""

    def __init__(self, judge_spec: str = DEFAULT_JUDGE_SPEC, max_tokens: int = PIAC_JUDGE_MAX_TOKENS):
        from models.client import make_client

        self.client = make_client(judge_spec)
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return self.client.model_id

    def score(self, category: str, question: str, reference: str, answer: str,
              answer_format: str = "") -> dict:
        prompt = build_prompt(category, question, reference, answer, answer_format)
        reply = self.client.generate(prompt, max_tokens=self.max_tokens)
        out = parse_judge(reply)
        out["category"] = category
        out["eval_strategy"] = eval_strategy(category)
        return out


def _score_run(judge: Judge, run_dir: Path, limit: int | None) -> Path:
    results = sorted(run_dir.glob("results_*.json"))
    if not results:
        raise SystemExit(f"No results_*.json in {run_dir}.")
    payload = json.loads(results[0].read_text())
    items = payload["items"]
    if limit:
        items = items[:limit]

    print(f"Judge: {judge.model_id}  |  scoring {len(items)} OEQ answers (0-4)")
    scores = []
    for it in items:
        oeq = it.get("oeq")
        if not oeq:
            continue
        verdict = judge.score(it["question"], oeq["reference_answer"], oeq["response"])
        oeq["judge_0_4"] = verdict
        if verdict["score"] is not None:
            scores.append(verdict["score"])
        print(f"  [{it.get('qid', '?')}] score={verdict['score']} "
              f"({verdict['label']}) - {verdict['rationale'][:70]}")

    payload["judge_model"] = judge.model_id
    payload["judge_scale"] = {str(i): label for i, label in enumerate(SCALE)}
    payload["items"] = items
    slug = judge.model_id.replace("/", "_").replace(":", "_")
    out = run_dir / f"judged_0_4_{slug}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    mean = sum(scores) / len(scores) if scores else float("nan")
    print(f"\nMean score: {mean:.2f} / {MAX_SCORE}  (n={len(scores)})")
    print(f"Saved {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", default=DEFAULT_JUDGE_SPEC)
    parser.add_argument("--run", default=None, help="Score an OEQ run directory with the generic judge.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--category", default=None, help="Use PIAC judge when provided.")
    parser.add_argument("--question")
    parser.add_argument("--reference")
    parser.add_argument("--answer")
    parser.add_argument("--answer-format", default="")
    args = parser.parse_args()

    if args.run:
        _score_run(Judge(args.judge), Path(args.run), args.limit)
    elif args.category and args.question and args.reference is not None and args.answer is not None:
        judge = PIACJudge(args.judge)
        print(json.dumps(
            judge.score(args.category, args.question, args.reference, args.answer, args.answer_format),
            indent=2,
            ensure_ascii=False,
        ))
    elif args.question and args.reference is not None and args.answer is not None:
        judge = Judge(args.judge)
        print(json.dumps(judge.score(args.question, args.reference, args.answer),
                         indent=2, ensure_ascii=False))
    else:
        parser.error("give --run, or --question/--reference/--answer; add --category for PIAC judging.")


if __name__ == "__main__":
    main()

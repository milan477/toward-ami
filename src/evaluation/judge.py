"""Binary PIEC-aware LLM-as-judge utilities."""

from __future__ import annotations

import argparse
import json
import re

from src.analysis.taxonomy import eval_strategy
from src.config import DEFAULT_JUDGE_SPEC, PIEC_JUDGE_MAX_TOKENS
from .prompts import PIEC_JUDGE_PROMPT, STRATEGY_RUBRIC

PIEC_JUDGE_SCHEMA = "piec-binary-confidence-v1"
CONFIDENCE_LEVELS = {"low", "mid", "high"}


def build_prompt(
    category: str,
    question: str,
    reference: str,
    answer: str,
    answer_format: str = "",
    context: dict | None = None,
) -> str:
    context = context or {}
    strat = eval_strategy(category) or "graded_experiential"
    return PIEC_JUDGE_PROMPT.format(
        category=category or "unclassified",
        rubric=STRATEGY_RUBRIC.get(strat, STRATEGY_RUBRIC["graded_experiential"]),
        question=str(question).strip(),
        original_question=str(context.get("original_question", question)).strip(),
        answer_format=(answer_format or "a short answer").strip(),
        reference=str(reference).strip(),
        original_answer=str(
            context.get("correct_answer", context.get("original_answer", reference))
        ).strip(),
        question_nature=str(context.get("question_nature", "")).strip(),
        action_content=str(context.get("action_content", "")).strip(),
        creator_categories=str(context.get("creator_categories", "")).strip(),
        distractors=str(context.get("distractors", "")).strip(),
        transcription=str(context.get("transcription", "")).strip(),
        answer=str(answer).strip() or "(no answer given)",
    )




def parse_judge(text: str) -> dict:
    """Parse only the binary PIEC contract; never coerce intermediate scores."""
    score, confidence, rationale = None, "", ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            raw_score = obj.get("score")
            if raw_score in (0, 1, "0", "1"):
                score = int(raw_score)
            candidate = str(obj.get("confidence", "")).strip().lower()
            confidence = candidate if candidate in CONFIDENCE_LEVELS else ""
            rationale = str(obj.get("rationale", "")).strip()[:300]
        except json.JSONDecodeError:
            pass
    if score is None:
        d = re.search(r"\b([01])\b", text)
        score = int(d.group(1)) if d else None
    return {
        "score": score,
        "score_norm": score,
        "verdict": "correct" if score == 1 else "incorrect",
        "confidence": confidence or None,
        "rationale": rationale,
        "raw": text.strip()[:300],
        "judge_schema": PIEC_JUDGE_SCHEMA,
    }


class PIECJudge:
    """Category-aware binary judge with low/mid/high confidence."""

    def __init__(self, judge_spec: str = DEFAULT_JUDGE_SPEC, max_tokens: int = PIEC_JUDGE_MAX_TOKENS):
        from models.client import make_client

        self.client = make_client(judge_spec)
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return self.client.model_id

    def score(
        self,
        category: str,
        question: str,
        reference: str,
        answer: str,
        answer_format: str = "",
        *,
        context: dict | None = None,
    ) -> dict:
        prompt = build_prompt(
            category, question, reference, answer, answer_format, context
        )
        reply = ""
        out = {}
        for attempt in range(2):
            reply = self.client.generate(prompt, max_tokens=self.max_tokens)
            out = parse_judge(reply)
            if out["score"] in (0, 1) and out["confidence"] in CONFIDENCE_LEVELS:
                break
            prompt += (
                "\n\nYour previous response did not satisfy the required schema. "
                "Return score 0 or 1 and confidence low, mid, or high."
            )
        if out.get("score") not in (0, 1) or out.get("confidence") not in CONFIDENCE_LEVELS:
            raise ValueError(f"PIEC judge returned an invalid result: {reply[:300]}")
        out["category"] = category
        out["eval_strategy"] = eval_strategy(category)
        return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", default=DEFAULT_JUDGE_SPEC)
    parser.add_argument("--category", required=True, help="PIEC category.")
    parser.add_argument("--question")
    parser.add_argument("--reference")
    parser.add_argument("--answer")
    parser.add_argument("--answer-format", default="")
    args = parser.parse_args()

    if args.question and args.reference is not None and args.answer is not None:
        judge = PIECJudge(args.judge)
        print(json.dumps(
            judge.score(args.category, args.question, args.reference, args.answer, args.answer_format),
            indent=2,
            ensure_ascii=False,
        ))
    else:
        parser.error("give --category, --question, --reference, and --answer.")


if __name__ == "__main__":
    main()

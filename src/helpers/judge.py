"""LLM-as-judge on a 0–4 correctness scale, runnable on a local model.

A model's free-text answer is graded against a reference answer on a 5-point
Likert scale:

    0  fully incorrect
    1  mostly incorrect
    2  neither correct nor incorrect
    3  mostly correct
    4  fully correct

By default the judge is a local Qwen model (transformers, runs on this machine),
so grading needs no API key. Any model spec understood by ``make_client`` works
as the judge backend (``local:...`` / ``openai:...`` / ``openrouter:...``).

Python API:
    from src.helpers.judge import Judge
    judge = Judge()                          # local Qwen, loaded on first use
    v = judge.score(question, reference, answer)
    # -> {"score": 3, "label": "mostly correct", "rationale": "...", "raw": "..."}

CLI:
    # grade one ad-hoc answer (handy for sanity-checking the judge)
    python -m src.helpers.judge \
        --question "What instrument leads the melody?" \
        --reference "violin" --answer "a violin plays the main tune"

    # grade an OEQ run directory (results_*.json with reference/answer pairs)
    python -m src.helpers.judge --run results/<experiment>/<ts>
"""

import argparse
import json
import re
from pathlib import Path

from models.client import make_client

# Index = score, value = human label. Single source of truth for the scale.
SCALE = [
    "fully incorrect",
    "mostly incorrect",
    "neither correct nor incorrect",
    "mostly correct",
    "fully correct",
]
MIN_SCORE, MAX_SCORE = 0, len(SCALE) - 1

_RUBRIC = "\n".join(f"    {i} — {label}" for i, label in enumerate(SCALE))

JUDGE_TEMPLATE = f"""You are a strict, fair grader. Compare a model's answer to a \
reference (ground-truth) answer for the same question and rate how correct the \
model's answer is on this 0–4 scale:

{_RUBRIC}

Judge meaning, not wording: an answer that conveys the reference's content in \
different words is fully correct; 0 for answers that are wrong, empty, or off-topic.

Grading rules (apply strictly):
- A single number or single discrete value (a count, a note, yes/no, one name) is either \
right or wrong: 4 if it matches, 0 if not — NEVER partial credit for a close-but-wrong value \
(e.g. 20 when the reference is 26 scores 0).
- Ignore extra information: an answer that includes everything the reference requires PLUS \
extra details is still fully correct (4).
- The middle scores apply ONLY to a multi-part reference where the answer is incomplete \
(some required parts present, others missing) — never to a single value that is merely close.

Question: {{question}}
Reference answer (ground truth): {{reference}}
Model's answer: {{answer}}

Reply with ONLY a JSON object and nothing else:
{{{{"score": <integer 0-4>, "rationale": "<one short sentence>"}}}}"""


def build_prompt(question: str, reference: str, answer: str) -> str:
    return JUDGE_TEMPLATE.format(
        question=question.strip(),
        reference=str(reference).strip(),
        answer=str(answer).strip() or "(no answer given)",
    )


def _clamp_score(v) -> int | None:
    try:
        s = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return max(MIN_SCORE, min(MAX_SCORE, s))


def parse_judge(text: str) -> dict:
    """Pull {score, label, rationale} out of the judge's reply, robustly."""
    score, rationale = None, ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            score = _clamp_score(obj.get("score"))
            rationale = str(obj.get("rationale", "")).strip()
        except json.JSONDecodeError:
            pass
    if score is None:  # fall back to the first standalone 0–4 digit
        d = re.search(r"\b([0-4])\b", text)
        score = int(d.group(1)) if d else None
    return {
        "score": score,
        "label": SCALE[score] if score is not None else "unparsed",
        "rationale": rationale or (text.strip()[:200] if score is None else ""),
        "raw": text.strip(),
    }


class Judge:
    """A 0–4 correctness judge backed by any model spec (default: local Qwen)."""

    def __init__(self, judge_spec: str = "local", max_tokens: int = 200):
        self.client = make_client(judge_spec)
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return self.client.model_id

    def score(self, question: str, reference: str, answer: str) -> dict:
        prompt = build_prompt(question, reference, answer)
        reply = self.client.generate(prompt, max_tokens=self.max_tokens)
        return parse_judge(reply)


# --- CLI ------------------------------------------------------------------

def _score_run(judge: Judge, run_dir: Path, limit: int | None) -> Path:
    results = sorted(run_dir.glob("results_*.json"))
    if not results:
        raise SystemExit(f"No results_*.json in {run_dir}.")
    payload = json.loads(results[0].read_text())
    items = payload["items"]
    if limit:
        items = items[:limit]

    print(f"Judge: {judge.model_id}  |  scoring {len(items)} OEQ answers (0–4)")
    scores = []
    for it in items:
        oeq = it.get("oeq")
        if not oeq:
            continue
        v = judge.score(it["question"], oeq["reference_answer"], oeq["response"])
        oeq["judge_0_4"] = v
        if v["score"] is not None:
            scores.append(v["score"])
        print(f"  [{it.get('qid', '?')}] score={v['score']} ({v['label']}) — {v['rationale'][:70]}")

    payload["judge_model"] = judge.model_id
    payload["judge_scale"] = {str(i): lbl for i, lbl in enumerate(SCALE)}
    payload["items"] = items
    slug = judge.model_id.replace("/", "_").replace(":", "_")
    out = run_dir / f"judged_0_4_{slug}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    mean = sum(scores) / len(scores) if scores else float("nan")
    print(f"\nMean score: {mean:.2f} / {MAX_SCORE}  (n={len(scores)})")
    print(f"Saved {out}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judge", default="local", help="Judge model spec (default: local Qwen).")
    ap.add_argument("--run", default=None, help="Score an OEQ run directory.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--question")
    ap.add_argument("--reference")
    ap.add_argument("--answer")
    args = ap.parse_args()

    judge = Judge(args.judge)
    if args.run:
        _score_run(judge, Path(args.run), args.limit)
    elif args.question and args.reference is not None and args.answer is not None:
        v = judge.score(args.question, args.reference, args.answer)
        print(json.dumps(v, indent=2, ensure_ascii=False))
    else:
        ap.error("give --run <dir>, or --question/--reference/--answer for an ad-hoc grade.")


if __name__ == "__main__":
    main()

"""Step 5: LLM-as-judge scoring of the open-ended (OEQ) answers.

Each OEQ answer is scored against the reference answer using the evaluation
criterion of its level (HEAR/ANALYZE/FEEL/KNOW). The judge returns:
    accuracy  0-1  how well the answer matches the truth / is plausible (FEEL)
    grounding 0-1  how well it ties claims to observable audio features
    verdict   correct | partial | incorrect

Reads a run produced by run.py and writes judged_<model>.json next to it.

Usage:
    python -m experiments.oeq_mcq.judge --run experiments/results/exp_3_oeq_vs_mcq/<ts>
    python -m experiments.oeq_mcq.judge                      # latest run
    python -m experiments.oeq_mcq.judge --judge openrouter:openai/gpt-4o
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from experiments.helpers.models import make_client
from experiments.helpers.results import RESULTS_ROOT

from .taxonomy import LEVELS

EXP_DIR = RESULTS_ROOT / "exp_3_oeq_vs_mcq"

JUDGE_TEMPLATE = """You are grading a model's open-ended answer to a question about an audio clip.

Question level: {level} — {content}
Definition: {definition}
Evaluation criterion: {criterion}

Question: {question}
Reference answer (ground truth): {reference}
Model's answer: {answer}

Score the model's answer. For FEEL questions there is no single right answer, so
judge plausibility and grounding rather than exact correctness.
Reply with ONLY a JSON object:
{{"accuracy": <0-1 float>, "grounding": <0-1 float>, "verdict": "correct|partial|incorrect", "rationale": "<one sentence>"}}"""


def build_judge_prompt(level: str, question: str, reference: str, answer: str) -> str:
    lv = LEVELS[level]
    return JUDGE_TEMPLATE.format(
        level=lv.key, content=lv.content, definition=lv.definition,
        criterion=lv.eval_criterion, question=question,
        reference=reference, answer=answer,
    )


def parse_judge(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"accuracy": None, "grounding": None, "verdict": "unparsed", "rationale": text[:200]}
    try:
        obj = json.loads(m.group())
    except json.JSONDecodeError:
        return {"accuracy": None, "grounding": None, "verdict": "unparsed", "rationale": text[:200]}
    return {
        "accuracy": _num(obj.get("accuracy")),
        "grounding": _num(obj.get("grounding")),
        "verdict": str(obj.get("verdict", "")),
        "rationale": str(obj.get("rationale", "")),
    }


def _num(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def _latest_run() -> Path:
    runs = sorted(p for p in EXP_DIR.glob("*") if p.is_dir())
    if not runs:
        raise SystemExit(f"No runs under {EXP_DIR}. Run run.py first.")
    return runs[-1]


def judge_run(run_dir: Path, judge_spec: str, limit: int | None = None) -> Path:
    results = sorted(run_dir.glob("results_*.json"))
    if not results:
        raise SystemExit(f"No results_*.json in {run_dir}.")
    payload = json.loads(results[0].read_text())
    items = payload["items"]
    if limit:
        items = items[:limit]

    judge = make_client(judge_spec)
    print(f"Judge: {judge.model_id}  |  scoring {len(items)} OEQ answers")

    by_level = defaultdict(lambda: {"acc": [], "ground": []})
    for it in items:
        oeq = it["oeq"]
        prompt = build_judge_prompt(it["level"], it["question"],
                                    oeq["reference_answer"], oeq["response"])
        verdict = parse_judge(judge.generate(prompt, max_tokens=200))
        oeq["judge"] = verdict
        if verdict["accuracy"] is not None:
            by_level[it["level"]]["acc"].append(verdict["accuracy"])
        if verdict["grounding"] is not None:
            by_level[it["level"]]["ground"].append(verdict["grounding"])
        print(f"  [{it['qid']}] {it['level']:<8} acc={verdict['accuracy']} "
              f"ground={verdict['grounding']} ({verdict['verdict']})")

    payload["judge_model"] = judge.model_id
    payload["items"] = items
    out = run_dir / f"judged_{judge.model_id.replace('/', '_').replace(':', '_')}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    print("\nOEQ scores by level (mean):")
    for lvl, d in by_level.items():
        acc = sum(d["acc"]) / len(d["acc"]) if d["acc"] else float("nan")
        gnd = sum(d["ground"]) / len(d["ground"]) if d["ground"] else float("nan")
        print(f"  {lvl:<8} accuracy={acc:.2f}  grounding={gnd:.2f}  (n={len(d['acc'])})")
    print(f"\nSaved {out}")
    print("Next: build the table →  python -m experiments.oeq_mcq.table --run", run_dir)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default=None, help="Run directory (default: latest).")
    ap.add_argument("--judge", default="openai:gpt-4o", help="Judge model spec.")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run_dir = Path(args.run) if args.run else _latest_run()
    judge_run(run_dir, args.judge, limit=args.limit)


if __name__ == "__main__":
    main()

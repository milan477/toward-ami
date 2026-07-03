"""
Exp 1: LLM-only baseline.
Query the model with benchmark questions but NO audio, to establish
how much a text-only model can score — the floor that audio adds value over.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "helpers"))    # src/helpers → results
sys.path.insert(0, str(Path(__file__).parent.parent / "analysis"))   # src/analysis → catalog
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "models"))  # models → api

from api import get_model_info, model_slug, query_text_only
from results import get_run_metadata, save_results
from catalog import load_all, load_items

CONFIG = {
    "benchmarks": "all",   # or list of benchmark names
    "n_questions_per_benchmark": None,  # sample size per benchmark (None = all)
    "prompt_template": (
        "Answer the following music question. "
        "You do not have access to any audio.\n\n{question}"
    ),
}


def _load_questions(benchmark_name: str) -> list[dict]:
    """Return a list of dicts with keys: question, choices (optional), answer."""
    items = load_items(benchmark_name)
    if not items:
        raise NotImplementedError(
            f"No normalized data for {benchmark_name!r}. "
            f"Run:  python download/run.py {benchmark_name.lower()}"
        )
    return items


def preview() -> None:
    benchmarks = load_all()
    print(f"Will run LLM-only baseline on {len(benchmarks)} benchmarks")
    for b in benchmarks:
        n = (b.get('coverage') or {}).get('n_items', '?')
        print(f"  - {b['name']} ({n} items)")


def run() -> None:
    model_info = get_model_info()
    metadata = get_run_metadata("exp_1_llm_baseline", model_info["model_id"], CONFIG)

    benchmarks = load_all()
    all_items = []
    summary: dict[str, dict] = {}

    for b in benchmarks:
        name = b["name"]
        try:
            questions = _load_questions(name)
        except NotImplementedError as e:
            print(f"Skipping {name}: {e}")
            continue

        n = CONFIG["n_questions_per_benchmark"]
        if n:
            questions = questions[:n]

        question_format = b.get("question_format") or []
        correct = 0
        for q in questions:
            prompt = CONFIG["prompt_template"].format(question=q["question"])
            response = query_text_only(prompt)
            is_correct = response.strip().lower() == str(q["answer"]).strip().lower()
            correct += int(is_correct)
            all_items.append({
                "benchmark": name,
                "question_format": question_format,
                "question": q["question"],
                "choices": q.get("choices"),
                "expected": q["answer"],
                "response": response,
                "correct": is_correct,
            })

        acc = correct / len(questions) if questions else 0.0
        summary[name] = {"n": len(questions), "accuracy": round(acc, 4)}
        print(f"{name}: {acc:.1%} ({correct}/{len(questions)})")

    save_results(metadata, all_items, summary)

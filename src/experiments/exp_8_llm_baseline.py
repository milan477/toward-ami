"""
Exp 8: legacy LLM-only baseline.
Query the model with benchmark questions but NO audio, to establish
how much a text-only model can score — the floor that audio adds value over.
"""

from models.api import get_model_info, query_text_only
from src.helpers.results import get_run_metadata, save_results
from src.analysis.load import available_benchmarks, load_items
from src.querying.common import run_stamp

CONFIG = {
    "benchmarks": "all",   # or list of benchmark names
    "n_questions_per_benchmark": None,  # sample size per benchmark (None = all)
    "prompt_template": (
        "Answer the following music question. "
        "You do not have access to any audio.\n\n{question}"
    ),
}


def _load_questions(benchmark_name: str) -> list[dict]:
    """Return normalized benchmark question rows."""
    items = load_items(benchmark_name)
    if not items:
        raise NotImplementedError(
            f"No normalized data for {benchmark_name!r}. "
            f"Run:  python download/run.py {benchmark_name.lower()}"
        )
    return items


def preview() -> None:
    benchmarks = available_benchmarks()
    print(f"Will run LLM-only baseline on {len(benchmarks)} benchmarks")
    for name in benchmarks:
        print(f"  - {name} ({len(load_items(name))} items)")


def run() -> None:
    model_info = get_model_info()
    metadata = get_run_metadata("exp_8_llm_baseline", model_info["model_id"], CONFIG)

    benchmarks = available_benchmarks()
    summary: dict[str, dict] = {}
    date = run_stamp()

    for name in benchmarks:
        try:
            questions = _load_questions(name)
        except NotImplementedError as e:
            print(f"Skipping {name}: {e}")
            continue

        n = CONFIG["n_questions_per_benchmark"]
        if n:
            questions = questions[:n]

        question_format = sorted({q.get("question_type", "") for q in questions if q.get("question_type")})
        correct = 0
        benchmark_items = []
        for q in questions:
            prompt = CONFIG["prompt_template"].format(question=q["question"])
            response = query_text_only(prompt)
            is_correct = response.strip().lower() == str(q["correct_answer"]).strip().lower()
            correct += int(is_correct)
            benchmark_items.append({
                "benchmark": name,
                "question_format": question_format,
                "question": q["question"],
                "distractors": q.get("distractors"),
                "expected": q["correct_answer"],
                "response": response,
                "correct": is_correct,
            })

        acc = correct / len(questions) if questions else 0.0
        summary[name] = {"n": len(questions), "accuracy": round(acc, 4)}
        print(f"{name}: {acc:.1%} ({correct}/{len(questions)})")
        save_results(metadata, benchmark_items, summary[name], benchmark=name, date=date)

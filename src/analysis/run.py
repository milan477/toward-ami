"""Entry point for all analysis scripts. Usage: python analysis/run.py [script] [--list]"""

import argparse
import inspect
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from catalog import load_all

SCRIPTS = {
    "taxonomy":             ("taxonomy",             ["skill_distribution", "format_breakdown"]),
    "overlap":              ("overlap",              ["skill_overlap_matrix"]),
    "timeline":             ("timeline",             ["publication_timeline", "sota_score_evolution"]),
    "gaps":                 ("gaps",                 ["gap_report"]),
    "question_categories":  ("question_categories",  ["question_category_breakdown"]),
    "deep_analysis":        ("deep_analysis",        ["deep_analysis"]),
}

ANALYSIS_DIR = Path(__file__).resolve().parents[2] / "paper" / "analysis"


def _out_dir() -> Path:
    return ANALYSIS_DIR / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def run_script(
    name: str,
    out_dir: Path,
    benchmark: str | None = None,
    extra_kwargs: dict | None = None,
) -> None:
    module_name, functions = SCRIPTS[name]
    mod = __import__(module_name)
    benchmarks = load_all()
    if benchmark:
        benchmarks = [b for b in benchmarks if b["name"].lower() == benchmark.lower()]
        if not benchmarks:
            sys.exit(f"No benchmark named {benchmark!r} found in catalog.")
        print(f"Filtering to benchmark: {benchmarks[0]['name']}")
    script_out = out_dir / name
    kwargs = extra_kwargs or {}
    for fn_name in functions:
        fn = getattr(mod, fn_name)
        print(f"Running {module_name}.{fn_name} → {script_out}/")
        sig = inspect.signature(fn)
        accepted = set(sig.parameters)
        safe_kwargs = {k: v for k, v in kwargs.items() if k in accepted}
        fn(benchmarks, script_out, **safe_kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run analysis scripts.")
    parser.add_argument("script", nargs="?", help="Script to run (e.g. taxonomy)")
    parser.add_argument("--list", action="store_true", help="List available scripts")
    parser.add_argument("--all", action="store_true", help="Run all scripts in order")
    parser.add_argument("--benchmark", metavar="NAME", help="Restrict analysis to one benchmark (e.g. MMAR)")
    # deep_analysis options (silently ignored by other scripts)
    parser.add_argument("--backend", choices=["ollama", "hf"], default=None,
                        help="LLM backend for deep_analysis (default: LLM_BACKEND env or 'ollama')")
    parser.add_argument("--model",   default=None,
                        help="Ollama model tag or HuggingFace model id for deep_analysis")
    parser.add_argument("--skip-llm",  action="store_true", help="Skip LLM steps in deep_analysis")
    parser.add_argument("--skip-sim",  action="store_true", help="Skip sentence-encoder in deep_analysis")
    args = parser.parse_args()

    if args.list or (not args.script and not args.all):
        print("Available analysis scripts:")
        for name, (module, fns) in SCRIPTS.items():
            print(f"  {name:<22} {', '.join(fns)}")
        return

    targets = list(SCRIPTS) if args.all else [args.script]
    for name in targets:
        if name not in SCRIPTS:
            sys.exit(f"Unknown script {name!r}. Run with --list to see options.")

    deep_kwargs: dict = {}
    if args.skip_llm:
        deep_kwargs["skip_llm"] = True
    if args.skip_sim:
        deep_kwargs["skip_similarity"] = True
    if "deep_analysis" in targets and not args.skip_llm:
        from llm import LLMClient
        backend = args.backend or "ollama"
        if backend == "hf":
            deep_kwargs["client"] = LLMClient.from_hf(args.model) if args.model else LLMClient.from_hf()
        else:
            deep_kwargs["client"] = LLMClient.from_ollama(args.model) if args.model else LLMClient.from_ollama()
        print(f"LLM client: {deep_kwargs['client']}")

    out_dir = _out_dir()
    print(f"Output directory: {out_dir}")

    for name in targets:
        kwargs = deep_kwargs if name == "deep_analysis" else {}
        run_script(name, out_dir, benchmark=args.benchmark, extra_kwargs=kwargs)


if __name__ == "__main__":
    main()

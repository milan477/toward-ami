"""Central dispatcher for src workflows.

Usage:
    python -m src.run --list
    python -m src.run analysis pipeline mmar --limit 20
    python -m src.run decomposition decompose mmar --limit 5
    python -m src.run experiments exp-0 mmar --model af-next --limit 5
"""

from __future__ import annotations

import argparse
import importlib
import sys

COMMANDS: dict[str, dict[str, str]] = {
    "preprocess": {
        "load": "src.preprocess.benchmarks",
    },
    "analysis": {
        "enhance": "src.analysis.run",
        "pipeline": "src.analysis.run",
        "rewrite-questions": "src.analysis.run",
        "statistics": "src.analysis.run",
        "piec": "src.analysis.piec_analyze",
    },
    "evaluation": {
        "judge": "src.evaluation.judge",
    },
    "decomposition": {
        "decompose": "src.analysis.decompose",
        "perturbation": "src.experiments.exp_9_perturbation",
    },
    "experiments": {
        "batch": "src.experiments.batch",
        "exp-0": "src.experiments.exp_0_text_mcq",
        "exp-1": "src.experiments.exp_1_no_audio",
        "exp-2": "src.experiments.exp_2_no_audio_stt",
        "exp-3": "src.experiments.exp_3_format_type_oeq",
        "exp-4": "src.experiments.exp_4_original_mcq",
        "exp-5": "src.experiments.exp_5_piec_rewrite",
        "exp-6": "src.experiments.exp_6_task_rewrite_mcq",
        "exp-7": "src.experiments.exp_7_mcq_oeq",
        "exp-8": "src.experiments.exp_8_llm_baseline",
        "exp-9": "src.experiments.exp_9_perturbation",
        "exp-10": "src.experiments.exp_10_decomposition",
        "exp-11": "src.experiments.exp_11_probe_eval",
    },
}


def _print_commands() -> None:
    print("Available commands:")
    for area, commands in COMMANDS.items():
        print(f"\n{area}")
        for name, module in commands.items():
            print(f"  {name:<14} {module}")


def _resolve(area: str, command: str) -> str:
    try:
        return COMMANDS[area][command]
    except KeyError:
        choices = ", ".join(COMMANDS.get(area, {})) if area in COMMANDS else ", ".join(COMMANDS)
        raise SystemExit(f"Unknown command {area} {command!r}. Choices: {choices}")


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("area", nargs="?")
    parser.add_argument("command", nargs="?")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    ns = parser.parse_args()

    if ns.help or ns.list or not ns.area:
        _print_commands()
        print("\nPass command-specific flags after the command, e.g. "
              "`python -m src.run analysis pipeline mmar --limit 20`.")
        return
    if not ns.command:
        raise SystemExit(f"Missing command for area {ns.area!r}. Run `python -m src.run --list`.")

    module = _resolve(ns.area, ns.command)
    if module == "src.analysis.run":
        sys.argv = [ns.area, ns.command, *ns.args]
    else:
        sys.argv = [f"{ns.area} {ns.command}", *ns.args]
    mod = importlib.import_module(module)
    if hasattr(mod, "main"):
        mod.main()
    elif hasattr(mod, "run"):
        mod.run()
    else:
        raise SystemExit(f"{module} has no main() or run() entry point.")


if __name__ == "__main__":
    main()

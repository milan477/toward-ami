"""Central dispatcher for src workflows.

Usage:
    python -m src.run --list
    python -m src.run analysis pipeline mmar --limit 20
    python -m src.run decomposition decompose mmar --limit 5
    python -m src.run experiments mcq-oeq --model af-next --limit 5
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
        "annotate": "src.analysis.run",
        "pipeline": "src.analysis.run",
        "statistics": "src.analysis.run",
    },
    "evaluation": {
        "judge": "src.evaluation.judge",
        "piac": "src.evaluation.piac_analyze",
    },
    "decomposition": {
        "decompose": "src.decomposition.decompose",
        "perturbation": "src.decomposition.exp_2_perturbation",
    },
    "experiments": {
        "mcq-oeq": "src.experiments.exp_0_mcq_oeq",
        "probes": "src.experiments.exp_4_probe_eval",
        "llm-baseline": "src.experiments.exp_1_llm_baseline",
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

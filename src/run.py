"""Entry point for all src. Usage: python run.py <exp_name> [--preview]"""

import argparse
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent / "scripts"


def load_exp(name: str):
    matches = list(SCRIPTS.glob(f"{name}.py"))
    if not matches:
        sys.exit(f"No experiment script found for {name!r}. Run with --list to see options.")
    spec = importlib.util.spec_from_file_location(name, matches[0])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def list_experiments():
    for p in sorted(SCRIPTS.glob("exp_*.py")):
        print(f"  {p.stem}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("exp", nargs="?", help="Experiment name (e.g. exp_1_llm_baseline)")
    parser.add_argument("--preview", action="store_true", help="Preview without querying model")
    parser.add_argument("--list", action="store_true", help="List available experiments")
    args = parser.parse_args()

    if args.list or not args.exp:
        print("Available experiments:")
        list_experiments()
        return

    mod = load_exp(args.exp)
    if args.preview:
        mod.preview()
    else:
        mod.run()


if __name__ == "__main__":
    main()

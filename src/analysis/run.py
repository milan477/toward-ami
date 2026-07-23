"""Opening CLI for analysis workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.config import DEFAULT_JUDGE_SPEC


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark analysis.")
    sub = parser.add_subparsers(dest="command")

    enhance = sub.add_parser("enhance", help="Add LLM-derived dimensions to normalized questions.")
    enhance.add_argument("dataset")
    enhance.add_argument("--modality", default="")
    enhance.add_argument("--limit", type=int, default=None)
    enhance.add_argument("--judge", default=DEFAULT_JUDGE_SPEC)
    enhance.add_argument(
        "--transcriber", default=None,
        help="Audio-capable model spec for STT (defaults to --judge when audio-capable).",
    )
    enhance.add_argument("--rewriter", default=None)
    enhance.add_argument("--task-rewriter", default=None)
    enhance.add_argument("--overwrite", action="store_true")

    pipe = sub.add_parser("pipeline", help="Alias for enhance; runs the full analysis pipeline.")
    pipe.add_argument("dataset")
    pipe.add_argument("--modality", default="")
    pipe.add_argument("--limit", type=int, default=None)
    pipe.add_argument("--judge", default=DEFAULT_JUDGE_SPEC)
    pipe.add_argument(
        "--transcriber", default=None,
        help="Audio-capable model spec for STT (defaults to --judge when audio-capable).",
    )
    pipe.add_argument("--rewriter", default=None)
    pipe.add_argument("--task-rewriter", default=None)
    pipe.add_argument("--overwrite", action="store_true")

    stats = sub.add_parser("statistics", help="Write benchmark statistics.")
    stats.add_argument("dataset", nargs="?", default=None)
    stats.add_argument("--stage", default="normalized")
    stats.add_argument("--out", default=None)

    rewrite = sub.add_parser(
        "rewrite-questions", help="Backfill maximally open-ended question rewrites."
    )
    rewrite.add_argument("dataset")
    rewrite.add_argument("--model", default=DEFAULT_JUDGE_SPEC)
    rewrite.add_argument("--limit", type=int, default=None)
    rewrite.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()
    if args.command in {"enhance", "pipeline"}:
        from src.analysis import pipeline

        pipeline.run(
            args.dataset,
            args.modality or None,
            args.limit,
            judge_spec=args.judge,
            transcriber_spec=args.transcriber,
            rewriter_spec=args.rewriter,
            task_rewriter_spec=args.task_rewriter,
            overwrite=args.overwrite,
        )
    elif args.command == "statistics":
        from src.analysis.statistics import write_statistics

        write_statistics(args.dataset, args.stage, Path(args.out) if args.out else None)
    elif args.command == "rewrite-questions":
        from src.analysis.rewrite_questions import rewrite_enhanced_questions

        rewrite_enhanced_questions(
            args.dataset, args.model, args.limit, overwrite=args.overwrite
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

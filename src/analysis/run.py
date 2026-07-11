"""Opening CLI for analysis workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.config import DEFAULT_JUDGE_SPEC, DEFAULT_MODALITY


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark analysis.")
    sub = parser.add_subparsers(dest="command")

    annotate = sub.add_parser("annotate", help="Classify questions and write the annotated CSV.")
    annotate.add_argument("dataset")
    annotate.add_argument("--modality", default=DEFAULT_MODALITY)
    annotate.add_argument("--limit", type=int, default=None)
    annotate.add_argument("--judge", default=DEFAULT_JUDGE_SPEC)
    annotate.add_argument("--overwrite", action="store_true")

    pipe = sub.add_parser("pipeline", help="Alias for annotate; runs the full analysis pipeline.")
    pipe.add_argument("dataset")
    pipe.add_argument("--modality", default=DEFAULT_MODALITY)
    pipe.add_argument("--limit", type=int, default=None)
    pipe.add_argument("--judge", default=DEFAULT_JUDGE_SPEC)
    pipe.add_argument("--overwrite", action="store_true")

    stats = sub.add_parser("statistics", help="Write benchmark statistics.")
    stats.add_argument("dataset", nargs="?", default=None)
    stats.add_argument("--stage", default="normalized")
    stats.add_argument("--out", default=None)

    args = parser.parse_args()
    if args.command in {"annotate", "pipeline"}:
        if args.command == "pipeline":
            from src.analysis import pipeline

            pipeline.run(
                args.dataset,
                args.modality or None,
                args.limit,
                judge_spec=args.judge,
                overwrite=args.overwrite,
            )
        else:
            from src.analysis.annotate import annotate

            annotate(
                args.dataset,
                args.modality or None,
                args.limit,
                judge_spec=args.judge,
                overwrite=args.overwrite,
            )
    elif args.command == "statistics":
        from src.analysis.statistics import write_statistics

        write_statistics(args.dataset, args.stage, Path(args.out) if args.out else None)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

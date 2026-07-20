"""Save and load experiment results with full reproducibility metadata."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.querying.common import create_result_dir


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent.parent.parent,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def get_run_metadata(exp_name: str, model: str, config: dict) -> dict:
    return {
        "exp_name": exp_name,
        "model": model,
        "config": config,
        "git_commit": git_commit(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def save_results(
    metadata: dict,
    items: list[dict],
    summary: dict,
    *,
    benchmark: str,
    date: str | None = None,
) -> Path:
    """Save one benchmark run below experiment/benchmark/model/date."""
    exp_name = metadata["exp_name"]
    run_dir = create_result_dir(exp_name, benchmark, metadata["model"], date)

    payload = {**metadata, "benchmark": benchmark, "result_dir": str(run_dir),
               "summary": summary, "items": items}

    json_path = run_dir / "results.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    txt_path = run_dir / "report.txt"
    lines = [
        f"Experiment: {exp_name}",
        f"Benchmark:  {benchmark}",
        f"Model:      {metadata['model']}",
        f"Commit:     {metadata['git_commit']}",
        f"Timestamp:  {metadata['timestamp']}",
        "",
        "Summary:",
        *[f"  {k}: {v}" for k, v in summary.items()],
    ]
    txt_path.write_text("\n".join(lines))

    print(f"Results saved to {run_dir}")
    return run_dir

"""Save and load experiment results with full reproducibility metadata."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RESULTS_ROOT = Path(__file__).resolve().parents[2] / "results"


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


def save_results(metadata: dict, items: list[dict], summary: dict) -> Path:
    exp_name = metadata["exp_name"]
    model_slug = metadata["model"].replace("/", "_").replace(":", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    run_dir = RESULTS_ROOT / exp_name / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = {**metadata, "summary": summary, "items": items}

    json_path = run_dir / f"results_{model_slug}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    txt_path = run_dir / f"results_{model_slug}.txt"
    lines = [
        f"Experiment: {exp_name}",
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

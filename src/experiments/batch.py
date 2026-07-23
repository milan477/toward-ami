"""Run the same frozen question batch across several experiment variants."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from download.common import bench_path
from src.config import DEFAULT_DATASET, DEFAULT_RUNNER_MODEL, RESULTS_DIR
from src.experiments.runner import run_variant
from src.experiments.variants import get_variant
from src.helpers.results import git_commit
from src.querying.common import row_has_focus


def parse_experiments(raw: str) -> list[int]:
    """Parse comma-separated numbers/ranges such as ``0-3,5,6``."""
    numbers: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            if end < start:
                raise ValueError(f"Invalid experiment range: {part}")
            numbers.extend(range(start, end + 1))
        else:
            numbers.append(int(part))
    unique = list(dict.fromkeys(numbers))
    for number in unique:
        get_variant(number)
    if not unique:
        raise ValueError("Choose at least one experiment.")
    return unique


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_questions(path: Path, rows: list[dict]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _campaign_root(campaign: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", campaign):
        raise ValueError(
            "Campaign names may contain only letters, numbers, dots, underscores, and hyphens."
        )
    return RESULTS_DIR / "campaigns" / campaign


def prepare_campaign(campaign: str, benchmark: str, model_spec: str) -> tuple[Path, dict]:
    """Create or validate immutable dataset snapshots for one campaign."""
    root = _campaign_root(campaign)
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {"benchmark": benchmark, "model_spec": model_spec}
        mismatched = {
            key: (manifest.get(key), value)
            for key, value in expected.items()
            if manifest.get(key) != value
        }
        if mismatched:
            raise ValueError(f"Campaign {campaign!r} has incompatible settings: {mismatched}")
        for stage, filename in manifest.get("snapshots", {}).items():
            snapshot = root / filename
            expected_hash = manifest.get("snapshot_sha256", {}).get(stage)
            if not snapshot.exists() or not expected_hash or _sha256(snapshot) != expected_hash:
                raise ValueError(
                    f"Campaign {campaign!r} has a missing or modified {stage} snapshot."
                )
        return root, manifest

    selected = bench_path(benchmark, "selected")
    enhanced = bench_path(benchmark, "enhanced")
    if not selected.exists():
        raise FileNotFoundError(f"Missing selected benchmark data: {selected}")

    root.mkdir(parents=True, exist_ok=False)
    selected_snapshot = root / "normalized_selected.csv"
    shutil.copy2(selected, selected_snapshot)
    snapshots = {"selected": selected_snapshot.name}
    hashes = {"selected": _sha256(selected_snapshot)}
    if enhanced.exists():
        enhanced_snapshot = root / "normalized_selected_enhanced.csv"
        shutil.copy2(enhanced, enhanced_snapshot)
        snapshots["enhanced"] = enhanced_snapshot.name
        hashes["enhanced"] = _sha256(enhanced_snapshot)

    rows = _read_rows(selected_snapshot)
    qids = [row.get("qid", "") for row in rows]
    if not all(qids) or len(qids) != len(set(qids)):
        raise ValueError("Selected snapshot must contain unique, non-empty qids.")
    _write_questions(root / "questions.jsonl", rows)
    manifest = {
        "schema": "experiment-campaign-v1",
        "campaign": campaign,
        "benchmark": benchmark,
        "model_spec": model_spec,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "snapshots": snapshots,
        "snapshot_sha256": hashes,
        "question_qids": qids,
        "n_questions": len(qids),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return root, manifest


def resolve_batch(
    total: int,
    *,
    start: int | None,
    limit: int | None,
    batch_index: int | None,
    batch_size: int | None,
) -> tuple[int, int]:
    """Return a zero-based half-open slice after validating CLI conventions."""
    indexed = batch_index is not None or batch_size is not None
    ranged = start is not None or limit is not None
    if indexed and ranged:
        raise ValueError("Use either --start/--limit or --batch-index/--batch-size, not both.")
    if indexed:
        if batch_index is None or batch_size is None or batch_index < 1 or batch_size < 1:
            raise ValueError("--batch-index and --batch-size must both be positive integers.")
        first = (batch_index - 1) * batch_size
        return first, min(first + batch_size, total)
    if start is None or limit is None or start < 1 or limit < 1:
        raise ValueError("--start and --limit must both be positive integers.")
    first = start - 1
    return first, min(first + limit, total)


def run_batch(
    benchmark: str,
    model_spec: str,
    campaign: str,
    experiments: list[int],
    *,
    start: int | None = None,
    limit: int | None = None,
    batch_index: int | None = None,
    batch_size: int | None = None,
    modality: str | None = None,
    no_judge: bool = False,
) -> list[Path]:
    root, manifest = prepare_campaign(campaign, benchmark, model_spec)
    candidate_qids = manifest["question_qids"]
    if modality:
        selected_rows = _read_rows(root / manifest["snapshots"]["selected"])
        candidate_qids = [
            row["qid"] for row in selected_rows if row_has_focus(row, modality)
        ]
    first, stop = resolve_batch(
        len(candidate_qids),
        start=start,
        limit=limit,
        batch_index=batch_index,
        batch_size=batch_size,
    )
    if first >= len(candidate_qids):
        raise ValueError(
            f"Batch starts at question {first + 1}, beyond campaign size "
            f"{len(candidate_qids)} for focus {modality or 'all'}."
        )
    qids = candidate_qids[first:stop]
    focus_prefix = f"{modality.casefold()}_" if modality else ""
    batch_name = f"{focus_prefix}batch_{first + 1:06d}_{stop:06d}"
    outputs: list[Path] = []
    for number in experiments:
        variant = get_variant(number)
        stage = "enhanced" if variant.requires_enhanced else "selected"
        snapshot_name = manifest["snapshots"].get(stage)
        if not snapshot_name:
            raise FileNotFoundError(
                f"Campaign {campaign!r} has no {stage} snapshot required by "
                f"{variant.experiment_name}. Create a new campaign after enhancement."
            )
        output = root / variant.experiment_name / batch_name
        outputs.append(
            run_variant(
                number,
                model_spec,
                root / snapshot_name,
                modality,
                None,
                benchmark_name=benchmark,
                no_judge=no_judge,
                qid_subset=qids,
                run_dir_override=output,
            )
        )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", nargs="?", default=DEFAULT_DATASET)
    parser.add_argument("--model", default=DEFAULT_RUNNER_MODEL)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--experiments", default="0-6")
    parser.add_argument("--start", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-index", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--modality", default="")
    parser.add_argument("--no-judge", action="store_true")
    args = parser.parse_args()
    try:
        experiments = parse_experiments(args.experiments)
        outputs = run_batch(
            args.benchmark,
            args.model,
            args.campaign,
            experiments,
            start=args.start,
            limit=args.limit,
            batch_index=args.batch_index,
            batch_size=args.batch_size,
            modality=args.modality or None,
            no_judge=args.no_judge,
        )
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))
    print("Campaign batch complete:")
    for output in outputs:
        print(f"  {output}")


if __name__ == "__main__":
    main()

"""Durable, per-day cost accounting for successful OpenRouter calls."""

from __future__ import annotations

import csv
import fcntl
import os
import tempfile
import threading
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CALLS_DIR = ROOT / "data" / "calls"

DETAIL_FIELDS = [
    "id",
    "cost",
    "input length",
    "output length",
    "date",
    "#tokens prompt",
    "#tokens response",
    "prompt",
    "response",
]
TOTAL_FIELDS = ["date", "cost", "calls", "last call"]

_THREAD_LOCK = threading.Lock()


def _one_line(value: object) -> str:
    """Collapse all whitespace so CSV prompt/response values stay on one line."""
    return " ".join(str(value).split())


def _decimal_text(value: Decimal) -> str:
    """Write a non-exponent decimal without discarding provider precision."""
    return format(value, "f")


def _require_usage(response: dict) -> tuple[str, Decimal, int, int]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("OpenRouter response did not include usage accounting.")

    call_id = response.get("id")
    if not call_id:
        raise RuntimeError("OpenRouter response did not include a call id.")

    try:
        cost = Decimal(str(usage["cost"]))
        prompt_tokens = int(usage["prompt_tokens"])
        response_tokens = int(usage["completion_tokens"])
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise RuntimeError(
            "OpenRouter response had incomplete cost/token usage accounting."
        ) from exc

    return str(call_id), cost, prompt_tokens, response_tokens


def record_openrouter_call(
    api_response: dict,
    prompt: object,
    response: object,
    *,
    called_at: datetime | None = None,
    calls_dir: Path | None = None,
) -> Path:
    """Append a billed call and atomically rebuild daily/all-time totals.

    The API response is validated before any file is changed. Both a thread lock
    and an OS file lock protect concurrent experiment workers.
    """
    call_id, cost, prompt_tokens, response_tokens = _require_usage(api_response)
    timestamp = called_at or datetime.now().astimezone()
    if timestamp.tzinfo is None:
        timestamp = timestamp.astimezone()
    timestamp_text = timestamp.isoformat(timespec="seconds")
    directory = Path(calls_dir) if calls_dir is not None else CALLS_DIR
    detail_path = directory / f"{timestamp.date().isoformat()}.csv"
    prompt_text = str(prompt)
    response_text = "" if response is None else str(response)

    row = {
        "id": call_id,
        "cost": _decimal_text(cost),
        "input length": len(prompt_text),
        "output length": len(response_text),
        "date": timestamp_text,
        "#tokens prompt": prompt_tokens,
        "#tokens response": response_tokens,
        "prompt": _one_line(prompt_text),
        "response": _one_line(response_text),
    }

    directory.mkdir(parents=True, exist_ok=True)
    with _THREAD_LOCK, (directory / ".lock").open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        _append_detail(detail_path, row)
        _rebuild_totals(directory)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return detail_path


def _append_detail(path: Path, row: dict) -> None:
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=DETAIL_FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
        output.flush()
        os.fsync(output.fileno())


def _rebuild_totals(directory: Path) -> None:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    call_counts: dict[str, int] = defaultdict(int)
    last_calls: dict[str, str] = {}

    for detail_path in sorted(directory.glob("????-??-??.csv")):
        with detail_path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source):
                day = detail_path.stem
                try:
                    totals[day] += Decimal(row["cost"])
                except (KeyError, InvalidOperation) as exc:
                    raise RuntimeError(f"Invalid cost row in {detail_path}.") from exc
                call_counts[day] += 1
                timestamp = row.get("date", "")
                if timestamp > last_calls.get(day, ""):
                    last_calls[day] = timestamp

    rows = [
        {
            "date": day,
            "cost": _decimal_text(totals[day]),
            "calls": call_counts[day],
            "last call": last_calls.get(day, ""),
        }
        for day in sorted(totals)
    ]
    rows.append(
        {
            "date": "TOTAL",
            "cost": _decimal_text(sum(totals.values(), Decimal())),
            "calls": sum(call_counts.values()),
            "last call": max(last_calls.values(), default=""),
        }
    )

    target = directory / "total.csv"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=directory, delete=False
    ) as output:
        temporary = Path(output.name)
        writer = csv.DictWriter(output, fieldnames=TOTAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, target)

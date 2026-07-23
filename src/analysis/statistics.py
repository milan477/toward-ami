"""Benchmark statistics for analysis reports and the static site."""

from __future__ import annotations

import json
import re
import wave
from collections import Counter
from pathlib import Path

import pandas as pd

from download.common import bench_path
from src.analysis.load import available_benchmarks
from src.config import DATA_DIR, ROOT
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus"}
STAGE_FALLBACKS = ("enhanced", "selected", "normalized")
CATEGORY_DIMENSIONS = {
    "modality": "Modality",
    "category": "Category",
    "genre": "Genre",
    "content": "Content",
    "action": "Action",
}


def _stage_path(name: str, stage: str) -> tuple[Path, str]:
    if stage != "best":
        return bench_path(name, stage), stage
    for candidate in STAGE_FALLBACKS:
        path = bench_path(name, candidate)
        if path.exists():
            return path, candidate
    return bench_path(name, "normalized"), "normalized"


def _load_frame(name: str, stage: str) -> tuple[pd.DataFrame, Path, str]:
    path, resolved_stage = _stage_path(name, stage)
    if not path.exists():
        return pd.DataFrame(), path, resolved_stage
    return pd.read_csv(path, dtype=str, keep_default_na=False), path, resolved_stage


def _parse_json_list(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_listish(raw) -> list[str]:
    """Parse JSON lists, concatenated JSON lists, or comma-separated cells."""
    text = str(raw or "").strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    out: list[str] = []
    pos = 0
    decoded_json = False
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        try:
            value, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        decoded_json = True
        if isinstance(value, list):
            out.extend(str(item).strip() for item in value if str(item).strip())
        elif str(value).strip():
            out.append(str(value).strip())
        pos = end
    if decoded_json:
        return _dedupe(out)
    if not out:
        out = [part.strip() for part in re.split(r"[,;]", text) if part.strip()]
    return _dedupe(out)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _category_cell_values(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        return _parse_listish(text)
    return [text]


def category_values_for_row(row: dict) -> dict[str, list[str]]:
    """Named, list-valued category dimensions used by stats and the website."""
    category_columns = sorted(
        (key for key in row if re.fullmatch(r"category_[1-9][0-9]*_.+", key)),
        key=lambda key: (int(key.split("_", 2)[1]), key),
    )
    categories = _dedupe([
        value
        for key in category_columns
        for value in _category_cell_values(row.get(key, ""))
    ])
    genres = _dedupe([
        value for key in category_columns if "genre" in key
        for value in _category_cell_values(row.get(key, ""))
    ])
    try:
        pairs = json.loads(row.get("action_content", "") or "[]")
    except (json.JSONDecodeError, TypeError):
        pairs = []
    if not isinstance(pairs, list):
        pairs = []
    actions = _dedupe([str(pair[0]) for pair in pairs if isinstance(pair, list) and len(pair) == 2])
    content = _dedupe([str(pair[1]) for pair in pairs if isinstance(pair, list) and len(pair) == 2])
    return {
        "modality": _parse_listish(row.get("focus", "")),
        "category": categories,
        "genre": genres,
        "content": content,
        "action": actions,
    }


def _audio_names(raw: str) -> list[str]:
    names = []
    pieces = _parse_json_list(raw)
    if not pieces:
        pieces = str(raw or "").split(";")
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        name = piece.replace("\\", "/").lstrip("./")
        if ":" in name:
            name = name.split(":", 1)[1]
        if name:
            names.append(name)
    return names


def _build_audio_index(name: str) -> dict[str, Path]:
    roots = [DATA_DIR / "audio" / name, DATA_DIR / "audio"]
    index: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                try:
                    index.setdefault(path.relative_to(root).as_posix(), path)
                except ValueError:
                    pass
                index.setdefault(path.name, path)
                index.setdefault(path.stem, path)
    return index


def _audio_duration(path: Path) -> float | None:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                rate = handle.getframerate()
                return handle.getnframes() / rate if rate else None
        except (wave.Error, EOFError, OSError):
            pass
    if path.suffix.lower() == ".mp3":
        duration = _mp3_duration(path)
        if duration is not None:
            return duration
    try:
        import soundfile as sf

        info = sf.info(str(path))
        if info.samplerate:
            return float(info.frames) / float(info.samplerate)
    except Exception:
        pass
    return _duration_from_name(path.name)


_MPEG_BITRATES = {
    ("1", "I"):    [None, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    ("1", "II"):   [None, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    ("1", "III"):  [None, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    ("2", "I"):    [None, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
    ("2", "II"):   [None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    ("2", "III"):  [None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_MPEG_SAMPLE_RATES = {
    "1": [44100, 48000, 32000],
    "2": [22050, 24000, 16000],
    "2.5": [11025, 12000, 8000],
}


def _mp3_duration(path: Path) -> float | None:
    """Estimate MP3 duration by summing MPEG audio frame durations."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    pos = _skip_id3v2(data)
    total_seconds = 0.0
    frames = 0
    while pos + 4 <= len(data):
        header = int.from_bytes(data[pos:pos + 4], "big")
        frame = _parse_mp3_header(header)
        if frame is None:
            pos += 1
            continue
        frame_len, sample_rate, samples = frame
        if frame_len <= 0 or pos + frame_len > len(data):
            pos += 1
            continue
        total_seconds += samples / sample_rate
        frames += 1
        pos += frame_len
    return total_seconds if frames else None


def _skip_id3v2(data: bytes) -> int:
    if len(data) < 10 or data[:3] != b"ID3":
        return 0
    size = (
        ((data[6] & 0x7F) << 21)
        | ((data[7] & 0x7F) << 14)
        | ((data[8] & 0x7F) << 7)
        | (data[9] & 0x7F)
    )
    footer = 10 if data[5] & 0x10 else 0
    return 10 + size + footer


def _parse_mp3_header(header: int) -> tuple[int, int, int] | None:
    if (header >> 21) & 0x7FF != 0x7FF:
        return None
    version_bits = (header >> 19) & 0x3
    layer_bits = (header >> 17) & 0x3
    bitrate_idx = (header >> 12) & 0xF
    sample_rate_idx = (header >> 10) & 0x3
    padding = (header >> 9) & 0x1
    if version_bits == 1 or layer_bits == 0 or bitrate_idx in (0, 15) or sample_rate_idx == 3:
        return None

    version = {3: "1", 2: "2", 0: "2.5"}[version_bits]
    layer = {3: "I", 2: "II", 1: "III"}[layer_bits]
    bitrate_version = "1" if version == "1" else "2"
    bitrate = _MPEG_BITRATES[(bitrate_version, layer)][bitrate_idx] * 1000
    sample_rate = _MPEG_SAMPLE_RATES[version][sample_rate_idx]

    if layer == "I":
        frame_len = int((12 * bitrate / sample_rate + padding) * 4)
        samples = 384
    elif layer == "III" and version != "1":
        frame_len = int(72 * bitrate / sample_rate + padding)
        samples = 576
    else:
        frame_len = int(144 * bitrate / sample_rate + padding)
        samples = 1152
    return frame_len, sample_rate, samples


def _timestamp_seconds(raw: str) -> int:
    parts = [int(p) for p in raw.split("-")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def _duration_from_name(name: str) -> float | None:
    match = re.search(r"_(\d{2}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})(?:[_.]|$)", name)
    if not match:
        return None
    start = _timestamp_seconds(match.group(1))
    end = _timestamp_seconds(match.group(2))
    return float(end - start) if end > start else None


def _audio_duration_stats(name: str, audio_col: pd.Series) -> dict:
    index = _build_audio_index(name)
    durations: list[float] = []
    missing: set[str] = set()
    seen: set[str] = set()
    for raw in audio_col.astype(str):
        for audio_name in _audio_names(raw):
            key = audio_name or Path(audio_name).stem
            if not key or key in seen:
                continue
            seen.add(key)
            path = index.get(audio_name) or index.get(Path(audio_name).stem)
            if not path:
                missing.add(audio_name)
                continue
            duration = _audio_duration(path)
            if duration is None:
                missing.add(audio_name)
            else:
                durations.append(duration)
    durations_sorted = sorted(durations)
    rounded = [round(value, 3) for value in durations_sorted]
    return {
        "n_audio_files_with_duration": len(durations),
        "n_audio_files_missing_duration": len(missing),
        "average_audio_duration_seconds": round(sum(durations) / len(durations), 3) if durations else None,
        "median_audio_duration_seconds": round(durations_sorted[len(durations_sorted) // 2], 3) if durations_sorted else None,
        "min_audio_duration_seconds": round(min(durations), 3) if durations else None,
        "max_audio_duration_seconds": round(max(durations), 3) if durations else None,
        "total_audio_duration_seconds": round(sum(durations), 3) if durations else 0.0,
        "audio_duration_seconds": rounded,
        "audio_duration_histogram": _histogram_bins(rounded),
    }


def _histogram_bins(values: list[float], n_bins: int = 12) -> list[dict]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [{"min": lo, "max": hi, "count": len(values)}]
    width = (hi - lo) / n_bins
    bins = [{"min": lo + i * width, "max": lo + (i + 1) * width, "count": 0}
            for i in range(n_bins)]
    for value in values:
        idx = min(n_bins - 1, int((value - lo) / width))
        bins[idx]["count"] += 1
    return [
        {"min": round(item["min"], 3), "max": round(item["max"], 3), "count": item["count"]}
        for item in bins
    ]


def _counter(series: pd.Series) -> dict:
    values = [str(value).strip() or "(blank)" for value in series.astype(str)]
    return dict(Counter(values).most_common())


def _summarize_frame(name: str, df: pd.DataFrame) -> dict:
    audio = df.get("url", pd.Series(dtype=str)).astype(str)
    distractor_lists = [
        _parse_json_list(raw)
        for raw in df.get("distractors", pd.Series(dtype=str)).astype(str)
    ]
    distractor_counts = [len(items) for items in distractor_lists]
    questions_with_distractors = sum(1 for count in distractor_counts if count > 0)

    summary = {
        "n_questions": int(len(df)),
        "n_audio_files": len({name for raw in audio for name in _audio_names(raw)}),
        "n_questions_with_audio": sum(bool(_audio_names(raw)) for raw in audio),
        "question_nature_distribution": (
            _counter(df["question_nature"]) if "question_nature" in df.columns else {}
        ),
        "piec_distribution": _counter(df["piec"]) if "piec" in df.columns else {},
        "average_distractors": round(sum(distractor_counts) / len(distractor_counts), 3)
        if distractor_counts else 0.0,
        "max_distractors": max(distractor_counts) if distractor_counts else 0,
        "n_questions_with_distractors": int(questions_with_distractors),
        "pct_questions_with_distractors": round(questions_with_distractors / len(df), 4)
        if len(df) else 0.0,
        "distractor_count_distribution": dict(Counter(distractor_counts).most_common()),
        "creator_category_distributions": {
            column: _counter(df[column])
            for column in df.columns
            if re.fullmatch(r"category_[1-9][0-9]*_.+", column)
        },
        "columns": list(df.columns),
    }
    summary.update(_audio_duration_stats(name, audio))
    return summary


def _category_slices(name: str, df: pd.DataFrame) -> dict:
    row_values = [
        category_values_for_row({col: row.get(col, "") for col in df.columns})
        for _, row in df.iterrows()
    ]
    out: dict[str, dict[str, dict]] = {}
    for dim in CATEGORY_DIMENSIONS:
        labels = sorted({
            value
            for values in row_values
            for value in values.get(dim, [])
            if value
        }, key=str.lower)
        values: dict[str, dict] = {}
        for label in labels:
            mask = [label in values_by_dim.get(dim, []) for values_by_dim in row_values]
            group = df.loc[mask]
            stats = _summarize_frame(name, group)
            stats["filter"] = {"dimension": dim, "title": CATEGORY_DIMENSIONS[dim], "value": label}
            values[label] = stats
        out[dim] = {"title": CATEGORY_DIMENSIONS[dim], "values": values}
    return out


def benchmark_statistics(name: str, stage: str = "normalized") -> dict:
    df, path, resolved_stage = _load_frame(name, stage)
    if df.empty:
        return {
            "benchmark": name,
            "stage": stage,
            "resolved_stage": resolved_stage,
            "path": str(path.relative_to(ROOT)),
            "n_questions": 0,
            "missing": True,
        }

    stats = {
        "benchmark": name,
        "stage": stage,
        "resolved_stage": resolved_stage,
        "path": str(path.relative_to(ROOT)),
        "missing": False,
        **_summarize_frame(name, df),
        "by_category": _category_slices(name, df),
    }
    return stats


def collect_statistics(name: str | None = None, stage: str = "normalized") -> list[dict]:
    names = [name] if name else available_benchmarks()
    return [benchmark_statistics(benchmark, stage) for benchmark in names]


def statistics_paths(name: str, stage: str = "normalized") -> tuple[Path, Path]:
    directory = bench_path(name, "normalized").parent
    suffix = "statistics" if stage == "normalized" else f"{stage}_statistics"
    return directory / f"{name}_{suffix}.json", directory / f"{name}_{suffix}.csv"


def write_statistics(name: str | None = None, stage: str = "normalized",
                     out_dir: Path | None = None) -> Path:
    stats = collect_statistics(name, stage)
    summary_cols = [
        "benchmark", "resolved_stage", "n_questions", "n_audio_files",
        "average_audio_duration_seconds", "median_audio_duration_seconds",
        "average_distractors", "n_questions_with_distractors",
        "pct_questions_with_distractors",
    ]
    written: list[Path] = []
    for rec in stats:
        benchmark = rec["benchmark"]
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            json_path = out_dir / f"{benchmark}_{stage}_statistics.json"
            csv_path = out_dir / f"{benchmark}_{stage}_statistics.csv"
        else:
            json_path, csv_path = statistics_paths(benchmark, stage)
        json_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        pd.DataFrame([{col: rec.get(col) for col in summary_cols}]).to_csv(csv_path, index=False)
        written.append(json_path)

        print(f"{rec['benchmark']}: {rec['n_questions']} questions, "
              f"{rec.get('n_audio_files', 0)} audio files, "
              f"avg audio={rec.get('average_audio_duration_seconds')}s")
        print(f"Wrote {json_path}")
        print(f"Wrote {csv_path}")
    return written[0] if len(written) == 1 else written[-1]

"""Import source-backed benchmark results into SQLite and export site data."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data" / "results" / "literature_results.sqlite3"
SOURCES = ROOT / "literature" / "sources.json"
MMAR_TABLE_2 = ROOT / "literature" / "mmar_table_2.csv"
MMAU_TABLE_3 = ROOT / "literature" / "mmau_table_3.csv"
MMAU_PRO_TABLE_4 = ROOT / "literature" / "mmau_pro_table_4.csv"
HUMMUSQA_TABLE_1 = ROOT / "literature" / "hummusqa_table_1.csv"

MMAR_METRICS = (
    ("sound", "Sound", "Single modality", 1),
    ("music", "Music", "Single modality", 2),
    ("speech", "Speech", "Single modality", 3),
    ("sound_music", "Sound + music", "Mixed modalities", 4),
    ("sound_speech", "Sound + speech", "Mixed modalities", 5),
    ("music_speech", "Music + speech", "Mixed modalities", 6),
    ("sound_music_speech", "Sound + music + speech", "Mixed modalities", 7),
    ("average", "Average", "Overall", 0),
)

MMAU_METRICS = (
    ("average_test", "Average - test", "Overall", 0),
    ("average_test_mini", "Average - test-mini", "Overall", 1),
    ("sound_test", "Sound - test", "Sound", 2),
    ("sound_test_mini", "Sound - test-mini", "Sound", 3),
    ("music_test", "Music - test", "Music", 4),
    ("music_test_mini", "Music - test-mini", "Music", 5),
    ("speech_test", "Speech - test", "Speech", 6),
    ("speech_test_mini", "Speech - test-mini", "Speech", 7),
)

MMAU_PRO_METRICS = (
    ("average", "Average", "Overall", 0),
    ("sound", "Sound", "Single modality", 1),
    ("music", "Music", "Single modality", 2),
    ("speech", "Speech", "Single modality", 3),
    ("sound_music", "Sound + music", "Mixed modalities", 4),
    ("speech_music", "Speech + music", "Mixed modalities", 5),
    ("speech_sound", "Speech + sound", "Mixed modalities", 6),
    ("sound_music_speech", "Sound + music + speech", "Mixed modalities", 7),
    ("spatial", "Spatial", "Specialized", 8),
    ("voice", "Voice", "Specialized", 9),
    ("multi_audio", "Multi-audio", "Specialized", 10),
    ("open_ended", "Open-ended", "Specialized", 11),
    ("instruction_following", "Instruction following", "Specialized", 12),
)

HUMMUSQA_METRICS = (
    ("accuracy_all", "Accuracy - all", "Accuracy", 0),
    ("accuracy_low", "Accuracy - low difficulty", "Accuracy", 1),
    ("accuracy_medium", "Accuracy - medium difficulty", "Accuracy", 2),
    ("accuracy_high", "Accuracy - high difficulty", "Accuracy", 3),
    ("accuracy_all_sd", "Accuracy SD - all", "Accuracy uncertainty", 4),
    ("accuracy_low_sd", "Accuracy SD - low difficulty", "Accuracy uncertainty", 5),
    ("accuracy_medium_sd", "Accuracy SD - medium difficulty", "Accuracy uncertainty", 6),
    ("accuracy_high_sd", "Accuracy SD - high difficulty", "Accuracy uncertainty", 7),
    ("consistency_all", "Consistency - all", "Consistency", 8),
    ("consistency_low", "Consistency - low difficulty", "Consistency", 9),
    ("consistency_medium", "Consistency - medium difficulty", "Consistency", 10),
    ("consistency_high", "Consistency - high difficulty", "Consistency", 11),
)

TABLES = (
    (MMAR_TABLE_2, MMAR_METRICS, "Classification accuracy", "%", "average"),
    (MMAU_TABLE_3, MMAU_METRICS, "Micro-averaged accuracy", "%", "average_test"),
    (MMAU_PRO_TABLE_4, MMAU_PRO_METRICS, "Accuracy", "%", "average"),
    (HUMMUSQA_TABLE_1, HUMMUSQA_METRICS, "Accuracy and answer-order consistency", "%", "accuracy_all"),
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,
    year INTEGER NOT NULL,
    venue TEXT NOT NULL,
    url TEXT NOT NULL,
    pdf_url TEXT NOT NULL,
    local_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS result_sets (
    result_set_id TEXT PRIMARY KEY,
    benchmark TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    table_label TEXT NOT NULL,
    page INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    default_metric_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
    model_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    size TEXT NOT NULL,
    UNIQUE(name, category, size)
);

CREATE TABLE IF NOT EXISTS metrics (
    metric_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    metric_group TEXT NOT NULL,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS measurements (
    measurement_id INTEGER PRIMARY KEY,
    result_set_id TEXT NOT NULL REFERENCES result_sets(result_set_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    model_id INTEGER NOT NULL REFERENCES models(model_id),
    metric_id TEXT NOT NULL REFERENCES metrics(metric_id),
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    UNIQUE(result_set_id, model_id, metric_id)
);
"""


def rebuild_database(database: Path = DATABASE) -> Path:
    """Rebuild the generated database from checked-in, source-tagged extracts."""
    database.parent.mkdir(parents=True, exist_ok=True)
    database.unlink(missing_ok=True)
    with sqlite3.connect(database) as conn:
        conn.executescript(SCHEMA)
        sources = json.loads(SOURCES.read_text(encoding="utf-8"))
        conn.executemany(
            "INSERT INTO sources VALUES (:source_id, :title, :authors, :year, :venue, :url, :pdf_url, :local_path)",
            sources,
        )
        for path, metrics, metric_name, unit, default_metric_id in TABLES:
            conn.executemany("INSERT OR IGNORE INTO metrics VALUES (?, ?, ?, ?)", metrics)
            _import_wide_csv(
                conn, path, metrics, metric_name, unit, default_metric_id,
            )
    return database


def _import_wide_csv(
    conn: sqlite3.Connection,
    path: Path,
    metrics: tuple[tuple[str, str, str, int], ...],
    metric_name: str,
    unit: str,
    default_metric_id: str,
) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return
    first = rows[0]
    conn.execute(
        "INSERT INTO result_sets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            first["result_set_id"], first["benchmark"], first["source_id"],
            first["table_label"], int(first["page"]), metric_name, unit,
            default_metric_id,
        ),
    )
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO models(name, category, size) VALUES (?, ?, ?)",
            (row["model"], row["model_category"], row["size"]),
        )
        model_id = conn.execute(
            "SELECT model_id FROM models WHERE name = ? AND category = ? AND size = ?",
            (row["model"], row["model_category"], row["size"]),
        ).fetchone()[0]
        conn.executemany(
            """INSERT INTO measurements
               (result_set_id, source_id, model_id, metric_id, value, unit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    row["result_set_id"], row["source_id"], model_id,
                    metric_id, float(row[metric_id]), unit,
                )
                for metric_id, _, _, _ in metrics
                if row.get(metric_id, "").strip()
            ],
        )


def site_payload(database: Path = DATABASE) -> dict:
    """Return a static-site projection while preserving per-value provenance."""
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        source_rows = conn.execute("SELECT * FROM sources ORDER BY year, source_id").fetchall()
        metric_rows = conn.execute(
            "SELECT * FROM metrics ORDER BY display_order, metric_id"
        ).fetchall()
        set_rows = conn.execute(
            "SELECT * FROM result_sets ORDER BY benchmark, result_set_id"
        ).fetchall()
        payload_sets = []
        for result_set in set_rows:
            results = conn.execute(
                """SELECT m.name AS model, m.category, m.size, x.metric_id, x.value,
                          x.unit, x.source_id
                   FROM measurements x
                   JOIN models m ON m.model_id = x.model_id
                   WHERE x.result_set_id = ?
                   ORDER BY m.model_id, x.metric_id""",
                (result_set["result_set_id"],),
            ).fetchall()
            models: dict[tuple[str, str, str], dict] = {}
            for result in results:
                key = (result["model"], result["category"], result["size"])
                model = models.setdefault(key, {
                    "model": result["model"],
                    "category": result["category"],
                    "size": result["size"],
                    "values": {},
                })
                model["values"][result["metric_id"]] = {
                    "value": result["value"],
                    "unit": result["unit"],
                    "source_id": result["source_id"],
                }
            payload_sets.append({**dict(result_set), "models": list(models.values())})
    return {
        "sources": [dict(row) for row in source_rows],
        "metrics": [dict(row) for row in metric_rows],
        "result_sets": payload_sets,
    }


if __name__ == "__main__":
    path = rebuild_database()
    payload = site_payload(path)
    measurements = sum(len(model["values"]) for result_set in payload["result_sets"] for model in result_set["models"])
    print(f"wrote {path.relative_to(ROOT)} ({measurements} source-backed measurements)")

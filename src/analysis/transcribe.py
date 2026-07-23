"""Reusable audio-to-text preprocessing for benchmark analysis."""

from __future__ import annotations

import json
from pathlib import Path

from download.common import AUDIO_DIR, bench_dir
from src.helpers.results import git_commit


TRANSCRIPTION_PROMPT = (
    "Transcribe all intelligible speech in this audio verbatim. Preserve the "
    "language being spoken. Do not describe music, sound effects, speakers, or "
    "the acoustic environment. If there is no intelligible speech, return an "
    "empty string. Return only the transcription, without commentary or labels."
)
TRANSCRIPTION_COLUMN = "transcription"


def transcription_path(name: str) -> Path:
    return bench_dir(name) / f".{name}.normalized_selected.transcriptions.jsonl"


def _json_list(value) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def should_transcribe(name: str, row: dict) -> bool:
    """MMAR uses STT only for creator rows whose focus includes speech."""
    if name.casefold() != "mmar":
        return bool(_json_list(row.get("url", "")))
    return "speech" in {item.casefold() for item in _json_list(row.get("focus", ""))}


def resolve_audio_paths(name: str, row: dict) -> list[Path]:
    """Resolve normalized URL references against downloaded benchmark audio."""
    resolved: list[Path] = []
    for raw in _json_list(row.get("url", "")):
        value = Path(raw)
        candidates = (
            value,
            AUDIO_DIR / name / value,
            AUDIO_DIR / name / value.name,
        )
        found = next((path for path in candidates if path.is_file()), None)
        if found is not None and found not in resolved:
            resolved.append(found)
    return resolved


def load_transcriptions(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["qid"]] = record
    return records


class AudioTranscriber:
    """Cache audio-to-text results and their complete provenance."""

    def __init__(
        self,
        name: str,
        model_spec: str,
        *,
        overwrite: bool = False,
        client=None,
    ):
        from models.client import make_client

        self.name = name
        self.model_spec = model_spec
        self.client = client or make_client(model_spec)
        if not self.client.supports_audio:
            raise ValueError(
                f"Transcriber {self.client.model_id!r} does not support audio. "
                "Pass --transcriber with an audio-capable model."
            )
        self.path = transcription_path(name)
        self.records = {} if overwrite else load_transcriptions(self.path)
        self.handle = self.path.open("w" if overwrite else "a", encoding="utf-8")

    def close(self) -> None:
        self.handle.close()

    def transcribe(self, row: dict) -> str:
        qid = row["qid"]
        prior = self.records.get(qid)
        if prior is not None:
            return str(prior.get("transcription", ""))

        audio_paths = resolve_audio_paths(self.name, row)
        parts = [
            " ".join(
                self.client.generate(
                    TRANSCRIPTION_PROMPT, audio_path=str(path), max_tokens=1024
                ).strip().split()
            )
            for path in audio_paths
        ]
        parts = [part for part in parts if part]
        transcription = "\n".join(parts)
        record = {
            "qid": qid,
            "transcription": transcription,
            "transcription_model": self.client.model_id,
            "transcription_model_spec": self.model_spec,
            "transcription_git_commit": git_commit(),
            "transcription_prompt": TRANSCRIPTION_PROMPT,
            "transcription_audio_paths": [str(path) for path in audio_paths],
        }
        self.records[qid] = record
        self.handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.handle.flush()
        return transcription

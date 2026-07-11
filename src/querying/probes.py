"""Model-query helpers for decomposed probe chains."""

from __future__ import annotations

import json
from pathlib import Path

from src.config import OEQ_MAX_TOKENS
from src.querying.common import audio_name, read_jsonl
from src.querying.model_eval import generate_with_retries


def query_probe_answers(probe_units: list[dict], audio_index: dict[str, Path],
                        client, cache: Path) -> dict[str, dict]:
    """Query ``client`` for all uncached probe units."""
    done = read_jsonl(cache, key="key")
    todo = [unit for unit in probe_units if unit["key"] not in done]
    if not todo:
        print(f"[probe-query] all {len(done)} probe answers present; skipping generation.")
        return done

    print(f"[probe-query] {client.model_id}: {len(todo)} probes to answer ({len(done)} cached)")
    fh = cache.open("a", encoding="utf-8")
    for i, unit in enumerate(todo, 1):
        audio = audio_index.get(audio_name(unit["audio_url"]))
        if audio is None:
            rec = {
                "key": unit["key"],
                "qid": unit["qid"],
                "probe_idx": unit["probe_idx"],
                "skipped": "no_audio",
            }
        else:
            response, error = generate_with_retries(
                client,
                unit["prompt"],
                audio,
                OEQ_MAX_TOKENS,
            )
            rec = {
                "key": unit["key"],
                "qid": unit["qid"],
                "probe_idx": unit["probe_idx"],
                "audio": audio.name,
                "level": unit["level"],
                "probe_question": unit["probe_question"],
                "expected": unit["expected"],
                "n_probes": unit.get("n_probes", ""),
                "category": unit.get("category", ""),
                "question": unit.get("question", ""),
                "response": response,
                "error": error,
            }
        done[unit["key"]] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        print(f"  [{i}/{len(todo)}] {unit['key']:<32} {rec.get('level',''):<11} "
              f"{'ERR' if rec.get('error') else 'OK'}: "
              f"{(rec.get('response') or rec.get('skipped') or '')[:44]!r}")
    fh.close()
    if hasattr(client, "unload"):
        client.unload()
    return done

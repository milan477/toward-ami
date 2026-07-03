"""Run Audio Flamingo Next on MMAR (in-process, no FastAPI server).

Loads the model exactly as the model card shows — `AutoModel.from_pretrained`
(which, with the AudioFlamingoNext transformers build, returns the
generation-capable class) — applies a small fix to the audio tower's
multi-window timestamp code so clips ≥30s don't crash, queries each MMAR
question in multiple-choice form, parses the chosen letter, and scores it.

Audio is NOT truncated: the >30s "device-side assert" is a genuine bug in the
checkpoint's multi-window path (an empty trailing window indexes out of bounds),
fixed here in `_patch_multiwindow` rather than worked around by trimming audio.

Output files (written to --outdir, default results/mmar/af-next/music/) are
prefixed with the ACTUAL local date-time of the run:
    <YYYY-MM-DD_HH-MM-SS>_comparison.json  — full per-question records + metadata
    <YYYY-MM-DD_HH-MM-SS>_summary.csv      — one row per question (pred vs. gold)
    <YYYY-MM-DD_HH-MM-SS>_report.txt       — human-readable accuracy report

The run is incremental: per-question records are appended to .progress.jsonl in
the output dir so an interrupted run resumes without re-querying.

Usage:
    # 206 pure-music MMAR questions, cleaned data, no truncation:
    python src/scripts/run_mmar_af_next.py \
        --data data/benchmarks/mmar/mmar_cleaned.csv --modality music
    python src/scripts/run_mmar_af_next.py --limit 5   # smoke test
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.helpers.results import git_commit  # noqa: E402
from src.piac.prompts import build_mcq, parse_distractors  # noqa: E402
from src.piac.prompts import extract_letter  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "benchmarks" / "mmar" / "mmar_cleaned.csv"
DEFAULT_OUTDIR = ROOT / "results" / "mmar" / "af-next" / "music"
DEFAULT_FRONTEND_DIR = ROOT / "data" / "af_next"
MAX_TOKENS = 16
DEFAULT_MODEL_ID = "nvidia/audio-flamingo-next-hf"


def _patch_multiwindow(model) -> bool:
    """Fix the audio tower's multi-window timestamp bug in place.

    A clip a hair over 30s yields encoder `post_lengths` like [750, 0] — an
    empty trailing window. Its cumulative offset lands exactly on the audio
    sample boundary, and `searchsorted(..., right=True)` returns an index ==
    num_samples, which is out of bounds when indexing `sample_start_rows` →
    device-side assert. The empty window's rows are masked out downstream, so
    clamping the index to the valid range is harmless; for genuine multi-window
    (≥2 non-empty windows) the clamp is a no-op. Verified byte-identical output
    on ≤30s clips and coherent output on 30s/56s clips.
    """
    import torch

    base = getattr(model, "model", model)
    cls = type(base)
    if getattr(cls, "_multiwindow_patched", False):
        return True

    def _build_audio_timestamps(self, input_ids, post_lengths, max_post_length):
        audio_token_mask = input_ids == self.config.audio_token_id
        diff = torch.diff(torch.nn.functional.pad(audio_token_mask.int(), (1, 1), value=0), dim=1)
        _, starts = torch.where(diff == 1)
        _, ends = torch.where(diff == -1)
        sample_lengths = (ends - starts).to(torch.long)

        audio_embed_frame_step = self.config.audio_frame_step * 4
        frame_offsets = (
            torch.arange(max_post_length, device=post_lengths.device, dtype=torch.float32)
            * audio_embed_frame_step
        )
        cumsum_post = torch.cat(
            [torch.zeros(1, device=post_lengths.device), torch.cumsum(post_lengths, dim=0)[:-1]]
        )
        cumsum_samples = torch.cumsum(sample_lengths, dim=0)
        sample_indices = torch.searchsorted(cumsum_samples, cumsum_post, right=True)
        # FIX: empty trailing window → index == num_samples (out of bounds). Clamp.
        sample_indices = sample_indices.clamp(max=sample_lengths.shape[0] - 1)
        sample_start_rows = torch.searchsorted(
            sample_indices, torch.arange(sample_lengths.shape[0], device=post_lengths.device)
        )
        window_indices = (
            torch.arange(post_lengths.shape[0], device=post_lengths.device)
            - sample_start_rows[sample_indices]
        )
        return window_indices.unsqueeze(1) * max_post_length * audio_embed_frame_step + frame_offsets

    cls._build_audio_timestamps = _build_audio_timestamps
    cls._multiwindow_patched = True
    return True


class DirectFlamingoClient:
    """In-process Audio Flamingo Next, loaded per the model card's AutoModel
    snippet. No HTTP server, so the run survives without a long-lived process.
    """

    name = "flamingo"
    supports_audio = True

    def __init__(self, model_id: str = DEFAULT_MODEL_ID, max_audio_seconds: float | None = None):
        self.model_id = model_id
        self.max_audio_seconds = max_audio_seconds  # None → no truncation
        self._processor = None
        self._model = None
        self._patched = False

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModel, AutoProcessor

            print(f"[direct] loading {self.model_id} …", flush=True)
            self._processor = AutoProcessor.from_pretrained(self.model_id)
            self._model = AutoModel.from_pretrained(
                self.model_id,
                torch_dtype=torch.bfloat16,
                device_map="auto",
            ).eval()
            self._patched = _patch_multiwindow(self._model)
            print(f"[direct] ready on {next(self._model.parameters()).device} "
                  f"(class={type(self._model).__name__}, multiwindow_patch={self._patched})",
                  flush=True)
        return self._processor, self._model

    def info(self) -> dict:
        return {"name": self.name, "model_id": self.model_id,
                "supports_audio": self.supports_audio, "backend": "direct-in-process",
                "multiwindow_patch": True, "audio_truncation": self.max_audio_seconds}

    def _prepare_audio(self, audio_path: str) -> tuple[str, bool]:
        """Return (path, is_temp). Only truncates if max_audio_seconds is set;
        by default audio is passed through untouched (no truncation)."""
        if self.max_audio_seconds is None:
            return audio_path, False
        import soundfile as sf

        info = sf.info(audio_path)
        if info.frames / info.samplerate < self.max_audio_seconds:
            return audio_path, False
        import tempfile
        data, sr = sf.read(audio_path)
        clip = data[: int(self.max_audio_seconds * sr)]
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        sf.write(tmp, clip, sr)
        return tmp, True

    def generate(self, prompt: str, audio_path: str, max_tokens: int = MAX_TOKENS) -> str:
        import os

        import torch

        processor, model = self._load()
        path, is_temp = self._prepare_audio(audio_path)
        try:
            conversation = [[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "audio", "path": path},
                ],
            }]]
            batch = processor.apply_chat_template(
                conversation, tokenize=True, add_generation_prompt=True, return_dict=True,
            ).to(model.device)
            if "input_features" in batch:
                batch["input_features"] = batch["input_features"].to(model.dtype)
            with torch.inference_mode():
                outputs = model.generate(
                    **batch, max_new_tokens=max_tokens, repetition_penalty=1.2,
                )
            prompt_len = batch["input_ids"].shape[1]
            return processor.batch_decode(
                outputs[:, prompt_len:], skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
        finally:
            if is_temp:
                os.unlink(path)


def build_audio_index() -> dict[str, Path]:
    """Map every wav/flac/mp3 basename under data/audio to its path."""
    index: dict[str, Path] = {}
    audio_root = ROOT / "data" / "audio"
    if not audio_root.exists():
        return index
    for p in audio_root.rglob("*"):
        if p.suffix.lower() in (".wav", ".flac", ".mp3", ".m4a", ".ogg"):
            index.setdefault(p.name, p)
    return index


def load_progress(progress_path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if progress_path.exists():
        for line in progress_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rec = json.loads(line)
                done[rec["qid"]] = rec
    return done


def _qid_for(row) -> str:
    """Per-question id used to match AF records to input rows (audio basename)."""
    return row["audio_url"].split("/")[-1].rsplit(".", 1)[0] or str(row.get("audio_url", ""))


def run(data_path: Path, modality: str | None, out_dir: Path,
        max_audio_seconds: float | None, limit: int | None,
        frontend_out: Path | None = None) -> None:
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    df = pd.read_csv(data_path, dtype=str, keep_default_na=False)
    if "benchmark" in df.columns:
        df = df[df["benchmark"] == "mmar"]
    if modality:
        df = df[df["category_1"].str.lower() == modality.lower()]
    df = df.reset_index(drop=True)
    if limit:
        df = df.head(limit)

    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = out_dir / ".progress.jsonl"
    audio_index = build_audio_index()
    client = DirectFlamingoClient(max_audio_seconds=max_audio_seconds)
    info = client.info()
    print(f"Model: {info}")
    print(f"Data: {data_path.name}  modality={modality or 'all'}  "
          f"questions: {len(df)}   audio indexed: {len(audio_index)}")

    done = load_progress(progress_path)
    if done:
        print(f"Resuming: {len(done)} questions already answered.")

    started = datetime.now(timezone.utc).isoformat()
    config = {
        "data": str(data_path.relative_to(ROOT)),
        "benchmark": "mmar",
        "modality_filter": modality,
        "n_questions": len(df),
        "question_form": "mcq",
        "max_tokens": MAX_TOKENS,
        "audio_truncation": max_audio_seconds,  # None = full audio, no truncation
        "multiwindow_patch": True,
        "model_load": "AutoModel.from_pretrained(..., torch_dtype=bfloat16, device_map=auto)",
        "instruction": build_mcq("Q", "C", ["D"], "seed")["prompt"].split("\n\nQuestion")[0],
    }

    progress_fh = progress_path.open("a", encoding="utf-8")
    n_new = 0
    for _, r in df.iterrows():
        qid = _qid_for(r)
        if qid in done:
            continue

        audio = audio_index.get(r["audio_url"].split("/")[-1])
        if audio is None:
            rec = {"qid": qid, "question": r["question"], "audio": None, "skipped": "no_audio"}
            done[qid] = rec
            progress_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            progress_fh.flush()
            continue

        distractors = parse_distractors(r["distractors"])
        mcq = build_mcq(r["question"], r["correct_answer"], distractors, qid)
        fatal = False
        try:
            resp = client.generate(mcq["prompt"], str(audio), max_tokens=MAX_TOKENS)
            pred = extract_letter(resp, mcq["letter_map"])
            correct = pred == mcq["correct_letter"]
            err = None
        except Exception as exc:  # keep going; record the failure
            resp, pred, correct, err = "", None, False, str(exc)[:300]
            # A device-side assert poisons the CUDA context — record this qid (so
            # a restart quarantines it) and exit with a sentinel to restart.
            fatal = "device-side assert" in err or "CUDA error" in err

        rec = {
            "qid": qid, "question": r["question"], "audio": audio.name,
            "category_1": r["category_1"], "category_2": r["category_2"],
            "category_3": r["category_3"], "options": mcq["options"],
            "letter_map": mcq["letter_map"], "correct_answer": mcq["correct_answer"],
            "correct_letter": mcq["correct_letter"], "prompt": mcq["prompt"],
            "response": resp, "pred_letter": pred,
            "pred_answer": mcq["letter_map"].get(pred) if pred else None,
            "correct": correct, "error": err,
        }
        done[qid] = rec
        progress_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        progress_fh.flush()
        n_new += 1
        mark = "OK" if err is None else "ERR"
        tick = "✓" if correct else "✗"
        print(f"  [{n_new}] {qid[:28]:<28} {mark} {tick} pred={pred} gold={mcq['correct_letter']}")
        if fatal:
            progress_fh.close()
            print(f"FATAL CUDA error on {qid}; quarantined. Restart to resume.", flush=True)
            raise SystemExit(75)

    progress_fh.close()
    finished = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # ACTUAL local run date-time

    records = [done[q] for q in done]
    answered = [r for r in records if not r.get("skipped")]
    n_correct = sum(1 for r in answered if r.get("correct"))
    n_total = len(answered)
    acc = n_correct / n_total if n_total else 0.0

    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in answered:
        cat = r.get("category_2") or "(uncategorized)"
        by_cat[cat][0] += int(bool(r.get("correct")))
        by_cat[cat][1] += 1

    metadata = {
        "experiment": "mmar_af_next_music",
        "benchmark": "mmar",
        "model": info,
        "config": config,
        "git_commit": git_commit(),
        "run_started": started,
        "run_finished": finished,
        "run_local_datetime": stamp,
    }
    summary = {
        "n_questions_total": len(records),
        "n_answered": n_total,
        "n_skipped_no_audio": sum(1 for r in records if r.get("skipped") == "no_audio"),
        "n_errors": sum(1 for r in records if r.get("error")),
        "n_correct": n_correct,
        "accuracy": round(acc, 4),
    }

    _write_comparison(out_dir, stamp, metadata, summary, records)
    _write_summary_csv(out_dir, stamp, records)
    _write_report(out_dir, stamp, metadata, summary, by_cat)
    if frontend_out is not None:
        _write_frontend_csv(frontend_out, df, done)

    print(f"\nDone. accuracy {acc:.1%}  ({n_correct}/{n_total})")
    print(f"Wrote results to {out_dir} (prefix {stamp})")


def _write_comparison(out_dir, stamp, metadata, summary, records) -> None:
    payload = {**metadata, "summary": summary, "items": records}
    (out_dir / f"{stamp}_comparison.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_summary_csv(out_dir, stamp, records) -> None:
    cols = ["qid", "category_1", "category_2", "category_3", "question",
            "correct_answer", "correct_letter", "pred_letter", "pred_answer",
            "response", "correct", "skipped", "error"]
    with (out_dir / f"{stamp}_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in records:
            row = dict(r)
            row["response"] = (r.get("response") or "").replace("\n", " ").strip()
            w.writerow(row)


def _write_frontend_csv(out_path: Path, df: pd.DataFrame, done: dict[str, dict]) -> None:
    """Write a renderers/server/server.py-viewable CSV: the full input rows (normalized
    schema + any annotation columns like `category`/`answer_format`) joined with
    AF-Next's prediction, so the run can be browsed with audio in the question
    browser. The input's own `qid` (if present) is preserved untouched."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, r in df.iterrows():
        rec = done.get(_qid_for(r), {})
        row = r.to_dict()
        row["af_pred_letter"] = rec.get("pred_letter") or ""
        row["af_pred_answer"] = rec.get("pred_answer") or ""
        row["af_correct"] = "" if (not rec or rec.get("skipped")) else str(bool(rec.get("correct"))).lower()
        row["af_response"] = (rec.get("response") or "").replace("\n", " ").strip()
        row["af_error"] = rec.get("error") or ""
        rows.append(row)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"Wrote frontend-viewable CSV → {out_path}")
    print(f"  browse it:  python renderers/server/server.py --data-dir {out_path.parent.relative_to(ROOT)}")


def _write_report(out_dir, stamp, metadata, summary, by_cat) -> None:
    cfg = metadata["config"]
    trunc = cfg["audio_truncation"]
    lines = [
        "Audio Flamingo Next — MMAR music subset (MCQ)",
        "=" * 52,
        f"Model:        {metadata['model'].get('model_id')}",
        f"Load:         {cfg['model_load']}",
        f"Git commit:   {metadata['git_commit']}",
        f"Run datetime: {metadata['run_local_datetime']} (local)",
        f"Run started:  {metadata['run_started']}",
        f"Run finished: {metadata['run_finished']}",
        f"Modality:     {cfg['modality_filter'] or 'all'}",
        f"Audio:        {'no truncation (full clips); multi-window bug patched' if trunc is None else f'truncated to {trunc}s'}",
        "",
        "Overall",
        "-" * 52,
        f"  questions (total):   {summary['n_questions_total']}",
        f"  answered:            {summary['n_answered']}",
        f"  skipped (no audio):  {summary['n_skipped_no_audio']}",
        f"  errors:              {summary['n_errors']}",
        f"  correct:             {summary['n_correct']}",
        f"  accuracy:            {summary['accuracy']:.2%}",
        "",
        "Accuracy by category (Layer)",
        "-" * 52,
    ]
    for cat, (corr, tot) in sorted(by_cat.items(), key=lambda kv: -kv[1][1]):
        a = corr / tot if tot else 0.0
        lines.append(f"  {cat:<32} {corr:>4}/{tot:<4}  {a:6.2%}")
    (out_dir / f"{stamp}_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=str(DEFAULT_DATA),
                    help="CSV to read (default: data/benchmarks/mmar/mmar_cleaned.csv)")
    ap.add_argument("--modality", default="music",
                    help="filter category_1 == this (default: music; '' for all)")
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR),
                    help="output directory (default: results/mmar/af-next/music)")
    ap.add_argument("--max-audio-seconds", type=float, default=None,
                    help="truncate clips to N seconds (default: None = no truncation)")
    ap.add_argument("--limit", type=int, default=None, help="only first N questions")
    ap.add_argument("--frontend-out", default=None,
                    help="also write a renderers/server/server.py-viewable CSV here "
                         f"(default: {DEFAULT_FRONTEND_DIR.relative_to(ROOT)}/<input>.csv; "
                         "pass '' to skip)")
    args = ap.parse_args()
    if args.frontend_out is None:
        frontend_out = DEFAULT_FRONTEND_DIR / Path(args.data).name
    elif args.frontend_out == "":
        frontend_out = None
    else:
        frontend_out = Path(args.frontend_out)
    run(Path(args.data), args.modality or None, Path(args.outdir),
        args.max_audio_seconds, args.limit, frontend_out)


if __name__ == "__main__":
    main()

"""AF-Next open-ended (OEQ) on MMAR music subset, judged by local Qwen.

Two phases (the 4090 can't hold both models at once, so they run in sequence):

  1. AF-Next answers each question open-ended (free text, no options), with audio.
     Reuses DirectFlamingoClient + the multi-window patch from run_mmar_af_next.
     When the input has `answer_format` / `example_answer` columns (e.g.
     data/benchmarks/mmar/mmar_ready.csv), the OEQ prompt includes the answer style and a
     format example (an incorrect answer, so the correct one is never leaked).
  2. Qwen2.5-7B-Instruct grades each answer against the reference on an integer
     0-4 scale; the score is normalized to 0-1 (score / 4).

Each phase is resumable (.oeq_answers.jsonl / .oeq_judged.jsonl in the out dir).

Outputs (prefixed with the ACTUAL local run date-time), in
results/mmar/af-next/music-oeq/ :
    <stamp>_comparison.json   — per-question answer + judge score (0-4 and 0-1)
    <stamp>_summary.csv       — one row per question
    <stamp>_report.txt        — mean normalized score overall + by category

Usage:
    python src/scripts/run_mmar_af_next_oeq.py            # 206 music q
    python src/scripts/run_mmar_af_next_oeq.py --limit 5  # smoke test
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.helpers.results import git_commit  # noqa: E402
from src.piac.prompts import build_oeq  # noqa: E402
from run_mmar_af_next import DirectFlamingoClient, build_audio_index  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "benchmarks" / "mmar" / "mmar_cleaned.csv"
DEFAULT_OUTDIR = ROOT / "results" / "mmar" / "af-next" / "music-oeq"
OEQ_MAX_TOKENS = 192
JUDGE_MODEL = "Qwen/Qwen3-8B"
JUDGE_MAX_TOKENS = 160
SCORE_MAX = 4  # judge scale is 0..SCORE_MAX, normalized to 0..1

JUDGE_PROMPT = """You are grading a model's open-ended answer to a question about an audio clip.

Question: {question}
Reference answer (ground truth): {reference}
Model's answer: {answer}

Score how well the model's answer matches the reference answer, on an integer scale 0-4:
0 = wrong, irrelevant, or no answer
1 = mostly wrong; only a slight or incidental overlap
2 = partially correct; a MULTI-PART answer that gets some required parts but misses others
3 = largely correct; all key content present, only minor wording differences
4 = fully correct and complete

Grading rules (apply strictly):
- A single number or single discrete value (a count, a note, yes/no, one name, one word) is
  either right or wrong: 4 if it matches the reference, 0 if it does not. NEVER give partial
  credit for a close-but-wrong value — e.g. answering 20 when the reference is 26 scores 0.
- Ignore extra information: if the answer contains everything the reference requires PLUS
  additional details, do not penalize the extra — that is still 4.
- "Partially correct" (2) applies ONLY when the reference has several required parts and the
  answer is incomplete (some parts right, some missing) — never to a single value that is merely close.
- Judge meaning, not wording: accept synonyms and paraphrases of the reference.

Reply with ONLY a JSON object: {{"score": <integer 0-4>, "rationale": "<one short sentence>"}}"""


class QwenJudge:
    """Local Qwen2.5-Instruct text-only judge."""

    def __init__(self, model_id: str = JUDGE_MODEL):
        self.model_id = model_id
        self._tok = None
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            print(f"[judge] loading {self.model_id} …", flush=True)
            self._tok = AutoTokenizer.from_pretrained(self.model_id)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_id, torch_dtype=torch.bfloat16, device_map="auto",
            ).eval()
            print(f"[judge] ready on {next(self._model.parameters()).device}", flush=True)
        return self._tok, self._model

    def score(self, question: str, reference: str, answer: str) -> dict:
        import torch

        tok, model = self._load()
        prompt = JUDGE_PROMPT.format(question=question, reference=reference,
                                     answer=answer or "(no answer)")
        messages = [
            {"role": "system", "content": "You are a strict, fair grader. Reply only with the requested JSON."},
            {"role": "user", "content": prompt},
        ]
        enc = tok.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt", return_dict=True,
            enable_thinking=False,  # Qwen3: no <think> blocks, keep JSON-only output
        ).to(model.device)
        with torch.inference_mode():
            out = model.generate(**enc, max_new_tokens=JUDGE_MAX_TOKENS, do_sample=False)
        text = tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        return parse_judge(text)


def parse_judge(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    raw = m.group() if m else None
    score = None
    rationale = text.strip()[:200]
    if raw:
        try:
            obj = json.loads(raw)
            score = obj.get("score")
            rationale = str(obj.get("rationale", ""))[:300]
        except json.JSONDecodeError:
            pass
    if score is None:  # fallback: first standalone 0-4 digit
        d = re.search(r"\b([0-4])\b", text)
        score = int(d.group(1)) if d else None
    try:
        score = int(round(float(score)))
        score = max(0, min(SCORE_MAX, score))
    except (TypeError, ValueError):
        score = None
    norm = round(score / SCORE_MAX, 4) if score is not None else None
    return {"score": score, "score_norm": norm, "rationale": rationale,
            "raw": text.strip()[:300]}


def _read_jsonl(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["qid"]] = rec
    return out


def _free_gpu(client) -> None:
    import torch

    client._model = None
    client._processor = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def phase1_answers(df, audio_index, ans_path: Path) -> dict[str, dict]:
    done = _read_jsonl(ans_path)
    todo = [r for _, r in df.iterrows()
            if (r["audio_url"].split("/")[-1].rsplit(".", 1)[0]) not in done]
    if not todo:
        print(f"[phase1] all {len(done)} OEQ answers present; skipping generation.")
        return done

    client = DirectFlamingoClient(max_audio_seconds=None)  # no truncation
    print(f"[phase1] AF-Next OEQ: {len(todo)} to answer ({len(done)} cached)")
    fh = ans_path.open("a", encoding="utf-8")
    for i, r in enumerate(todo, 1):
        qid = r["audio_url"].split("/")[-1].rsplit(".", 1)[0]
        audio = audio_index.get(r["audio_url"].split("/")[-1])
        answer_format = r.get("answer_format", "")
        example = r.get("example_answer", "")
        oeq = build_oeq(r["question"], r["correct_answer"],
                        answer_format=answer_format, example=example)
        if audio is None:
            rec = {"qid": qid, "skipped": "no_audio"}
        else:
            try:
                resp = client.generate(oeq["prompt"], str(audio), max_tokens=OEQ_MAX_TOKENS)
                err = None
            except Exception as exc:
                resp, err = "", str(exc)[:300]
            rec = {
                "qid": qid, "question": r["question"], "audio": audio.name,
                "category_1": r["category_1"], "category_2": r["category_2"],
                "category_3": r["category_3"], "category": r.get("category", ""),
                "reference_answer": r["correct_answer"],
                "answer_format": answer_format, "example_answer": example,
                "prompt": oeq["prompt"], "response": resp, "error": err,
            }
        done[qid] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        print(f"  [{i}/{len(todo)}] {qid[:26]:<26} {'ERR' if rec.get('error') else 'OK'}: "
              f"{(rec.get('response') or rec.get('skipped') or '')[:50]!r}")
    fh.close()
    _free_gpu(client)
    return done


def phase2_judge(answers: dict[str, dict], judged_path: Path) -> dict[str, dict]:
    done = _read_jsonl(judged_path)
    todo = [qid for qid, a in answers.items()
            if qid not in done and not a.get("skipped")]
    if not todo:
        print(f"[phase2] all judged ({len(done)} present); skipping.")
        return done

    judge = QwenJudge()
    print(f"[phase2] Qwen judging: {len(todo)} answers ({len(done)} cached)")
    fh = judged_path.open("a", encoding="utf-8")
    for i, qid in enumerate(todo, 1):
        a = answers[qid]
        verdict = judge.score(a["question"], a["reference_answer"], a.get("response", ""))
        rec = {"qid": qid, **verdict}
        done[qid] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        print(f"  [{i}/{len(todo)}] {qid[:26]:<26} score={verdict['score']} "
              f"norm={verdict['score_norm']}")
    fh.close()
    return done


def run(data_path: Path, modality: str | None, out_dir: Path, limit: int | None) -> None:
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
    audio_index = build_audio_index()
    started = datetime.now(timezone.utc).isoformat()
    print(f"Data: {data_path.name}  modality={modality or 'all'}  questions: {len(df)}")

    answers = phase1_answers(df, audio_index, out_dir / ".oeq_answers.jsonl")
    judged = phase2_judge(answers, out_dir / ".oeq_judged.jsonl")

    finished = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Merge answers + judgements into per-question records, in df order.
    records = []
    for _, r in df.iterrows():
        qid = r["audio_url"].split("/")[-1].rsplit(".", 1)[0]
        a = answers.get(qid, {"qid": qid})
        j = judged.get(qid, {})
        records.append({**a, "judge_score": j.get("score"),
                        "judge_score_norm": j.get("score_norm"),
                        "judge_rationale": j.get("rationale")})

    scored = [r for r in records if r.get("judge_score_norm") is not None]
    mean_norm = sum(r["judge_score_norm"] for r in scored) / len(scored) if scored else 0.0
    by_cat = defaultdict(list)
    for r in scored:
        by_cat[r.get("category_2") or "(uncategorized)"].append(r["judge_score_norm"])
    by_piac = defaultdict(list)
    for r in scored:
        by_piac[r.get("category") or "(unclassified)"].append(r["judge_score_norm"])
    dist = defaultdict(int)
    for r in scored:
        dist[r["judge_score"]] += 1

    metadata = {
        "experiment": "mmar_af_next_oeq_music",
        "benchmark": "mmar",
        "answer_model": "nvidia/audio-flamingo-next-hf",
        "judge_model": JUDGE_MODEL,
        "config": {
            "data": str(data_path.relative_to(ROOT)),
            "modality_filter": modality, "question_form": "oeq",
            "n_questions": len(df), "oeq_max_tokens": OEQ_MAX_TOKENS,
            "audio_truncation": None, "multiwindow_patch": True,
            "judge_scale": f"0-{SCORE_MAX}", "normalization": f"score / {SCORE_MAX}",
            "judge_max_tokens": JUDGE_MAX_TOKENS,
        },
        "git_commit": git_commit(),
        "run_started": started, "run_finished": finished, "run_local_datetime": stamp,
    }
    summary = {
        "n_questions": len(records),
        "n_answered": sum(1 for r in records if not r.get("skipped")),
        "n_judged": len(scored),
        "n_skipped_no_audio": sum(1 for r in records if r.get("skipped") == "no_audio"),
        "mean_score_0_4": round(mean_norm * SCORE_MAX, 4),
        "mean_score_norm": round(mean_norm, 4),
        "score_distribution_0_4": {str(k): dist[k] for k in sorted(dist)},
        "mean_score_norm_by_piac": {
            k: round(sum(v) / len(v), 4) for k, v in by_piac.items()
        },
    }

    _write_comparison(out_dir, stamp, metadata, summary, records)
    _write_summary_csv(out_dir, stamp, records)
    _write_report(out_dir, stamp, metadata, summary, by_cat, by_piac)
    print(f"\nDone. mean normalized score {mean_norm:.3f} "
          f"({mean_norm * SCORE_MAX:.2f}/4 over {len(scored)} judged)")
    print(f"Wrote results to {out_dir} (prefix {stamp})")


def _write_comparison(out_dir, stamp, metadata, summary, records) -> None:
    (out_dir / f"{stamp}_comparison.json").write_text(
        json.dumps({**metadata, "summary": summary, "items": records},
                   indent=2, ensure_ascii=False), encoding="utf-8")


def _write_summary_csv(out_dir, stamp, records) -> None:
    cols = ["qid", "category", "category_1", "category_2", "category_3", "question",
            "answer_format", "example_answer", "prompt", "reference_answer", "response",
            "judge_score", "judge_score_norm", "judge_rationale", "skipped", "error"]
    with (out_dir / f"{stamp}_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in records:
            row = dict(r)
            row["response"] = (r.get("response") or "").replace("\n", " ").strip()
            w.writerow(row)


PIAC_ORDER = ["perceptual", "inferential", "affective", "contextual"]


def _write_report(out_dir, stamp, metadata, summary, by_cat, by_piac) -> None:
    cfg = metadata["config"]
    lines = [
        "Audio Flamingo Next — MMAR music subset (OEQ, Qwen-judged)",
        "=" * 58,
        f"Answer model: {metadata['answer_model']}",
        f"Judge model:  {metadata['judge_model']}",
        f"Judge scale:  {cfg['judge_scale']}  →  normalized {cfg['normalization']}",
        f"Git commit:   {metadata['git_commit']}",
        f"Run datetime: {metadata['run_local_datetime']} (local)",
        f"Modality:     {cfg['modality_filter'] or 'all'}   audio: no truncation",
        "",
        "Overall",
        "-" * 58,
        f"  questions:           {summary['n_questions']}",
        f"  answered:            {summary['n_answered']}",
        f"  judged:              {summary['n_judged']}",
        f"  skipped (no audio):  {summary['n_skipped_no_audio']}",
        f"  mean score (0-4):    {summary['mean_score_0_4']:.3f}",
        f"  mean score (0-1):    {summary['mean_score_norm']:.4f}",
        f"  score distribution:  {summary['score_distribution_0_4']}",
        "",
        "Mean normalized score by PIAC category",
        "-" * 58,
    ]
    ordered = sorted(by_piac.items(),
                     key=lambda kv: PIAC_ORDER.index(kv[0]) if kv[0] in PIAC_ORDER else 99)
    for cat, vals in ordered:
        lines.append(f"  {cat:<32} {sum(vals) / len(vals):.4f}  (n={len(vals)})")
    lines += ["", "Mean normalized score by category (MMAR Layer)", "-" * 58]
    for cat, vals in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {cat:<32} {sum(vals) / len(vals):.4f}  (n={len(vals)})")
    (out_dir / f"{stamp}_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--modality", default="music", help="filter category_1 (default music)")
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run(Path(args.data), args.modality or None, Path(args.outdir), args.limit)


if __name__ == "__main__":
    main()

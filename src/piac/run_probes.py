"""STEP 4b — run AF-Next against the DECOMPOSED probe chains, judged per PIAC level.

Each processed question carries an ordered `probes` chain (see decompose.py):
perceptual → … → the question's target level, each probe an atomic sub-question with
an `expected` answer. This runner asks AF-Next EVERY probe (with audio, open-ended) and
judges each answer against its `expected` using the probe's PIAC-level rubric — so we can
see WHERE in the chain understanding breaks, not just whether the final answer is right.

Two phases (sequential; the 4090 holds one model at a time):
  1. AF-Next answers every probe with audio (reuses DirectFlamingoClient + multi-window
     patch; no truncation). Resumable via .probe_answers.jsonl (key "<qid>#<idx>").
  2. PIACJudge grades each probe answer vs its expected answer, applying the probe level's
     rubric (perceptual/contextual/inferential → binary; affective → graded) + hallucination.
     Resumable via .probe_judged.jsonl.

Reports (datetime-prefixed) in results/mmar/af-next/music-probes/ :
    <stamp>_comparison.json  — per-probe records + per-question chains + metadata
    <stamp>_summary.csv      — one row per PROBE
    <stamp>_report.txt       — accuracy per PIAC level + chain diagnostics

Chain diagnostics answer the study question: when the FINAL answer is right/wrong, was the
PERCEPTUAL base underneath it right? (fluent higher-level answers on broken perceptual ground).

    python -m src.piac.run_probes            # full 206 (all probes)
    python -m src.piac.run_probes --limit 20 # POC gate (first 20 questions)
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
sys.path.insert(0, str(ROOT / "src" / "scripts"))

from src.helpers.results import git_commit  # noqa: E402
from src.piac.prompts import INSTRUCTION_OEQ_GUIDED  # noqa: E402
from src.piac.judge import PIACJudge  # noqa: E402
from src.piac.taxonomy import PIAC_ORDER  # noqa: E402
from run_mmar_af_next_oeq import (  # noqa: E402
    OEQ_MAX_TOKENS, DirectFlamingoClient, _free_gpu, _read_jsonl, build_audio_index,
)

DEFAULT_DATA = ROOT / "data" / "benchmarks" / "mmar" / "mmar_ready.csv"
DEFAULT_OUTDIR = ROOT / "results" / "mmar" / "af-next" / "music-probes"


def _stem(audio_url: str) -> str:
    return audio_url.split("/")[-1].rsplit(".", 1)[0]


def _probe_key(qid: str, idx: int) -> str:
    return f"{qid}#{idx}"


def _probe_prompt(probe_question: str) -> str:
    """Ask a single probe open-ended, with audio. No answer_format/example: probes are
    atomic sub-questions and their `expected` must not leak into the prompt."""
    return f"{INSTRUCTION_OEQ_GUIDED}\n\nQuestion: {probe_question}"


def _iter_probes(df):
    """Yield (row, idx, probe) for every probe of every question, in chain order."""
    for _, r in df.iterrows():
        try:
            probes = json.loads(r.get("probes") or "[]")
        except json.JSONDecodeError:
            probes = []
        for idx, p in enumerate(probes):
            if isinstance(p, dict) and p.get("question"):
                yield r, idx, p


def phase1_probe_answers(df, audio_index, ans_path: Path) -> dict[str, dict]:
    done = _read_jsonl(ans_path)
    todo = [(r, idx, p) for r, idx, p in _iter_probes(df)
            if _probe_key(_stem(r["audio_url"]), idx) not in done]
    if not todo:
        print(f"[phase1] all {len(done)} probe answers present; skipping generation.")
        return done

    client = DirectFlamingoClient(max_audio_seconds=None)
    print(f"[phase1] AF-Next answering {len(todo)} probes ({len(done)} cached)")
    fh = ans_path.open("a", encoding="utf-8")
    for i, (r, idx, p) in enumerate(todo, 1):
        qid = _stem(r["audio_url"])
        key = _probe_key(qid, idx)
        audio = audio_index.get(r["audio_url"].split("/")[-1])
        if audio is None:
            rec = {"key": key, "qid": qid, "probe_idx": idx, "skipped": "no_audio"}
        else:
            try:
                resp = client.generate(_probe_prompt(p["question"]), str(audio),
                                       max_tokens=OEQ_MAX_TOKENS)
                err = None
            except Exception as exc:
                resp, err = "", str(exc)[:300]
            rec = {
                "key": key, "qid": qid, "probe_idx": idx, "audio": audio.name,
                "level": p.get("level", ""), "probe_question": p["question"],
                "expected": p.get("expected", ""), "n_probes": r.get("n_probes", ""),
                "category": r.get("category", ""), "question": r.get("question", ""),
                "response": resp, "error": err,
            }
        done[key] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        print(f"  [{i}/{len(todo)}] {key:<32} {rec.get('level',''):<11} "
              f"{'ERR' if rec.get('error') else 'OK'}: {(rec.get('response') or rec.get('skipped') or '')[:44]!r}")
    fh.close()
    _free_gpu(client)
    return done


def phase2_probe_judge(answers: dict[str, dict], judged_path: Path) -> dict[str, dict]:
    done = _read_jsonl(judged_path)
    todo = [k for k, a in answers.items() if k not in done and not a.get("skipped")]
    if not todo:
        print(f"[phase2] all judged ({len(done)} present); skipping.")
        return done
    judge = PIACJudge()
    print(f"[phase2] PIAC judging {len(todo)} probe answers with {judge.model_id}")
    fh = judged_path.open("a", encoding="utf-8")
    for i, key in enumerate(todo, 1):
        a = answers[key]
        # Grade the probe answer vs its expected answer, using the PROBE's level rubric.
        v = judge.score(a.get("level", ""), a["probe_question"], a.get("expected", ""),
                        a.get("response", ""))
        rec = {"key": key, **v}
        done[key] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        h = "HALL" if v["hallucinated"] else "    "
        print(f"  [{i}/{len(todo)}] {key:<32} {a.get('level',''):<11} "
              f"score={v['score']} norm={v['score_norm']} {h}")
    fh.close()
    return done


def run(data_path: Path, out_dir: Path, limit: int | None) -> None:
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    df = pd.read_csv(data_path, dtype=str, keep_default_na=False)
    df = df[df["category_1"].str.lower() == "music"].reset_index(drop=True)
    if "probes" not in df.columns:
        raise SystemExit("No `probes` column. Run: python -m src.piac.decompose mmar")
    if limit:
        df = df.head(limit)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_index = build_audio_index()
    started = datetime.now(timezone.utc).isoformat()
    n_probes = sum(1 for _ in _iter_probes(df))
    print(f"Data: {data_path.name}  questions: {len(df)}  probes: {n_probes}")

    answers = phase1_probe_answers(df, audio_index, out_dir / ".probe_answers.jsonl")
    judged = phase2_probe_judge(answers, out_dir / ".probe_judged.jsonl")

    finished = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Per-probe records, in chain order.
    records = []
    for r, idx, p in _iter_probes(df):
        qid = _stem(r["audio_url"])
        key = _probe_key(qid, idx)
        a = answers.get(key, {})
        j = judged.get(key, {})
        records.append({
            "qid": qid, "probe_idx": idx, "level": p.get("level", ""),
            "target_category": r.get("category", ""), "question": r.get("question", ""),
            "probe_question": p.get("question", ""), "expected": p.get("expected", ""),
            "response": (a.get("response") or "").replace("\n", " ").strip(),
            "judge_score": j.get("score"), "judge_score_norm": j.get("score_norm"),
            "verdict": j.get("verdict"), "hallucinated": j.get("hallucinated"),
            "skipped": a.get("skipped"), "error": a.get("error"),
        })

    scored = [r for r in records if r.get("judge_score_norm") is not None]
    # Per-level accuracy (binary correct = score_norm == 1.0; for affective use mean score).
    by_level_correct = defaultdict(list)
    by_level_score = defaultdict(list)
    for r in scored:
        by_level_correct[r["level"]].append(1 if r["judge_score_norm"] == 1.0 else 0)
        by_level_score[r["level"]].append(r["judge_score_norm"])

    # Chain diagnostic: per question, is the FINAL probe right, and is the FIRST
    # (perceptual base) probe right? Cross-tabulate.
    chains = defaultdict(list)
    for r in scored:
        chains[r["qid"]].append(r)
    quad = defaultdict(int)  # (base_ok, final_ok) -> count
    base_correct = final_correct = 0
    n_chains = 0
    for qid, probes in chains.items():
        probes = sorted(probes, key=lambda x: x["probe_idx"])
        if not probes:
            continue
        n_chains += 1
        base_ok = probes[0]["judge_score_norm"] == 1.0
        final_ok = probes[-1]["judge_score_norm"] == 1.0
        base_correct += base_ok
        final_correct += final_ok
        quad[(base_ok, final_ok)] += 1

    metadata = {
        "experiment": "mmar_af_next_probes",
        "answer_model": "nvidia/audio-flamingo-next-hf",
        "judge_model": "Qwen/Qwen3-8B (local, PIAC per-probe-level)",
        "config": {"data": str(data_path.relative_to(ROOT)), "unit": "probe",
                   "n_questions": len(df), "n_probes": n_probes,
                   "audio_truncation": None},
        "git_commit": git_commit(), "run_started": started, "run_finished": finished,
        "run_local_datetime": stamp,
    }
    summary = {
        "n_questions": len(df), "n_probes": len(records), "n_judged": len(scored),
        "accuracy_by_level": {
            lv: round(sum(v) / len(v), 4) for lv, v in by_level_correct.items()},
        "mean_score_by_level": {
            lv: round(sum(v) / len(v), 4) for lv, v in by_level_score.items()},
        "n_by_level": {lv: len(v) for lv, v in by_level_correct.items()},
        "chain": {
            "n_chains": n_chains,
            "perceptual_base_correct": round(base_correct / n_chains, 4) if n_chains else 0,
            "final_correct": round(final_correct / n_chains, 4) if n_chains else 0,
            "base_ok_final_ok": quad[(True, True)],
            "base_ok_final_wrong": quad[(True, False)],
            "base_wrong_final_ok": quad[(False, True)],
            "base_wrong_final_wrong": quad[(False, False)],
        },
    }

    _write_comparison(out_dir, stamp, metadata, summary, records)
    _write_summary_csv(out_dir, stamp, records)
    _write_report(out_dir, stamp, metadata, summary)
    print(f"\nDone. {len(scored)} probes judged over {n_chains} chains.")
    print("Accuracy by level:", summary["accuracy_by_level"])
    print(f"Wrote results to {out_dir} (prefix {stamp})")


def _write_comparison(out_dir, stamp, metadata, summary, records) -> None:
    (out_dir / f"{stamp}_comparison.json").write_text(
        json.dumps({**metadata, "summary": summary, "items": records},
                   indent=2, ensure_ascii=False), encoding="utf-8")


def _write_summary_csv(out_dir, stamp, records) -> None:
    cols = ["qid", "probe_idx", "level", "target_category", "question", "probe_question",
            "expected", "response", "judge_score", "judge_score_norm", "verdict",
            "hallucinated", "skipped", "error"]
    with (out_dir / f"{stamp}_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)


def _write_report(out_dir, stamp, metadata, summary) -> None:
    cfg = metadata["config"]
    acc = summary["accuracy_by_level"]
    ms = summary["mean_score_by_level"]
    nb = summary["n_by_level"]
    ch = summary["chain"]
    lines = [
        "Audio Flamingo Next — MMAR music, DECOMPOSED PROBE chains (PIAC per-level)",
        "=" * 66,
        f"Answer model: {metadata['answer_model']}",
        f"Judge model:  {metadata['judge_model']}",
        f"Git commit:   {metadata['git_commit']}",
        f"Run datetime: {metadata['run_local_datetime']} (local)",
        f"Questions: {cfg['n_questions']}   probes: {cfg['n_probes']}   "
        f"judged: {summary['n_judged']}",
        "",
        "Accuracy by PIAC probe level  (correct = judge score 4/4; affective also shows mean)",
        "-" * 66,
    ]
    for lv in PIAC_ORDER:
        if lv in acc:
            extra = f"   mean {ms[lv]:.2f}" if lv == "affective" else ""
            lines.append(f"  {lv:<14} {acc[lv]:6.1%}   (n={nb[lv]}){extra}")
    lines += [
        "",
        "Chain diagnostic — does the FINAL answer rest on a correct PERCEPTUAL base?",
        "-" * 66,
        f"  chains analysed:            {ch['n_chains']}",
        f"  perceptual base correct:    {ch['perceptual_base_correct']:.1%}",
        f"  final (target) correct:     {ch['final_correct']:.1%}",
        "",
        f"  base ✓ & final ✓:           {ch['base_ok_final_ok']:>4}   (grounded success)",
        f"  base ✓ & final ✗:           {ch['base_ok_final_wrong']:>4}   (lost it higher up)",
        f"  base ✗ & final ✓:           {ch['base_wrong_final_ok']:>4}   (right answer, wrong ground = "
        "hallucinated/guessed)",
        f"  base ✗ & final ✗:           {ch['base_wrong_final_wrong']:>4}   (broken from the base)",
    ]
    (out_dir / f"{stamp}_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    ap.add_argument("--limit", type=int, default=None, help="first N questions (POC)")
    args = ap.parse_args()
    run(Path(args.data), Path(args.outdir), args.limit)


if __name__ == "__main__":
    main()

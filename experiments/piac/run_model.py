"""Run ANY make_client model spec (e.g. openrouter:google/gemini-3-flash-preview) on
the MMAR music set, in both MCQ and OEQ form, and PIAC-judge the OEQ answers.

Mirrors the AF-Next runners but for audio-capable API models (Gemini, GPT-4o-audio, …):
answers come from the API (no local GPU), then the local Qwen3 PIAC judge grades the OEQ
answers. Everything is reused: build_mcq / build_oeq / extract_letter (oeq_mcq), PIACJudge
(piac.judge), make_client (helpers.models). Outputs match the AF-Next schema so
`experiments.piac.analyze --oeq <…> --mcq <…>` works unchanged.

    OPENROUTER_API_KEY=... python -m experiments.piac.run_model \
        --model openrouter:google/gemini-3-flash-preview
    ... --limit 5     # smoke test

Writes results/mmar/<model-slug>/music/<stamp>_*  (MCQ) and
       results/mmar/<model-slug>/music-oeq-piac/<stamp>_*  (OEQ, PIAC-judged).
Resumable per phase via hidden .jsonl caches.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "scripts"))

from experiments.helpers.models import make_client  # noqa: E402
from experiments.helpers.results import git_commit  # noqa: E402
from experiments.oeq_mcq.prompts import build_mcq, build_oeq, parse_distractors  # noqa: E402
from experiments.oeq_mcq.run import extract_letter  # noqa: E402
from experiments.piac.judge import PIACJudge  # noqa: E402
from experiments.piac.taxonomy import PIAC_ORDER  # noqa: E402
from run_mmar_af_next import build_audio_index  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "processed" / "mmar.csv"
MCQ_MAX_TOKENS = 16
OEQ_MAX_TOKENS = 192
RETRIES = 3


def _stem(audio_url: str) -> str:
    return audio_url.split("/")[-1].rsplit(".", 1)[0]


def _slug(spec: str) -> str:
    return spec.split(":", 1)[-1].split("/")[-1]


def _read_jsonl(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["qid"]] = rec
    return out


def _generate(client, prompt, audio, max_tokens):
    """One API call with a few retries for transient errors."""
    last = None
    for attempt in range(RETRIES):
        try:
            return client.generate(prompt, str(audio), max_tokens=max_tokens), None
        except Exception as exc:  # noqa: BLE001
            last = str(exc)[:300]
            time.sleep(0)  # no foreground sleep; immediate retry
    return "", last


def phase_answers(df, audio_index, client, cache: Path, form: str) -> dict[str, dict]:
    done = _read_jsonl(cache)
    todo = [r for _, r in df.iterrows() if _stem(r["audio_url"]) not in done]
    if not todo:
        print(f"[{form}] all {len(done)} answers present; skipping.")
        return done
    print(f"[{form}] {client.model_id}: {len(todo)} to answer ({len(done)} cached)")
    fh = cache.open("a", encoding="utf-8")
    for i, r in enumerate(todo, 1):
        qid = _stem(r["audio_url"])
        audio = audio_index.get(r["audio_url"].split("/")[-1])
        if audio is None:
            rec = {"qid": qid, "skipped": "no_audio"}
        elif form == "mcq":
            distractors = parse_distractors(r["distractors"])
            mcq = build_mcq(r["question"], r["correct_answer"], distractors, qid)
            resp, err = _generate(client, mcq["prompt"], audio, MCQ_MAX_TOKENS)
            pred = extract_letter(resp, mcq["letter_map"]) if not err else None
            rec = {"qid": qid, "question": r["question"], "audio": audio.name,
                   "category": r.get("category", ""), "skills": r.get("skills", ""),
                   "category_1": r["category_1"], "category_2": r["category_2"],
                   "category_3": r["category_3"], "correct_answer": mcq["correct_answer"],
                   "correct_letter": mcq["correct_letter"], "response": resp,
                   "pred_letter": pred, "pred_answer": mcq["letter_map"].get(pred) if pred else None,
                   "correct": (pred == mcq["correct_letter"]) if pred else False, "error": err}
        else:  # oeq (guided)
            oeq = build_oeq(r["question"], r["correct_answer"],
                            answer_format=r.get("answer_format", ""),
                            example=r.get("example_answer", ""))
            resp, err = _generate(client, oeq["prompt"], audio, OEQ_MAX_TOKENS)
            rec = {"qid": qid, "question": r["question"], "audio": audio.name,
                   "category": r.get("category", ""), "skills": r.get("skills", ""),
                   "category_1": r["category_1"], "category_2": r["category_2"],
                   "category_3": r["category_3"], "answer_format": r.get("answer_format", ""),
                   "example_answer": r.get("example_answer", ""), "prompt": oeq["prompt"],
                   "reference_answer": r["correct_answer"], "response": resp, "error": err}
        done[qid] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        tag = ("ERR" if rec.get("error") else
               (("✓" if rec.get("correct") else "✗") if form == "mcq" else "OK"))
        print(f"  [{i}/{len(todo)}] {qid[:24]:<24} {tag} {(rec.get('response') or rec.get('skipped') or '')[:44]!r}")
    fh.close()
    return done


def phase_judge(answers: dict[str, dict], cache: Path) -> dict[str, dict]:
    done = _read_jsonl(cache)
    todo = [q for q, a in answers.items() if q not in done and not a.get("skipped")]
    if not todo:
        print(f"[judge] all judged ({len(done)}); skipping.")
        return done
    judge = PIACJudge()
    print(f"[judge] PIAC judging with {judge.model_id}: {len(todo)} answers")
    fh = cache.open("a", encoding="utf-8")
    for i, qid in enumerate(todo, 1):
        a = answers[qid]
        v = judge.score(a.get("category", ""), a["question"], a["reference_answer"],
                        a.get("response", ""), a.get("answer_format", ""))
        rec = {"qid": qid, **v}
        done[qid] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        h = "HALL" if v["hallucinated"] else "    "
        print(f"  [{i}/{len(todo)}] {qid[:22]:<22} {a.get('category','?'):<11} "
              f"score={v['score']} {h} {v['hallucination_level']}")
    fh.close()
    return done


def run(model_spec: str, data_path: Path, limit: int | None) -> None:
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    df = pd.read_csv(data_path, dtype=str, keep_default_na=False)
    df = df[df["category_1"].str.lower() == "music"].reset_index(drop=True)
    if limit:
        df = df.head(limit)

    slug = _slug(model_spec)
    mcq_dir = ROOT / "results" / "mmar" / slug / "music"
    oeq_dir = ROOT / "results" / "mmar" / slug / "music-oeq-piac"
    mcq_dir.mkdir(parents=True, exist_ok=True)
    oeq_dir.mkdir(parents=True, exist_ok=True)
    audio_index = build_audio_index()
    started = datetime.now(timezone.utc).isoformat()
    print(f"Model: {model_spec}  |  music questions: {len(df)}")

    client = make_client(model_spec)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    meta_base = {"model": model_spec, "benchmark": "mmar", "modality": "music",
                 "git_commit": git_commit(), "run_started": started,
                 "run_local_datetime": stamp}

    # 1. MCQ answers (API) — written immediately so a later judge failure can't lose them.
    mcq_ans = phase_answers(df, audio_index, client, mcq_dir / ".mcq.jsonl", "mcq")
    _write_mcq(mcq_dir, stamp, meta_base, df, mcq_ans)
    print(f"Wrote MCQ → {mcq_dir}  (prefix {stamp})")

    # 2. OEQ answers (API), then the local Qwen3 PIAC judge. If the judge fails (e.g. GPU
    #    busy), still write the OEQ answers (unscored) so nothing is lost; re-run to judge.
    oeq_ans = phase_answers(df, audio_index, client, oeq_dir / ".oeq_answers.jsonl", "oeq")
    judged_path = oeq_dir / ".oeq_piac_judged.jsonl"
    try:
        judged = phase_judge(oeq_ans, judged_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[judge] FAILED ({type(exc).__name__}: {str(exc)[:140]}) — writing OEQ "
              f"answers without scores; re-run to finish judging.")
        judged = _read_jsonl(judged_path)
    _write_oeq(oeq_dir, stamp, meta_base, df, oeq_ans, judged)
    print(f"Wrote OEQ → {oeq_dir}  (prefix {stamp}, {len(judged)}/{len(oeq_ans)} judged)")


def _records_mcq(df, ans):
    recs = []
    for _, r in df.iterrows():
        recs.append(ans.get(_stem(r["audio_url"]), {"qid": _stem(r["audio_url"])}))
    return recs


def _write_mcq(out_dir, stamp, meta, df, ans) -> None:
    recs = _records_mcq(df, ans)
    scored = [r for r in recs if not r.get("skipped") and not r.get("error")]
    acc = sum(1 for r in scored if r.get("correct")) / len(scored) if scored else 0.0
    by_piac = defaultdict(lambda: [0, 0])
    for r in scored:
        by_piac[r.get("category") or "?"][0] += int(bool(r.get("correct")))
        by_piac[r.get("category") or "?"][1] += 1
    cols = ["qid", "category", "skills", "category_1", "category_2", "category_3", "question",
            "correct_answer", "correct_letter", "pred_letter", "pred_answer", "response",
            "correct", "skipped", "error"]
    with (out_dir / f"{stamp}_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            row = dict(r); row["response"] = (r.get("response") or "").replace("\n", " ").strip()
            w.writerow(row)
    summary = {"n": len(recs), "n_scored": len(scored), "accuracy": round(acc, 4),
               "accuracy_by_piac": {k: round(v[0] / v[1], 4) for k, v in by_piac.items() if v[1]}}
    (out_dir / f"{stamp}_comparison.json").write_text(
        json.dumps({**meta, "form": "mcq", "summary": summary, "items": recs},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"{meta['model']} — MMAR music MCQ", "=" * 48,
             f"Run: {stamp}   commit {meta['git_commit']}",
             f"accuracy: {acc:.2%}  ({sum(1 for r in scored if r.get('correct'))}/{len(scored)})",
             "", "By PIAC category:"]
    for c in [*PIAC_ORDER, *[k for k in by_piac if k not in PIAC_ORDER]]:
        if c in by_piac and by_piac[c][1]:
            lines.append(f"  {c:<12} {by_piac[c][0]/by_piac[c][1]:.2%}  (n={by_piac[c][1]})")
    (out_dir / f"{stamp}_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_oeq(out_dir, stamp, meta, df, ans, judged) -> None:
    recs = []
    for _, r in df.iterrows():
        qid = _stem(r["audio_url"])
        a = ans.get(qid, {"qid": qid}); j = judged.get(qid, {})
        recs.append({**a, "judge_score": j.get("score"), "judge_score_norm": j.get("score_norm"),
                     "verdict": j.get("verdict"), "grounded": j.get("grounded"),
                     "hallucinated": j.get("hallucinated"),
                     "hallucination_level": j.get("hallucination_level"),
                     "judge_rationale": j.get("rationale")})
    scored = [r for r in recs if r.get("judge_score_norm") is not None]
    mean = sum(r["judge_score_norm"] for r in scored) / len(scored) if scored else 0.0
    halluc = [r for r in scored if r.get("hallucinated")]
    by_piac = defaultdict(list)
    for r in scored:
        by_piac[r.get("category") or "?"].append(r["judge_score_norm"])
    cols = ["qid", "category", "skills", "category_1", "category_2", "category_3", "question",
            "answer_format", "example_answer", "prompt", "reference_answer", "response",
            "judge_score", "judge_score_norm", "verdict", "grounded", "hallucinated",
            "hallucination_level", "judge_rationale", "skipped", "error"]
    with (out_dir / f"{stamp}_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            row = dict(r); row["response"] = (r.get("response") or "").replace("\n", " ").strip()
            w.writerow(row)
    summary = {"n": len(recs), "n_judged": len(scored), "mean_score_norm": round(mean, 4),
               "hallucination_rate": round(len(halluc) / len(scored), 4) if scored else 0.0,
               "mean_score_norm_by_piac": {k: round(sum(v) / len(v), 4) for k, v in by_piac.items()}}
    (out_dir / f"{stamp}_comparison.json").write_text(
        json.dumps({**meta, "form": "oeq", "judge": "Qwen3-8B PIAC category-specific",
                    "summary": summary, "items": recs}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    lines = [f"{meta['model']} — MMAR music OEQ (PIAC-judged)", "=" * 48,
             f"Run: {stamp}   commit {meta['git_commit']}",
             f"mean score (0-1): {mean:.4f}   hallucination: {summary['hallucination_rate']:.2%} "
             f"({len(halluc)}/{len(scored)})", "", "By PIAC category (mean score | n):"]
    for c in [*PIAC_ORDER, *[k for k in by_piac if k not in PIAC_ORDER]]:
        if c in by_piac:
            v = by_piac[c]
            lines.append(f"  {c:<12} {sum(v)/len(v):.4f}  (n={len(v)})")
    (out_dir / f"{stamp}_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, help="make_client spec, e.g. openrouter:google/gemini-3-flash-preview")
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run(args.model, Path(args.data), args.limit)


if __name__ == "__main__":
    main()

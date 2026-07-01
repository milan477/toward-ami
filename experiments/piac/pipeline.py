"""STEP 3 — the processing pipeline: questions CSV → probe-ready processed CSV.

    python -m experiments.piac.pipeline mmar          # full music subset (206)
    python -m experiments.piac.pipeline mmar --limit 20   # POC: classify 20 new rows

Given a dataset name, this:
  1. resolves it to data/cleaned/<name>.csv and ensures every music-subset question is
     PIAC-annotated (category + answer_format + example_answer) by reusing
     ``experiments.oeq_mcq.annotate`` — writes/updates data/processed/<name>.csv.
  2. adds the orthogonal SKILL labels with local Qwen3 (``classify.SkillClassifier``),
     resumable via a ``.skills.jsonl``.
  3. derives ``eval_strategy`` from the PIAC category (``taxonomy.eval_strategy``).
  4. writes data/processed/<name>.csv — "ready to probe for music understanding":
     original columns + qid, category (PIAC), category_rationale, answer_format,
     example_answer, skills, skill_axes, eval_strategy.

The processed CSV always contains every music row; ``--limit N`` only bounds how many
NEW skill classifications run this pass (like annotate), so POC and full runs share one file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from experiments.oeq_mcq.annotate import annotate
from experiments.piac.classify import PIACClassifier, SkillClassifier
from experiments.piac.taxonomy import eval_strategy

ROOT = Path(__file__).resolve().parents[2]
CLEANED_DIR = ROOT / "data" / "cleaned"
PROCESSED_DIR = ROOT / "data" / "processed"
SKILL_COLS = ["skills", "skill_axes", "eval_strategy"]


def _skills_path(name: str) -> Path:
    return PROCESSED_DIR / f".{name}.skills.jsonl"


def _read_jsonl(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["qid"]] = rec
    return out


def run(name: str, modality: str | None, limit: int | None,
        recompute_piac: bool = False) -> Path:
    source = CLEANED_DIR / f"{name}.csv"
    if not source.exists():
        raise SystemExit(f"No cleaned dataset at {source}. Run: python download/clean.py {name}")

    # 1. Ensure PIAC annotation (reuses annotate; a no-op for rows already annotated).
    processed = annotate(source, judge_spec="local", limit=limit, overwrite=False,
                         modality=modality)

    df = pd.read_csv(processed, dtype=str, keep_default_na=False)
    if modality:
        df = df[df["category_1"].str.lower() == modality.lower()].reset_index(drop=True)

    # 1b. Optionally RECOMPUTE the PIAC category with the full taxonomy definitions
    # (annotate uses a shorter prompt). Keeps annotate's label in `category_auto`.
    if recompute_piac:
        piac_path = PROCESSED_DIR / f".{name}.piac.jsonl"
        prior_piac = _read_jsonl(piac_path)
        clf_p = PIACClassifier()
        print(f"\n[piac] recomputing category with {clf_p.model_id} + full taxonomy "
              f"({sum(1 for q in df['qid'] if q in prior_piac)}/{len(df)} cached)")
        fh = piac_path.open("a", encoding="utf-8")
        n_new = 0
        for _, r in df.iterrows():
            qid = r["qid"]
            if qid in prior_piac or (limit is not None and n_new >= limit):
                continue
            res = clf_p.classify(r["question"], r.get("correct_answer", ""),
                                 r.get("answer_format", ""))
            rec = {"qid": qid, **res}
            prior_piac[qid] = rec
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n_new += 1
            old = r.get("category", "")
            mark = "→" if res["piac"] and res["piac"] != old else "="
            print(f"  [{n_new}] {qid} {old:<11} {mark} {res['piac']:<11} {r['question'][:38]!r}")
        fh.close()
        for idx, r in df.iterrows():
            p = prior_piac.get(r["qid"])
            if p and p.get("piac"):
                df.at[idx, "category"] = p["piac"]
                df.at[idx, "category_rationale"] = p.get("piac_rationale", "")
        n_changed = sum(1 for _, r in df.iterrows()
                        if r["qid"] in prior_piac
                        and prior_piac[r["qid"]].get("piac")
                        and prior_piac[r["qid"]]["piac"] != r.get("category_auto", ""))
        print(f"[piac] recomputed {len(prior_piac)} rows; {n_changed} differ from annotate.")

    # 2. Skill classification (resumable), bounded by --limit new rows this pass.
    skills_path = _skills_path(name)
    prior = _read_jsonl(skills_path)
    clf = SkillClassifier()
    print(f"\n[skills] classifying with {clf.model_id} "
          f"({sum(1 for q in df['qid'] if q in prior)}/{len(df)} cached)")
    fh = skills_path.open("a", encoding="utf-8")
    n_new = 0
    for _, r in df.iterrows():
        qid = r["qid"]
        if qid in prior:
            continue
        if limit is not None and n_new >= limit:
            continue
        res = clf.classify(r["question"], r.get("correct_answer", ""), r.get("answer_format", ""))
        rec = {"qid": qid, **res}
        prior[qid] = rec
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        n_new += 1
        print(f"  [{n_new}] {qid} {r.get('category','?'):<11} skills={res['skills']}")
    fh.close()

    # 3-4. Attach skill + eval_strategy columns and write.
    df["skills"] = [", ".join(prior.get(q, {}).get("skills", [])) for q in df["qid"]]
    df["skill_axes"] = ["|".join(prior.get(q, {}).get("skill_axes", [])) for q in df["qid"]]
    df["eval_strategy"] = [eval_strategy(c) for c in df["category"]]

    ordered = [c for c in df.columns if c not in SKILL_COLS] + SKILL_COLS
    df = df[ordered]
    df.to_csv(processed, index=False)

    n_skills = (df["skills"] != "").sum()
    print(f"\nDone. Wrote {processed}  ({len(df)} rows; {n_skills} with skills, {n_new} new).")
    print("PIAC:", df[df["category"] != ""]["category"].value_counts().to_dict())
    if n_skills:
        from collections import Counter
        c = Counter(s for row in df["skills"] if row for s in row.split(", "))
        print("Top skills:", dict(c.most_common(10)))
    return processed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", help="dataset name, e.g. 'mmar' (→ data/cleaned/mmar.csv)")
    ap.add_argument("--modality", default="music", help="filter category_1 (default: music)")
    ap.add_argument("--limit", type=int, default=None,
                    help="max NEW rows to annotate/classify this pass (for the POC gate)")
    ap.add_argument("--recompute-piac", action="store_true",
                    help="re-classify the PIAC category with the full taxonomy (Qwen3), "
                         "overwriting annotate's `category` (kept in `category_auto`)")
    args = ap.parse_args()
    run(args.dataset, args.modality or None, args.limit, args.recompute_piac)


if __name__ == "__main__":
    main()

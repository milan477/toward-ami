"""Annotate selected benchmark questions with analysis labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from download.common import bench_dir, bench_path
from src.config import ANALYSIS_COLS, DEFAULT_JUDGE_SPEC, DEFAULT_MODALITY
from src.analysis.annotators import build_annotators


def make_qid(question: str, audio_url: str) -> str:
    digest = hashlib.sha1(f"{question}|{audio_url}".encode("utf-8")).hexdigest()
    return digest[:10]


def _analysis_path(name: str) -> Path:
    return bench_dir(name) / f".{name}.analysis.jsonl"


def _read_jsonl(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        records[rec["qid"]] = rec
    return records


def _prior_annotated(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    old = pd.read_csv(path, dtype=str, keep_default_na=False)
    return {r["qid"]: r for _, r in old.iterrows() if r.get("qid")}


def annotate(
    name: str,
    modality: str | None = DEFAULT_MODALITY,
    limit: int | None = None,
    *,
    judge_spec: str = DEFAULT_JUDGE_SPEC,
    overwrite: bool = False,
) -> Path:
    source = bench_path(name, "selected")
    if not source.exists():
        raise SystemExit(f"No selected dataset at {source}. Run the download/clean step first.")

    df = pd.read_csv(source, dtype=str, keep_default_na=False)
    if modality:
        df = df[df["category_1"].str.lower() == modality.lower()].reset_index(drop=True)
        print(f"Filtered to category_1 == {modality!r}: {len(df)} rows")

    df["qid"] = [make_qid(r["question"], r.get("audio_url", "")) for _, r in df.iterrows()]
    out_path = bench_path(name, "annotated")
    bench_dir(name)

    prior_annotated = {} if overwrite else _prior_annotated(out_path)
    cache_path = _analysis_path(name)
    cached = {} if overwrite else _read_jsonl(cache_path)

    annotators = build_annotators(judge_spec)
    model_id = annotators[0].client.model_id if annotators else judge_spec
    print(f"[analysis] {source.name}: {len(df)} rows with {model_id}")
    print(f"[analysis] cache: {cache_path}")

    cache_fh = cache_path.open("w" if overwrite else "a", encoding="utf-8")
    rows: list[dict] = []
    n_new = 0
    n_kept = 0

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        rec = row.to_dict()
        qid = rec["qid"]
        prior = prior_annotated.get(qid)
        if prior and not overwrite and str(prior.get("category", "")).strip():
            for col in ANALYSIS_COLS:
                rec[col] = prior.get(col, "")
            n_kept += 1
        else:
            result = cached.get(qid, {"qid": qid})
            missing = [a for a in annotators if any(not result.get(c) for c in a.output_columns)]
            if missing and (limit is None or n_new < limit):
                for annotator in missing:
                    result.update(annotator.annotate(rec))
                cached[qid] = result
                cache_fh.write(json.dumps(result, ensure_ascii=False) + "\n")
                cache_fh.flush()
                n_new += 1
                print(f"  [{idx}/{len(df)}] {qid} "
                      f"{result.get('question_nature','?'):<11} "
                      f"{result.get('piac','?'):<11} "
                      f"skills={result.get('skills', '')}")

            if result:
                rec.update({col: result.get(col, "") for col in ANALYSIS_COLS})
            else:
                for col in ANALYSIS_COLS:
                    rec.setdefault(col, "")
                rec["qid"] = qid
        rows.append(rec)

    cache_fh.close()

    out = pd.DataFrame(rows)
    source_cols = [c for c in df.columns if c not in ANALYSIS_COLS]
    ordered = [*source_cols, *ANALYSIS_COLS]
    out = out[[c for c in ordered if c in out.columns]]
    out.to_csv(out_path, index=False)

    print(f"\nDone. Wrote {out_path}")
    print(f"New annotations: {n_new}; preserved annotated rows: {n_kept}")
    if "category" in out:
        print("PIAC:", out[out["category"] != ""]["category"].value_counts().to_dict())
    if "question_nature" in out:
        print("Question nature:", out[out["question_nature"] != ""]["question_nature"].value_counts().to_dict())
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--modality", default=DEFAULT_MODALITY)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--judge", default=DEFAULT_JUDGE_SPEC)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    annotate(
        args.dataset,
        modality=args.modality or None,
        limit=args.limit,
        judge_spec=args.judge,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()

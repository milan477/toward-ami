"""Qwen decomposition — break each question into an ordered chain of PIAC probes.

A question rarely tests a single level of understanding. "Is the location indoors
or outdoors?" really rests on a PERCEPTUAL fact (is there reverb?), an INFERENTIAL
one (how large is the space?), and only then the answer. Decomposing a question
into that chain lets us probe an ALM at each level and see *where* it fails — a
model may state the final answer fluently yet be wrong on the perceptual ground it
should rest on (cf. the hallucination analysis in ``analyze.py``).

For each question this asks local Qwen3 for an ordered list of sub-questions
("probes"), each tagged with its PIAC level, building from the most basic
perceptual observation up to a final probe at the level of the original question.
Each probe carries the expected answer consistent with the known correct answer
(the last probe's expected answer is the reference answer itself).

The chain is written back to data/benchmarks/<name>/<name>_normalized_selected_annotated.csv as:
    probe_chain  — the levels, e.g. "perceptual → inferential → affective"
    n_probes     — how many probes
    probes       — the full JSON list [{level, question, expected}, ...]

Resumable via a ``.<name>.probes.jsonl``; ``--limit N`` bounds only how many NEW
decompositions run this pass (so POC and full runs share one file).

    python -m src.decomposition.decompose mmar --limit 5   # POC gate
    python -m src.decomposition.decompose mmar             # full music subset (206)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from download.common import bench_dir, bench_path
from models.client import make_client

from src.analysis.taxonomy import CATEGORIES, PIAC_ORDER
from .prompts import build_decompose_prompt

ROOT = Path(__file__).resolve().parents[2]
PROBE_COLS = ["probe_chain", "n_probes", "probes"]


def parse_probes(text: str) -> dict:
    """Pull an ordered list of {level, question, expected} probes from the reply."""
    probes: list[dict] = []
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            for p in obj.get("probes", []):
                if not isinstance(p, dict):
                    continue
                lvl = str(p.get("level", "")).strip().lower()
                q = str(p.get("question", "")).strip()
                exp = str(p.get("expected", "")).strip()
                if lvl in CATEGORIES and q:
                    probes.append({"level": lvl, "question": q, "expected": exp})
        except json.JSONDecodeError:
            pass
    return {
        "probes": probes,
        "probe_chain": " → ".join(p["level"] for p in probes),
        "n_probes": len(probes),
    }


class Decomposer:
    """Break a question into an ordered PIAC probe chain (local Qwen3)."""

    def __init__(self, spec: str = "local", max_tokens: int = 420):
        self.client = make_client(spec)
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return self.client.model_id

    def decompose(self, question: str, reference: str, category: str = "",
                  answer_format: str = "") -> dict:
        reply = self.client.generate(
            build_decompose_prompt(question, reference, category, answer_format),
            max_tokens=self.max_tokens)
        return parse_probes(reply)


# --- Runner ---------------------------------------------------------------

def _read_jsonl(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["qid"]] = rec
    return out


def run(name: str, modality: str | None, limit: int | None) -> Path:
    processed = bench_path(name, "annotated")
    if not processed.exists():
        raise SystemExit(f"No annotated dataset at {processed}. Run: "
                         f"python -m src.analysis.run pipeline {name}")
    df = pd.read_csv(processed, dtype=str, keep_default_na=False)
    if modality:
        df = df[df["category_1"].str.lower() == modality.lower()].reset_index(drop=True)

    probes_path = bench_dir(name) / f".{name}.probes.jsonl"
    prior = _read_jsonl(probes_path)
    dec = Decomposer()
    print(f"[decompose] {dec.model_id}  "
          f"({sum(1 for q in df['qid'] if q in prior)}/{len(df)} cached)")

    fh = probes_path.open("a", encoding="utf-8")
    n_new = 0
    for _, r in df.iterrows():
        qid = r["qid"]
        if qid in prior or (limit is not None and n_new >= limit):
            continue
        res = dec.decompose(r["question"], r.get("correct_answer", ""),
                            r.get("category", ""), r.get("answer_format", ""))
        prior[qid] = {"qid": qid, **res}
        fh.write(json.dumps(prior[qid], ensure_ascii=False) + "\n")
        fh.flush()
        n_new += 1
        print(f"  [{n_new}] {qid} {r.get('category','?'):<11} {res['probe_chain']}")
    fh.close()

    df["probe_chain"] = [prior.get(q, {}).get("probe_chain", "") for q in df["qid"]]
    df["n_probes"] = [str(prior.get(q, {}).get("n_probes", "")) for q in df["qid"]]
    df["probes"] = [json.dumps(prior.get(q, {}).get("probes", []), ensure_ascii=False)
                    for q in df["qid"]]

    ordered = [c for c in df.columns if c not in PROBE_COLS] + PROBE_COLS
    df[ordered].to_csv(processed, index=False)

    n_done = (df["probe_chain"] != "").sum()
    print(f"\nDone. Wrote {processed}  ({len(df)} rows; {n_done} decomposed, {n_new} new).")
    from collections import Counter
    depth = Counter(df[df["probe_chain"] != ""]["n_probes"])
    print("Probes per question:", dict(sorted(depth.items())))
    # how often each level appears in a chain
    lvl = Counter(p["level"] for q in df["qid"] for p in prior.get(q, {}).get("probes", []))
    print("Level coverage:", {k: lvl.get(k, 0) for k in PIAC_ORDER})
    return processed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", help="dataset name, e.g. 'mmar' (→ data/benchmarks/mmar/mmar_normalized_selected_annotated.csv)")
    ap.add_argument("--modality", default="music", help="filter category_1 (default: music)")
    ap.add_argument("--limit", type=int, default=None,
                    help="bound how many NEW decompositions run this pass")
    args = ap.parse_args()
    run(args.dataset, args.modality or None, args.limit)


if __name__ == "__main__":
    main()

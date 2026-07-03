"""Auto-annotate MMAR questions with a local Qwen model, for later manual review.

For every question this asks the local judge model two things:

  answer_format — a short description of what a correct answer looks like
                  (e.g. "single instrument name", "one of the four options",
                  "a number of beats per minute", "a short emotion word").
  category      — the content category the question depends on, one of:
                      perceptual  — measurable directly from the audio signal
                      inferential — derived through trained analysis of the signal
                      affective   — the listener's subjective experience
                      contextual  — factual world knowledge beyond the signal
  example_answer — one plausible but INCORRECT answer to the question (matching
                  answer_format), as a distractor / negative example.

The result is written to an EDITABLE csv at data/benchmarks/<name>/<name>_ready.csv: the
source columns plus `qid`, `category` (the working label, reviewed/edited in the
frontend), `category_auto` (Qwen's original suggestion, kept for provenance),
`category_rationale`, and `answer_format`. Re-running is incremental — rows that
already carry a `category` are left untouched, so manual edits survive.

Usage:
    python -m src.piac.annotate                      # cleaned mmar
    python -m src.piac.annotate --source data/benchmarks/mmar/mmar_cleaned.csv
    python -m src.piac.annotate --judge local:Qwen/Qwen2.5-3B-Instruct
    python -m src.piac.annotate --limit 5 --overwrite
"""

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

import pandas as pd

from download.common import bench_dir, bench_path
from models.client import make_client

from .prompts import parse_distractors

ROOT = Path(__file__).parent.parent.parent
DEFAULT_SOURCE = bench_path("mmar", "cleaned")

# The four content categories, summarized for the classifier prompt (canonical
# display order). See the project taxonomy: perceptual / inferential / affective
# / contextual.
CATEGORIES = {
    "perceptual": (
        "Information directly measurable from the audio signal, admitting a single "
        "ground truth and requiring neither prior knowledge nor reasoning. Defined "
        "by the absence of reasonable disagreement (given an answer format): a note "
        "is A4 or it is not; an onset occurs at a given time or it does not. Covers "
        "objective signal-level attributes / audio features — pitch, timing, "
        "duration, loudness, instrumentation, lyrics. NB: meter / time-signature is "
        "NOT perceptual (not physically present in the signal; interpretable, e.g. "
        "4/4 vs 2/2)."
    ),
    "inferential": (
        "Musical information derived from the audio through trained listening and "
        "analytical reasoning. Intersubjective: trained listeners tend to converge "
        "on an answer but some disagreement remains possible; claims must be "
        "substantiable in perceptual evidence. Covers harmonic function, chord "
        "identity, formal segmentation, phrase structure, voice leading, other "
        "aspects of musical organization, and genre/style attribution — plus "
        "relative descriptors that map a measurable quantity onto a musical "
        "category (e.g. calling a measured tempo 'slow')."
    ),
    "affective": (
        "Information about the listener's subjective experience of the music — "
        "expression and emotional response. Subjective by definition: no single "
        "right answer and no consensus expected or desirable. Covers perceived "
        "mood, character, tension, intimacy, energy, aesthetic quality, and "
        "personal response; ideally grounded in perceptual/inferential features."
    ),
    "contextual": (
        "Factual knowledge about the music that is external to the audio signal, "
        "attached through historical or physical context, and admitting a single "
        "ground truth (when it is unknown, the correct response is to acknowledge "
        "that uncertainty). Covers composer, performer, title, date or place of "
        "recording, and the audio's reception or influence. NB: detecting genre "
        "from audio is inferential and ambiguous, NOT contextual."
    ),
}
CATEGORY_NAMES = list(CATEGORIES)

RULE_OF_THUMB = (
    "Rule of thumb, by degree of ambiguity: if it is directly measurable from the "
    "signal (single ground truth, no reasoning) it is perceptual; if it is an "
    "external fact about the music not derivable from the signal (single ground "
    "truth) it is contextual; if it is the listener's subjective experience (no "
    "consensus) it is affective; otherwise — derived by trained analysis, with "
    "expert consensus but some disagreement — it is inferential."
)

# New columns this script manages (order preserved when written out).
# `piac` is the human-facing name of the content category (kept in sync with the
# pipeline column `category`, which many readers use). Both hold the same value.
ANNOTATION_COLS = ["qid", "category", "piac", "category_auto", "category_rationale",
                   "answer_format", "example_answer"]


def _category_block() -> str:
    return "\n".join(f"  - {name}: {summary}" for name, summary in CATEGORIES.items())


PROMPT_TEMPLATE = f"""You are annotating a question about an audio clip for a music-evaluation \
study. Do three things.

1. answer_format: in a short, SPECIFIC noun phrase, describe what a correct \
answer looks like if the question were asked open-ended — its form, not its \
content, and IGNORING that options may be listed. Be precise about the type: \
e.g. "a single instrument name", "a country name", "an ordinal number \
(first/second/…)", "a tempo in beats per minute", "a short emotion word", "yes \
or no", "a count of beats", "a reason (a 'because…' clause)". Derive the type \
from the REFERENCE ANSWER's own form. NEVER answer with a vague type such as \
"mcq option", "one of the listed options", "an option", or "a piece number".

2. category: classify the question into exactly ONE of these four content \
categories, by what a correct answer fundamentally depends on:
{_category_block()}

{RULE_OF_THUMB}

3. example_answer: give ONE INCORRECT but valid answer to the question — a real \
answer from the SAME answer space and in the SAME form as the reference answer \
(same brevity and type), just a wrong value. It is a wrong OPTION, not an \
explanation: never a sentence or a justification.
   - If the question is yes/no or offers explicit alternatives, use the OTHER \
option (reference "Yes" → "No"; reference "Outdoors" → "Indoors"; reference \
"Fourth" → "Second").
   - If options are listed below, example_answer MUST be exactly one of the \
INCORRECT options, copied verbatim.
   - Otherwise pick a different but realistic value of the same kind (reference \
"violin" → "cello"; reference "Japan" → "Korea").

Question: {{question}}
Answer type: {{qtype}}
Reference answer (the CORRECT answer — do not reuse it): {{answer}}{{options}}

Reply with ONLY a JSON object and nothing else:
{{{{"answer_format": "<short phrase>", "category": "<perceptual|inferential|affective|contextual>", "rationale": "<one short sentence>", "example_answer": "<an incorrect option, same form as the reference>"}}}}"""


def make_qid(question: str, audio_url: str) -> str:
    h = hashlib.sha1(f"{question}|{audio_url}".encode("utf-8")).hexdigest()
    return h[:10]


def _incorrect_options(correct: str, distractors: list[str]) -> list[str]:
    return [d for d in distractors if d.strip().lower() != str(correct).strip().lower()]


def pick_incorrect_option(correct: str, distractors: list[str], qid: str) -> str:
    """A verbatim incorrect option, chosen deterministically (seeded by qid)."""
    wrong = _incorrect_options(correct, distractors)
    return random.Random(f"{qid}|example").choice(wrong) if wrong else ""


def ground_example(example: str, row: dict) -> str:
    """For MCQ, the example answer must be a real (incorrect) option. Keep the
    model's example when it already is one; otherwise fall back to an actual
    distractor so the example is always literally a possible answer."""
    if row.get("question_type") != "mcq":
        return example
    distractors = parse_distractors(row.get("distractors", ""))
    incorrect = {d.strip().lower() for d in _incorrect_options(row.get("correct_answer", ""), distractors)}
    if example.strip().lower() in incorrect:
        return example
    return pick_incorrect_option(row.get("correct_answer", ""), distractors, row.get("qid", ""))


def build_prompt(row: dict) -> str:
    qtype = row.get("question_type", "")
    options = ""
    if qtype == "mcq":
        opts = [row.get("correct_answer", ""), *parse_distractors(row.get("distractors", ""))]
        opts = [o for o in opts if o]
        if opts:
            options = "\nOptions (correct one is the reference above): " + "; ".join(opts)
    return PROMPT_TEMPLATE.format(
        question=str(row.get("question", "")).strip(),
        qtype=qtype or "open-ended",
        answer=str(row.get("correct_answer", "")).strip(),
        options=options,
    )


def parse_annotation(text: str) -> dict:
    """Pull {answer_format, category, rationale, example_answer} from the reply."""
    fmt, cat, rationale, example = "", "", "", ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            fmt = str(obj.get("answer_format", "")).strip()
            cat = str(obj.get("category", "")).strip().lower()
            rationale = str(obj.get("rationale", "")).strip()
            example = str(obj.get("example_answer", "")).strip()
        except json.JSONDecodeError:
            pass
    if cat not in CATEGORIES:  # fall back to the first category word mentioned
        found = next((c for c in CATEGORIES if re.search(rf"\b{c}\b", text, re.I)), "")
        cat = found
    return {"answer_format": fmt, "category": cat, "rationale": rationale,
            "example_answer": example, "raw": text.strip()}


def annotate(source: Path, judge_spec: str, limit: int | None, overwrite: bool,
             modality: str | None = None) -> Path:
    src = pd.read_csv(source, dtype=str, keep_default_na=False)
    if modality:
        src = src[src["category_1"].str.lower() == modality.lower()].reset_index(drop=True)
        print(f"Filtered to category_1 == {modality!r}: {len(src)} rows")
    src["qid"] = [make_qid(r["question"], r["audio_url"]) for _, r in src.iterrows()]

    # Source lives at data/benchmarks/<name>/<name>_cleaned.csv → write the
    # probe-ready CSV alongside it as <name>_ready.csv.
    name = source.parent.name
    out_path = bench_path(name, "ready")
    bench_dir(name)

    # Preserve prior annotations (incl. manual frontend edits) keyed by qid.
    prior: dict[str, dict] = {}
    if out_path.exists() and not overwrite:
        old = pd.read_csv(out_path, dtype=str, keep_default_na=False)
        prior = {r["qid"]: r for _, r in old.iterrows() if r.get("qid")}

    client = make_client(judge_spec)
    print(f"Annotating {source.name} ({len(src)} questions) with {client.model_id}")
    print(f"Writing → {out_path}")

    rows, n_new, n_kept = [], 0, 0
    for i, (_, r) in enumerate(src.iterrows()):
        rec = r.to_dict()
        existing = prior.get(rec["qid"])
        if existing is not None and str(existing.get("category", "")).strip():
            for c in ANNOTATION_COLS:
                rec[c] = existing.get(c, "")
            n_kept += 1
        elif limit is not None and n_new >= limit:
            for c in ANNOTATION_COLS:
                rec.setdefault(c, "")
            rec["qid"] = r["qid"]
        else:
            ann = parse_annotation(client.generate(build_prompt(rec), max_tokens=220))
            rec["category"] = ann["category"]
            rec["piac"] = ann["category"]
            rec["category_auto"] = ann["category"]
            rec["category_rationale"] = ann["rationale"]
            rec["answer_format"] = ann["answer_format"]
            rec["example_answer"] = ground_example(ann["example_answer"], rec)
            n_new += 1
            print(f"  [{i+1}/{len(src)}] {ann['category'] or '?':<11} "
                  f"fmt={ann['answer_format'][:32]!r}  ✗ex={ann['example_answer'][:28]!r}  "
                  f"{rec['question'][:40]!r}")
        rows.append(rec)

    out = pd.DataFrame(rows)
    # Keep source columns first, then the annotation columns.
    cols = [c for c in src.columns if c != "qid"]
    out = out[[*[c for c in cols if c not in ANNOTATION_COLS], *ANNOTATION_COLS]]
    out.to_csv(out_path, index=False)

    print(f"\nDone. {n_new} newly annotated, {n_kept} kept from prior file.")
    counts = out[out["category"] != ""]["category"].value_counts().to_dict()
    print("Category distribution:", counts)
    print(f"\nReview/edit in the frontend:\n"
          f"  python renderers/server/server.py --stage ready")
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(DEFAULT_SOURCE),
                    help="Source cleaned csv (default: data/benchmarks/mmar/mmar_cleaned.csv).")
    ap.add_argument("--judge", default="local", help="Annotator model spec (default: local Qwen).")
    ap.add_argument("--limit", type=int, default=None, help="Annotate at most N new rows.")
    ap.add_argument("--overwrite", action="store_true",
                    help="Ignore any existing processed file (re-annotate everything).")
    ap.add_argument("--modality", default=None,
                    help="Only annotate rows with category_1 == this (e.g. 'music' → 206 rows).")
    args = ap.parse_args()
    annotate(Path(args.source), args.judge, args.limit, args.overwrite, args.modality)


if __name__ == "__main__":
    main()

"""
Deep per-benchmark content analysis.

For each benchmark this module computes:
  - #questions, MCQ / OEQ counts, n_choices distribution, response-type distribution
  - question topic distribution (free-form LLM labels, guided by examples)
  - audio profile: genre / instrumentation / format — LLM extracts freely (no fixed list)
  - MCQ choice pairwise cosine similarity (sentence encoder)

Requires:
  - sentence-transformers   pip install sentence-transformers
  - Ollama running locally  (default) OR a HuggingFace model via LLM_BACKEND=hf
    See analysis/llm.py for env vars.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from catalog import load_all, load_items
from llm import LLMClient

_BATCH = 10   # questions per LLM call


# --- JSON parsing helpers -------------------------------------------------

def _extract_json(text: str) -> Any | None:
    """Return the first valid JSON value (array or object) found in text."""
    for pattern in (r"\[.*?\]", r"\{.*?\}"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


def _parse_str_array(text: str, expected_len: int) -> list[str]:
    val = _extract_json(text)
    if isinstance(val, list):
        arr = [str(x) for x in val]
        if len(arr) < expected_len:
            arr += ["other"] * (expected_len - len(arr))
        return arr[:expected_len]
    return ["other"] * expected_len


def _parse_obj_array(text: str, expected_len: int, fallback: dict) -> list[dict]:
    val = _extract_json(text)
    if isinstance(val, list):
        result = []
        for item in val[:expected_len]:
            if isinstance(item, dict):
                result.append(item)
            else:
                result.append(dict(fallback))
        if len(result) < expected_len:
            result += [dict(fallback)] * (expected_len - len(result))
        return result
    return [dict(fallback)] * expected_len


# --- Topic classification (free-form) ------------------------------------

_TOPIC_EXAMPLES = (
    "pitch, interval, rhythm, tempo, meter, timbre, loudness, melody, harmony, "
    "chord, key / tonality, form / structure, polyphony, genre, style, instrument "
    "identification, era / period, composer / artist, music theory, comparison, "
    "counting, ordering, analogy, inference, emotion / mood, valence / arousal"
)


def _topic_classify_batch(questions: list[str], client: LLMClient) -> list[str]:
    qs = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    prompt = (
        "You are a music expert. For each question, assign a concise topic label "
        "describing the primary music concept or skill being tested.\n\n"
        f"Examples of good labels: {_TOPIC_EXAMPLES}.\n"
        "Use your own label when none of the examples fit — keep it short (1–4 words).\n\n"
        f"Questions:\n{qs}\n\n"
        f"Respond with a JSON array of exactly {len(questions)} strings, "
        "one label per question, in order.\n"
        "Output only the JSON array, nothing else."
    )
    raw = client.generate(prompt)
    return _parse_str_array(raw, len(questions))


def classify_topics(questions: list[str], client: LLMClient) -> list[str]:
    results: list[str] = []
    for i in range(0, len(questions), _BATCH):
        batch = questions[i : i + _BATCH]
        labels = _topic_classify_batch(batch, client)
        results.extend(labels)
        print(f"  topics: {min(i + _BATCH, len(questions))}/{len(questions)}")
    return results


# --- Audio profile (free-form, multi-dimension) ---------------------------

_AUDIO_FALLBACK = {"genre": "unknown", "instrumentation": ["unknown"], "format": "unknown"}


def _audio_profile_batch(questions: list[str], client: LLMClient) -> list[dict]:
    qs = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    prompt = (
        "You are a music expert. For each question, infer the audio material it describes.\n\n"
        "Return a JSON array of objects — one per question — with these keys:\n"
        '  "genre"          : string — music genre (e.g. "classical", "jazz", "pop", "unknown")\n'
        '  "instrumentation": array of strings — instruments present (e.g. ["piano", "strings"])\n'
        '  "format"         : string — type of audio clip '
        '(e.g. "melody excerpt", "full piece", "isolated note", "chord", "rhythm loop", '
        '"vocal", "sound effect", "unknown")\n\n'
        f"Questions:\n{qs}\n\n"
        f"Output only the JSON array of {len(questions)} objects, nothing else."
    )
    raw = client.generate(prompt)
    profiles = _parse_obj_array(raw, len(questions), _AUDIO_FALLBACK)
    # normalise instrumentation to list[str]
    for p in profiles:
        inst = p.get("instrumentation", ["unknown"])
        if isinstance(inst, str):
            p["instrumentation"] = [inst] if inst else ["unknown"]
        elif not isinstance(inst, list):
            p["instrumentation"] = ["unknown"]
        p.setdefault("genre",  "unknown")
        p.setdefault("format", "unknown")
    return profiles


def analyze_audio_profiles(questions: list[str], client: LLMClient) -> list[dict]:
    """Return one audio-profile dict per question (free-form LLM extraction)."""
    results: list[dict] = []
    for i in range(0, len(questions), _BATCH):
        batch = questions[i : i + _BATCH]
        profiles = _audio_profile_batch(batch, client)
        results.extend(profiles)
        print(f"  audio profiles: {min(i + _BATCH, len(questions))}/{len(questions)}")
    return results


def _aggregate_audio_profiles(profiles: list[dict]) -> dict:
    genre_ctr = Counter(p["genre"] for p in profiles)
    inst_ctr  = Counter(inst for p in profiles for inst in p["instrumentation"])
    fmt_ctr   = Counter(p["format"] for p in profiles)
    return {
        "genre_distribution":         dict(genre_ctr.most_common()),
        "instrumentation_distribution": dict(inst_ctr.most_common()),
        "format_distribution":         dict(fmt_ctr.most_common()),
    }


# --- Sentence-encoder choice similarity -----------------------------------

_encoder = None   # lazy-loaded


def _get_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _encoder


def _pairwise_cosine(vecs: np.ndarray) -> list[float]:
    norms  = np.linalg.norm(vecs, axis=1, keepdims=True)
    normed = vecs / np.clip(norms, 1e-9, None)
    n = len(normed)
    return [
        float(np.dot(normed[a], normed[b]))
        for a in range(n)
        for b in range(a + 1, n)
    ]


def choice_similarities(items: list[dict]) -> dict[str, Any]:
    """Mean/min/max pairwise cosine similarity of MCQ choices across the benchmark."""
    encoder   = _get_encoder()
    mcq_items = [it for it in items if it.get("choices") and len(it["choices"]) >= 2]
    print(f"  choice similarity for {len(mcq_items)} MCQ items …")

    all_choice_texts: list[str] = []
    offsets: list[tuple[int, int]] = []
    for it in mcq_items:
        start = len(all_choice_texts)
        all_choice_texts.extend(it["choices"])
        offsets.append((start, len(all_choice_texts)))

    if not all_choice_texts:
        return {"mean": None, "min": None, "max": None, "per_item": []}

    embeddings = encoder.encode(
        all_choice_texts, convert_to_numpy=True, show_progress_bar=False
    )

    all_means, all_mins, all_maxs = [], [], []
    per_item: list[dict] = []
    for it, (s, e) in zip(mcq_items, offsets):
        sims = _pairwise_cosine(embeddings[s:e])
        if not sims:
            continue
        m, lo, hi = float(np.mean(sims)), float(np.min(sims)), float(np.max(sims))
        all_means.append(m)
        all_mins.append(lo)
        all_maxs.append(hi)
        per_item.append({
            "question": it["question"],
            "choices":  it["choices"],
            "sim_mean": round(m,  4),
            "sim_min":  round(lo, 4),
            "sim_max":  round(hi, 4),
        })

    return {
        "mean": round(float(np.mean(all_means)), 4) if all_means else None,
        "min":  round(float(np.min(all_mins)),   4) if all_mins  else None,
        "max":  round(float(np.max(all_maxs)),   4) if all_maxs  else None,
        "per_item": per_item,
    }


# --- Basic stats ----------------------------------------------------------

def _infer_response_type(item: dict) -> str:
    """
    Infer response type from canonical item fields.
    MCQ items are always categorical; OEQ items may be numeric, binary, or free text.
    """
    if item.get("choices"):
        return "categorical"
    ans = str(item.get("correct_answer", "")).strip()
    try:
        float(ans)
        return "numeric"
    except ValueError:
        pass
    if ans.lower() in {"yes", "no", "true", "false"}:
        return "binary"
    return "text"


def basic_stats(items: list[dict]) -> dict:
    total     = len(items)
    mcq_items = [it for it in items if it.get("question_type") == "mcq"]
    oeq_items = [it for it in items if it.get("question_type") == "oeq"]
    return {
        "n_questions":   total,
        "n_mcq":         len(mcq_items),
        "n_oeq":         len(oeq_items),
        "mcq_fraction":  round(len(mcq_items) / total, 4) if total else 0.0,
        "n_choices_distribution": dict(
            sorted(Counter(len(it["choices"]) for it in mcq_items if it.get("choices")).items())
        ),
        "response_type_distribution": dict(
            Counter(_infer_response_type(it) for it in items).most_common()
        ),
    }


# --- Top-level per-benchmark analysis -------------------------------------

def analyze_benchmark(
    name: str,
    items: list[dict],
    *,
    client: LLMClient | None = None,
    skip_llm: bool = False,
    skip_similarity: bool = False,
) -> dict:
    print(f"\n{'=' * 60}")
    print(f"Analyzing: {name}  ({len(items)} items)")

    stats = basic_stats(items)
    print(
        f"  MCQ: {stats['n_mcq']}, OEQ: {stats['n_oeq']}, "
        f"response types: {stats['response_type_distribution']}"
    )

    sim_stats: dict = {}
    if not skip_similarity:
        try:
            sim_stats = choice_similarities(items)
            print(
                f"  choice sim — mean={sim_stats.get('mean')}, "
                f"min={sim_stats.get('min')}, max={sim_stats.get('max')}"
            )
        except Exception as exc:
            print(f"  [WARN] sentence-encoder failed: {exc}")
            sim_stats = {"error": str(exc)}

    topic_dist:   dict = {}
    audio_agg:    dict = {}
    per_question: list[dict] = []

    if not skip_llm:
        if client is None:
            client = LLMClient.from_env()
            print(f"  LLM client: {client}")

        q_texts = [it["question"] for it in items]

        topics: list[str] = ["unknown"] * len(items)
        try:
            topics     = classify_topics(q_texts, client)
            topic_dist = dict(Counter(topics).most_common())
        except Exception as exc:
            print(f"  [WARN] topic classification failed: {exc}")

        profiles: list[dict] = [dict(_AUDIO_FALLBACK)] * len(items)
        try:
            profiles  = analyze_audio_profiles(q_texts, client)
            audio_agg = _aggregate_audio_profiles(profiles)
        except Exception as exc:
            print(f"  [WARN] audio profile extraction failed: {exc}")

        for it, topic, profile in zip(items, topics, profiles):
            per_question.append({
                "question":      it["question"],
                "topic":         topic,
                "audio_profile": profile,
            })

    return {
        "benchmark":          name,
        "basic_stats":        stats,
        "choice_similarity":  sim_stats,
        "topic_distribution": topic_dist,
        "audio_profile":      audio_agg,
        "per_question":       per_question,
    }


# --- Load canonical items -------------------------------------------------

def _load_items(benchmark_name: str) -> list[dict]:
    """Read normalized question-level items for this benchmark."""
    return load_items(benchmark_name)


# --- Entry point ----------------------------------------------------------

def deep_analysis(
    benchmarks: list[dict],
    out_dir: Path,
    *,
    client: LLMClient | None = None,
    skip_llm: bool = False,
    skip_similarity: bool = False,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict] = []

    for b in benchmarks:
        name  = b["name"]
        items = _load_items(name)
        if not items:
            print(f"  No data for {name} (no loader or empty CSV), skipping.")
            continue

        result = analyze_benchmark(
            name, items,
            client=client,
            skip_llm=skip_llm,
            skip_similarity=skip_similarity,
        )
        all_results.append(result)

        detail_path = out_dir / f"{name.lower()}_deep.json"
        detail_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"  Saved {detail_path.name}")

    _write_summary_report(all_results, out_dir)


def _write_summary_report(results: list[dict], out_dir: Path) -> None:
    lines = ["=" * 72, "DEEP ANALYSIS SUMMARY", "=" * 72]

    for r in results:
        bs = r["basic_stats"]
        lines.append(f"\n[{r['benchmark']}]")
        lines.append(f"  Questions     : {bs['n_questions']}")
        lines.append(f"  MCQ / OEQ     : {bs['n_mcq']} / {bs['n_oeq']}  ({bs['mcq_fraction']:.0%} MCQ)")
        lines.append(f"  # choices dist: {bs['n_choices_distribution']}")
        lines.append(f"  Response types: {bs['response_type_distribution']}")

        cs = r.get("choice_similarity", {})
        if cs and cs.get("mean") is not None:
            lines.append(
                f"  Choice sim    : mean={cs['mean']:.4f}  "
                f"min={cs['min']:.4f}  max={cs['max']:.4f}"
            )

        if r.get("topic_distribution"):
            top5 = list(r["topic_distribution"].items())[:5]
            lines.append(f"  Top topics    : {top5}")

        ap = r.get("audio_profile", {})
        if ap.get("genre_distribution"):
            top5 = list(ap["genre_distribution"].items())[:5]
            lines.append(f"  Genres        : {top5}")
        if ap.get("instrumentation_distribution"):
            top5 = list(ap["instrumentation_distribution"].items())[:5]
            lines.append(f"  Instruments   : {top5}")
        if ap.get("format_distribution"):
            top5 = list(ap["format_distribution"].items())[:5]
            lines.append(f"  Audio formats : {top5}")

    report = "\n".join(lines)
    print("\n" + report)
    (out_dir / "deep_analysis_summary.txt").write_text(report)
    print(f"\nSaved deep_analysis_summary.txt")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark",  metavar="NAME", help="Restrict to one benchmark")
    parser.add_argument("--backend",    choices=["ollama", "hf"], default=None,
                        help="LLM backend (default: LLM_BACKEND env var or 'ollama')")
    parser.add_argument("--model",      default=None,
                        help="Ollama model tag or HuggingFace model id")
    parser.add_argument("--skip-llm",   action="store_true")
    parser.add_argument("--skip-sim",   action="store_true", help="Skip sentence-encoder step")
    parser.add_argument("--out",        default=None, help="Output directory")
    args = parser.parse_args()

    client: LLMClient | None = None
    if not args.skip_llm:
        backend = args.backend or "ollama"
        if backend == "hf":
            client = LLMClient.from_hf(args.model) if args.model else LLMClient.from_hf()
        else:
            client = LLMClient.from_ollama(args.model) if args.model else LLMClient.from_ollama()
        print(f"LLM client: {client}")

    out = Path(args.out) if args.out else Path(__file__).resolve().parents[2] / "paper" / "analysis" / "deep"
    benchmarks = load_all()
    if args.benchmark:
        benchmarks = [b for b in benchmarks if b["name"].lower() == args.benchmark.lower()]

    deep_analysis(
        benchmarks, out,
        client=client,
        skip_llm=args.skip_llm,
        skip_similarity=args.skip_sim,
    )

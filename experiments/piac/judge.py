"""PIAC-aware LLM-as-judge: category-specific grading + hallucination detection.

Unlike the single strict 0-4 rubric in ``experiments/helpers/judge.py``, this judge
applies the evaluation strategy that PIAC assigns to each category (``taxonomy.py``):

  perceptual  (binary_exact)      → 0 or 4 only; exact / within-tolerance match.
  contextual  (binary_contextual) → 0 or 4 only; accept compatible specificity
                                     (ref 'China' vs 'Beijing'); 'unknown' if ref unknown.
  inferential (binary_expert_multi)→ 0 or 4 only; accept ANY reasonable expert-valid
                                     answer; do NOT require the model to justify.
  affective   (graded_affective)  → graded 0-4 on plausibility + consistency + grounding;
                                     accept similar emotions ('sad' ≈ 'melancholic').

We have no audio ("pretend you do"): correctness is judged against the reference as one
valid ground truth, with the per-category allowances above.

In the SAME call the judge flags **hallucination** and attributes it to a PIAC level —
a confident claim that is wrong or ungrounded (typically a fluent affective/inferential
statement resting on wrong/absent perceptual grounding). Output per item:

    {score 0-4, score_norm 0-1, verdict, grounded 0-1, hallucinated bool,
     hallucination_level ∈ {perceptual,inferential,affective,contextual,none}, rationale}

Backed by the local Qwen3 model (``make_client("local")``); no API key needed.
"""

from __future__ import annotations

import json
import re

from experiments.helpers.models import make_client

from .taxonomy import CATEGORIES, eval_strategy

SCORE_MAX = 4

# Per-strategy grading instruction injected into the judge prompt.
STRATEGY_RUBRIC = {
    "binary_exact": (
        "This is a PERCEPTUAL question with a single measurable ground truth. Grade BINARY: "
        "score 4 if the answer matches the reference (exactly, as a synonym/paraphrase, or "
        "within a small tolerance for a numeric value), otherwise 0. NEVER give 1/2/3. A "
        "close-but-wrong value scores 0 (e.g. 20 when the reference is 26 → 0)."
    ),
    "binary_contextual": (
        "This is a CONTEXTUAL question — an external factual ground truth. Grade BINARY: "
        "score 4 if the answer matches the reference fact, otherwise 0. Accept a "
        "semantically-compatible answer of different specificity (reference 'China' and "
        "answer 'Beijing' → 4; reference 'Beijing' and answer 'China' → 4). If the reference "
        "indicates the fact is unknown and the model declines/says unknown, score 4. Never 1/2/3."
    ),
    "binary_expert_multi": (
        "This is an INFERENTIAL question — trained analysis on which experts largely agree "
        "but valid alternatives exist. Grade BINARY: score 4 if the answer matches the "
        "reference OR any other reasonable expert-valid answer to this question, otherwise 0. "
        "Do NOT require the model to justify its answer (it was not asked to). Never 1/2/3."
    ),
    "graded_affective": (
        "This is an AFFECTIVE question — subjective, with no single right answer. Grade 0-4 "
        "on: plausibility (is the described feeling musically reasonable?), internal "
        "consistency, and grounding (does it tie the feeling to perceptual/inferential "
        "features?). Accept emotions similar to the reference ('sad' ≈ 'melancholic' → high). "
        "4 = plausible, consistent and grounded; 2 = plausible but ungrounded/thin; 0 = "
        "implausible, contradictory, or empty."
    ),
}

JUDGE_TEMPLATE = """You are a strict, fair music-evaluation judge. Grade a model's open-ended \
answer to a question about an audio clip, and separately assess hallucination.

Question category (PIAC): {category}
{rubric}

Also assess HALLUCINATION: a confident claim in the answer that is wrong or ungrounded — \
most often a fluent higher-level claim (affective or inferential) that rests on a wrong or \
absent lower-level (perceptual) observation, or a stated fact that contradicts the reference. \
If the answer hallucinates, set hallucinated=true and hallucination_level to the PIAC level \
of the failing claim (perceptual / inferential / affective / contextual); otherwise \
hallucinated=false and hallucination_level="none". Also rate grounding 0-1 (how well the \
answer ties its claims to observable audio features).

Question: {question}
Answer format expected: {answer_format}
Reference answer (one valid ground truth): {reference}
Model's answer: {answer}

Reply with ONLY a JSON object and nothing else:
{{"score": <int 0-4>, "grounded": <float 0-1>, "hallucinated": <true|false>, \
"hallucination_level": "<perceptual|inferential|affective|contextual|none>", \
"rationale": "<one short sentence>"}}"""

_LEVELS = set(CATEGORIES) | {"none"}


def build_prompt(category: str, question: str, reference: str, answer: str,
                 answer_format: str = "") -> str:
    strat = eval_strategy(category) or "graded_affective"
    return JUDGE_TEMPLATE.format(
        category=category or "unclassified",
        rubric=STRATEGY_RUBRIC.get(strat, STRATEGY_RUBRIC["graded_affective"]),
        question=str(question).strip(),
        answer_format=(answer_format or "a short answer").strip(),
        reference=str(reference).strip(),
        answer=str(answer).strip() or "(no answer given)",
    )


def _clamp_int(v, lo, hi):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _clamp_float(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def parse_judge(text: str) -> dict:
    score = grounded = None
    hallucinated, level, rationale = None, "none", ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            score = _clamp_int(obj.get("score"), 0, SCORE_MAX)
            grounded = _clamp_float(obj.get("grounded"))
            hv = obj.get("hallucinated")
            hallucinated = (bool(hv) if isinstance(hv, bool)
                            else str(hv).strip().lower() in ("true", "yes", "1"))
            lv = str(obj.get("hallucination_level", "none")).strip().lower()
            level = lv if lv in _LEVELS else "none"
            rationale = str(obj.get("rationale", "")).strip()[:300]
        except json.JSONDecodeError:
            pass
    if score is None:  # fall back to first standalone 0-4 digit
        d = re.search(r"\b([0-4])\b", text)
        score = int(d.group(1)) if d else None
    if not hallucinated:
        level = "none"
    norm = round(score / SCORE_MAX, 4) if score is not None else None
    verdict = ("correct" if norm == 1.0 else
               "incorrect" if norm in (0.0, None) else "partial")
    return {"score": score, "score_norm": norm, "verdict": verdict,
            "grounded": grounded, "hallucinated": bool(hallucinated),
            "hallucination_level": level, "rationale": rationale,
            "raw": text.strip()[:300]}


class PIACJudge:
    """Category-aware 0-4 judge + hallucination flag, backed by local Qwen3."""

    def __init__(self, judge_spec: str = "local", max_tokens: int = 220):
        self.client = make_client(judge_spec)
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return self.client.model_id

    def score(self, category: str, question: str, reference: str, answer: str,
              answer_format: str = "") -> dict:
        prompt = build_prompt(category, question, reference, answer, answer_format)
        reply = self.client.generate(prompt, max_tokens=self.max_tokens)
        out = parse_judge(reply)
        out["category"] = category
        out["eval_strategy"] = eval_strategy(category)
        return out

"""The PIAC taxonomy — the epistemic status of a musical claim.

Four categories, distinguished by the *nature of their ground truth*:

  perceptual   — measurable directly from the audio signal; single ground truth,
                 no reasonable disagreement.
  inferential  — derived through trained listening/analysis; expert consensus is
                 expected, though limited disagreement remains.
  affective    — the listener's subjective experience; no consensus expected.
  contextual   — factual world knowledge external to the signal; single ground truth.

This module is the single source of truth for the taxonomy (it supersedes the old
HEAR/ANALYZE/FEEL/KNOW ``Level`` taxonomy). It carries, per category, the full paper
definitions and — crucially — the **evaluation strategy** the LLM-as-judge applies
(see ``judge.py``). It also holds the **skill** vocabulary (what musical topic a
question probes), which reduces to *tone* and *time*.
"""

from __future__ import annotations

from dataclasses import dataclass

PIAC_ORDER = ["perceptual", "inferential", "affective", "contextual"]


@dataclass(frozen=True)
class Category:
    key: str            # perceptual / inferential / affective / contextual
    information: str     # what the content is
    ambiguity: str       # the nature of (dis)agreement
    coverage: str        # what falls in the category
    evaluation: str      # how an answer is evaluated
    example_q: str
    example_a: str
    eval_strategy: str   # machine key consumed by judge.py


CATEGORIES: dict[str, Category] = {
    "perceptual": Category(
        key="perceptual",
        information="Anything measurable from the audio itself; needs neither prior "
                    "knowledge nor active reasoning.",
        ambiguity="No reasonable disagreement given an answer format: a note is A4 or "
                  "it is not; an onset occurs at a time or it does not.",
        coverage="Objective signal-level attributes: pitch, timing, duration, bpm, loudness, "
                 "instrumentation, lyrics. NOT meter/time-signature (interpreted, e.g. "
                 "4/4 vs 2/2) — that is inferential.",
        evaluation="Exact semantic match, or match within a predefined tolerance.",
        example_q="What note is played by the violin at 0:31? Answer in scientific pitch "
                  "notation.",
        example_a="A4.",
        eval_strategy="binary_exact",
    ),
    "inferential": Category(
        key="inferential",
        information="Musical properties derived from the audio through trained listening "
                    "and analytical reasoning.",
        ambiguity="Intersubjective: trained listeners tend to converge, but some "
                  "disagreement remains possible.",
        coverage="Harmonic function, formal segmentation, phrase structure, genre "
                 "attribution, voice leading, other aspects of musical organization.",
        evaluation="Accept justified expert-annotated alternatives; a claim need only be "
                   "substantiable in perceptual content (traceable to observable features).",
        example_q="[B-flat grace note to an A over an A7 chord] What is the name of this "
                  "chord?",
        example_a="A7, or A9.",
        eval_strategy="binary_expert_multi",
    ),
    "affective": Category(
        key="affective",
        information="How the music is experienced by a listener — expression and "
                    "emotional response.",
        ambiguity="Subjective by definition; should NOT be resolved by consensus — there "
                  "is no single right answer.",
        coverage="Perceived mood, character, tension, intimacy, energy, aesthetic quality, "
                 "personal response.",
        evaluation="Accommodate multiple correct answers: judge plausibility (musically "
                    "reasonable), internal consistency, and grounding (affective claims "
                    "supported by perceptual/inferential references).",
        example_q="What is the most dramatic spot in the audio?",
        example_a="Any spot a listener could reasonably conceive as most dramatic.",
        eval_strategy="graded_affective",
    ),
    "contextual": Category(
        key="contextual",
        information="Factual, world knowledge information associated with the music through historical or "
                    "physical context; admits a single ground truth.",
        ambiguity="Not ambiguous in principle. When the fact is unknown, the correct "
                  "response is to acknowledge that uncertainty.",
        coverage="Composer, performer, title, date/period of recording, reception or "
                 "influence. (Detecting genre from audio is inferential, not contextual. Detecting location can be contextual if a documented fact, or inferential if deduced from reverberation.)",
        evaluation="Exact semantic match; a compatible answer of different specificity is "
                   "accepted (reference 'China' vs answer 'Beijing').",
        example_q="Who is the composer of the piece I just played?",
        example_a="Mozart.",
        eval_strategy="binary_contextual",
    ),
}

# Cross-cutting notes (fed to the classifier so the same query can shift category by
# the nature of its ground truth — e.g. recording location is contextual if a
# documented fact, inferential if deduced from reverberation).
FLEXIBILITY_NOTE = (
    "The SAME query can belong to different categories depending on the nature of its "
    "ground truth. 'Where was this recorded?' is contextual if the answer is a documented "
    "fact (a known studio), but inferential if it must be deduced from acoustic cues "
    "(room size from reverberation). Classify by what the correct answer fundamentally "
    "depends on, not by surface wording."
)

RULE_OF_THUMB = (
    "Rule of thumb: unambiguously extractable from the signal → perceptual; tied to the "
    "listener's subjective experience → affective; a non-debatable external fact about the "
    "piece → contextual; otherwise (trained analysis of the signal) → inferential."
)

# --- Skill vocabulary (what musical topic the question probes) --------------
# The paper reduces musical structure to TONE (pitch/loudness/timbre) and TIME
# (situating sound temporally), or their interaction. Skills are the concrete
# topics; each maps to a tone/time axis for aggregation.
SKILL_AXIS: dict[str, str] = {
    # tone
    "pitch": "tone", "timbre": "tone", "loudness": "tone", "instrumentation": "tone",
    "harmony": "tone", "chord": "tone", "key": "tone", "melody": "tone",
    # time
    "rhythm": "time", "tempo": "time", "onset": "time", "duration": "time",
    "meter": "time", "form": "time", "counting": "time",
    # tone×time / higher-order (interaction or beyond the tone/time core)
    "genre": "tone_time", "style": "tone_time", "lyrics": "tone_time",
    "emotion": "tone_time", "mood": "tone_time", "structure": "tone_time",
    "performer": "context", "composer": "context", "location": "context",
    "date": "context", "scene": "context", "other": "other",
}
SKILLS = list(SKILL_AXIS)


def eval_strategy(category: str) -> str:
    cat = CATEGORIES.get((category or "").strip().lower())
    return cat.eval_strategy if cat else ""


def describe(sep: str = "\n\n") -> str:
    """Full taxonomy block for classifier/judge prompts — Qwen sees every category
    definition, not just labels."""
    blocks = []
    for c in CATEGORIES.values():
        blocks.append(
            f"### {c.key}\n"
            f"- Information: {c.information}\n"
            f"- Ambiguity: {c.ambiguity}\n"
            f"- Coverage: {c.coverage}\n"
            f"- Evaluation: {c.evaluation}\n"
            f"- Example — Q: {c.example_q}  A: {c.example_a}"
        )
    return sep.join(blocks)

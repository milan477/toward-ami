"""The PIEC taxonomy — the epistemic status of a musical claim.

Four categories, distinguished by the *nature of their ground truth*:

  perceptual   — measurable directly from the audio signal; single ground truth,
                 no reasonable disagreement.
  inferential  — derived through trained listening/analysis or; general consensus is
                 desired and commonly possible, though disagreement can remain.
  experiential — the listener's subjective experience; consensus is neither
                 required nor desired.
  contextual   — factual world knowledge external to the signal; single ground truth.

This module is the single source of truth for the taxonomy (it supersedes the old
HEAR/ANALYZE/FEEL/KNOW ``Level`` taxonomy). It carries, per category, the full paper
definitions and — crucially — the **evaluation strategy** the LLM-as-judge applies
(see ``judge.py``). It also retains the content-to-axis mapping used by the site.
"""

from __future__ import annotations

from dataclasses import dataclass

PIEC_ORDER = ["perceptual", "inferential", "experiential", "contextual"]

RULE_OF_THUMB_ITEMS = [
    {"condition": "Unambiguously extractable from the signal", "category": "perceptual"},
    {"condition": "A listener's personal experience; no consensus sought", "category": "experiential"},
    {"condition": "A non-debatable external fact about the piece", "category": "contextual"},
    {"condition": "Through trained analysis of the signal or speech", "category": "inferential"},
]

MOTIVATION = {
    "body": [
        "PIEC is a framework that probes layered understanding of music. It distinguishes information that is directly perceived, inferred with general consensus as a goal, experienced personally without consensus as a goal, and known from external context.",
        "Consider the following examples. “How many notes are played in total in this audio?\" is a perceptual question, as it is directly measurable from the audio and admits a single ground truth. Therefore, its evaluation within an open-ended format is straightforward: an exact match requirement. The answer to “What does the music feel like?” shouldn't be converged on by consensus. The evaluation should admit multiple responses, using an LLM-as-a-judge or tailored similarity metrics.",
        "Beyond the level of ambiguity, these categories also represent different axes along which we want to probe the model's understanding of music. For instance, “Where is the first climax?” presumes a musical event with consensus about its relationship to the rest of the piece, and is therefore inferential. “Where does the first climax feel like it happens?” considers the question from a listener's subjective experience and is experiential. Accordingly, each question falls into one of the four categories, and both the question and its evaluation should be designed in accordance with the skill they intend to probe.",
        "More broadly, the taxonomy organizes the content of questions, their degree of ambiguity, and the evaluation methodology.",
    ],
}


@dataclass(frozen=True)
class Category:
    key: str            # perceptual / inferential / experiential / contextual
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
                    "knowledge nor active reasoning. There is a single, undeniable ground truth, and no room for personal judgment.",
        ambiguity="No reasonable disagreement given an answer format: a note is A4 or "
                  "it is not; an onset occurs at a time or it does not.",
        coverage="Objective signal-level attributes: pitch, timing, duration, bpm, loudness, "
                 "and instrumentation. Meter/time-signature (interpreted, e.g. 4/4 vs 2/2) is "
                 "inferential. There is also a disction between 'slows down' and 'plays slowly': the first can be measurable, the second needs to have a reference in order to be perceptual -- otherwise it is inferential.",
        evaluation="Exact semantic match, or match within a predefined tolerance.",
        example_q="What note is played by the violin at 0:31? Answer in scientific pitch "
                  "notation.",
        example_a="A4.",
        eval_strategy="binary_exact",
    ),
    "inferential": Category(
        key="inferential",
        information="Musical properties derived from the audio through listening "
                    "and analytical reasoning.",
        ambiguity="Intersubjective: general agreement is desired and/or trained listeners "
                  "commonly converge, although some disagreement remains possible, i.e. there might be other possible, though more unlikely, answers.",
        coverage="Questions answerable from speech alone, harmonic function, formal "
                 "segmentation, phrase structure, genre attribution, voice leading, environment inference, and "
                 "other aspects of musical organization.",
        evaluation="Accept justified expert-annotated alternatives; a claim need only be "
                   "substantiable in perceptual content (traceable to observable features).",
        example_q="[B-flat grace note to an A over an A7 chord] What is the name of this "
                  "chord?",
        example_a="A7, or A9.",
        eval_strategy="binary_expert_multi",
    ),
    "experiential": Category(
        key="experiential",
        information="How the music is personally experienced by the listener, including "
                    "felt mood, emotion, interpretation, tension, and direction.",
        ambiguity="Subjective by definition: consensus is neither required nor desired. "
                  "Different listeners may give equally valid incompatible answers.",
        coverage="A listener's felt mood, character, tension, direction, intimacy, energy, "
                 "aesthetic response, and personal interpretation. This excludes the "
                 "composer's inspiration, intention, or feelings: documented claims about "
                 "those are contextual, and unsupported claims are unknowable. Wording such as \"feels to you\" or \"in your experience\" or asking for emotions are strong evidence for experiential.",
        evaluation="Accommodate multiple correct answers: judge plausibility (musically "
                    "reasonable), internal consistency, and grounding (experiential claims "
                    "supported by perceptual/inferential references).",
        example_q="Where does the music feel most dramatic?",
        example_a="Any spot a listener could reasonably conceive as most dramatic.",
        eval_strategy="graded_experiential",
    ),
    "contextual": Category(
        key="contextual",
        information="Factual, world knowledge information associated with the music through historical or "
                    "physical context; admits a single ground truth.",
        ambiguity="Not ambiguous in principle. When the fact is unknown, the correct "
                  "response is to acknowledge that uncertainty.",
        coverage="Composer, performer, title, name of the piece, date/period of recording, reception or "
                 "influence. (Detecting genre from audio is inferential, not contextual. Detecting location can be contextual if a documented fact, or inferential if deduced from reverberation.)",
        evaluation="Exact semantic match; a compatible answer of different specificity is "
                   "accepted (reference 'China' vs answer 'Beijing').",
        example_q="Which song is this? What is the name of the composer?",
        example_a="Song name: 'Clair de Lune', Composer: Claude Debussy.",
        eval_strategy="binary_contextual",
    ),
}

RULE_OF_THUMB = (
    "Rule of thumb: unambiguously extractable from the signal → perceptual; tied to the "
    "listener's personal experience, with no consensus required or desired → experiential; "
    "a non-debatable external fact about the "
    "piece → contextual; otherwise (trained analysis of the signal) → inferential. "
    "If the question is answerable from the speech alone, it is inferential."
)


def eval_strategy(category: str) -> str:
    cat = CATEGORIES.get((category or "").strip().lower())
    return cat.eval_strategy if cat else ""


def row_piec(row) -> str:
    """Read a canonical PIEC value from an enhanced row."""
    direct = str(row.get("piec", "") or "").strip().lower()
    if direct in CATEGORIES:
        return direct
    legacy = str(row.get("category", "") or "").strip().lower()
    return legacy if legacy in CATEGORIES else ""


def describe(sep: str = "\n\n") -> str:
    blocks = []
    for c in CATEGORIES.values():
        blocks.append(
            f"### {c.key}\n"
            f"- Information: {c.information}\n"
            f"- Ambiguity: {c.ambiguity}\n"
            f"- Coverage: {c.coverage}\n"
        )
    return sep.join(blocks)

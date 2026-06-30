"""The four listener actions an ALM should perform: HEAR, ANALYZE, FEEL, KNOW.

This is the taxonomy at the centre of the study. It is NOT a hierarchy — an
interpretation is a combination of all four. It is audio-based, not score-based.
Each level carries the definition and the evaluation criterion used both in the
manual classification sheet and in the LLM-as-judge prompt.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Level:
    key: str            # HEAR / ANALYZE / FEEL / KNOW
    content: str        # the kind of content
    definition: str
    eval_criterion: str
    examples: tuple[str, ...]


LEVELS: dict[str, Level] = {
    "HEAR": Level(
        key="HEAR",
        content="Objective content — anything literally in the audio",
        definition=(
            "Measurable or factually extractable from the audio signal itself; "
            "the ground truth is computable from the audio. There is no reasonable "
            "disagreement: a frequency is A4 or it is not."
        ),
        eval_criterion="Exact match, or match within a defined tolerance.",
        examples=(
            "pitch", "tempo", "duration", "instrumentation", "dynamics/volume",
            "time signature", "lyrics",
        ),
    ),
    "ANALYZE": Level(
        key="ANALYZE",
        content="Intersubjective content — derivable through trained analysis",
        definition=(
            "Knowledge reachable from the signal through trained analysis, on which "
            "expert listeners reliably converge. Always grounded in objective content "
            "but requires interpretive mediation beyond measurement (e.g. recognizing "
            "a theme as a melody over a self-contained chord progression)."
        ),
        eval_criterion=(
            "Agreement with expert consensus; the claim must be traceable to "
            "observable audio features."
        ),
        examples=(
            "chord function", "harmonic progression", "formal/structural boundaries",
            "genre", "style", "voice leading", "phrase structure",
        ),
    ),
    "FEEL": Level(
        key="FEEL",
        content="Subjective content — what is felt, where consensus is not the goal",
        definition=(
            "Emotional effect, aesthetic quality, expressive character, listener "
            "preference. An answer cannot be simply right or wrong."
        ),
        eval_criterion=(
            "Plausibility, internal consistency, and grounding: the felt claim should "
            "be traceable to observable objective/intersubjective features (e.g. "
            "'tender' referencing soft dynamics, legato, resolved harmony)."
        ),
        examples=(
            "emotion conveyed", "mood", "aesthetic quality", "expressive character",
            "listener preference",
        ),
    ),
    "KNOW": Level(
        key="KNOW",
        content="World knowledge — non-debatable facts outside the music",
        definition=(
            "Facts about the music's place in the world, not derivable from the signal "
            "alone. Where a fact is genuinely unknown, that it is unknown is itself "
            "unambiguous."
        ),
        eval_criterion="Factual correctness against ground truth.",
        examples=(
            "composer", "name of the piece", "release/composition date", "performer",
            "how the piece lives on in the world",
        ),
    ),
}

KEYS = tuple(LEVELS.keys())


def describe(sep: str = "\n") -> str:
    """One-line-per-level description block, for prompts and the sheet header."""
    return sep.join(
        f"{lv.key}: {lv.content}. {lv.definition} "
        f"[eval: {lv.eval_criterion}] e.g. {', '.join(lv.examples)}."
        for lv in LEVELS.values()
    )

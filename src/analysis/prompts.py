"""Prompts for benchmark analysis annotations and labels."""

from __future__ import annotations

from .taxonomy import CATEGORIES, FLEXIBILITY_NOTE, RULE_OF_THUMB, SKILLS, describe


def category_block() -> str:
    return "\n".join(f"  - {name}: {cat.information} {cat.coverage}" for name, cat in CATEGORIES.items())


ANNOTATION_PROMPT = """You are annotating a question about an audio clip for a music-evaluation \
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
{categories}

{rule}

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

Question: {question}
Answer type: {qtype}
Reference answer (the CORRECT answer — do not reuse it): {answer}{options}

Reply with ONLY a JSON object and nothing else:
{{"answer_format": "<short phrase>", "category": "<perceptual|inferential|affective|contextual>", "rationale": "<one short sentence>", "example_answer": "<an incorrect option, same form as the reference>"}}"""


PIAC_PROMPT = """You classify a question about an audio clip into ONE epistemic category, \
by the NATURE of what a correct answer fundamentally depends on. The four PIAC categories:

{taxonomy}

{flexibility}

{rule}

Question: {question}
Reference answer (the correct answer): {reference}
Answer format: {answer_format}

Reply with ONLY a JSON object and nothing else:
{{"piac": "<perceptual|inferential|affective|contextual>", "rationale": "<one short sentence>"}}"""


SKILL_PROMPT = """You label what musical topic(s) a question about an audio clip probes.

Choose the applicable skill(s) from THIS fixed list (multiple allowed, most specific first):
{skills}

Guidance: tone skills = pitch, timbre, loudness, harmony, chord, key, melody, instrumentation.
time skills = rhythm, tempo, onset, duration, meter, form, counting. Higher-order = genre,
style, lyrics, emotion, mood, structure. External = performer, composer, location, date, scene.
Use "other" only if nothing fits. Pick 1-3 skills that best capture what the answer requires.

Question: {question}
Reference answer: {reference}
Answer format: {answer_format}

Reply with ONLY a JSON object and nothing else:
{{"skills": ["<skill>", ...], "rationale": "<one short sentence>"}}"""


ANALYSIS_PROMPT = """You are analyzing a benchmark question about an audio clip.

Ignore any separate distractor/options metadata from the dataset. Classify only the question
text itself and the reference answer.

Return five annotations:

1. question_nature: one of:
   - tfq: the question asks for true/false, yes/no, or equivalent binary truth.
   - mcq: the question embeds a closed set of choices in the question text itself, such as
     "indoors or outdoors" or "major or minor".
   - mlc: the question asks for a specific label/value such as a note, number, instrument,
     chord, tempo, location, or name.
   - oeq: the question invites a free-form description, explanation, or interpretation.

2. answer_format: the answer format as implied by the question and reference answer.

3. example_answer: a plausible answer in the same form as the reference answer. It may be
   the reference answer if that is the cleanest example of the answer space.

4. piac: one PIAC category:
{taxonomy}

{rule}

5. skills: one to three concise skills required to answer the question. Each skill must be
   at most three words, e.g. "melody identification", "pitch hearing",
   "spatial recognition".

Question: {question}
Reference answer: {reference}

Reply with ONLY this JSON object and nothing else:
{{
  "question_nature": {{"label": "<tfq|mcq|mlc|oeq>", "rationale": "<one short sentence>"}},
  "answer_format": {{"value": "<format as-is>", "rationale": "<one short sentence>"}},
  "example_answer": {{"value": "<example answer as-is>", "rationale": "<one short sentence>"}},
  "piac": {{"category": "<perceptual|inferential|affective|contextual>", "rationale": "<one short sentence>"}},
  "skills": {{"items": ["<skill>", "..."], "rationale": "<one short sentence>"}}
}}"""


def build_annotation_prompt(row: dict, options: str) -> str:
    return ANNOTATION_PROMPT.format(
        categories=category_block(),
        rule=RULE_OF_THUMB,
        question=str(row.get("question", "")).strip(),
        qtype=row.get("question_type", "") or "open-ended",
        answer=str(row.get("correct_answer", "")).strip(),
        options=options,
    )


def build_piac_prompt(question: str, reference: str, answer_format: str = "") -> str:
    return PIAC_PROMPT.format(
        taxonomy=describe(),
        flexibility=FLEXIBILITY_NOTE,
        rule=RULE_OF_THUMB,
        question=str(question).strip(),
        reference=str(reference).strip(),
        answer_format=(answer_format or "a short answer").strip(),
    )


def build_skill_prompt(question: str, reference: str, answer_format: str = "") -> str:
    return SKILL_PROMPT.format(
        skills=", ".join(SKILLS),
        question=str(question).strip(),
        reference=str(reference).strip(),
        answer_format=(answer_format or "a short answer").strip(),
    )


def build_analysis_prompt(question: str, reference: str) -> str:
    return ANALYSIS_PROMPT.format(
        taxonomy=describe(),
        rule=RULE_OF_THUMB,
        question=str(question).strip(),
        reference=str(reference).strip(),
    )

"""Prompts for benchmark decomposition into PIAC probe chains."""

from __future__ import annotations

from src.analysis.taxonomy import RULE_OF_THUMB, describe

DECOMPOSE_PROMPT = """You break a question about an audio clip into a short ORDERED CHAIN of \
simpler sub-questions ("probes") that build up to it. The chain lets us test an audio \
model's musical understanding at each level of the PIAC taxonomy and pinpoint WHERE it \
fails: a model may state the final answer fluently yet be wrong on the perceptual facts it \
should rest on.

The four PIAC levels, from least to most ambiguous:
{taxonomy}

{rule}

How to build the chain:
- Start from the most basic PERCEPTUAL observation and move UP one level at a time, each \
probe supplying the evidence the next one needs, ending with a final probe AT THE LEVEL of \
the original question (its category is given below).
- Every probe must be answerable by LISTENING to this audio (no outside knowledge, unless \
the original question is contextual).
- Give each probe its PIAC level, the sub-question, and the EXPECTED answer that is \
consistent with the known correct final answer — the LAST probe's expected answer is the \
reference answer itself. Keep expected answers short and concrete.
- Use 2 to 4 probes; do not repeat the original question except as the final probe.

Worked examples:
- "Is the location indoors or outdoors?" (contextual/inferential) →
    1. perceptual — "Is there audible reverberation or echo? (yes/no)"  expected: "yes"
    2. inferential — "How large does the enclosing space sound?"  expected: "a large room"
    3. contextual — "Is the location indoors or outdoors?"  expected: "indoors"
- "Which segment of music is played best?" (affective) →
    1. perceptual — "What instrument is playing?"  expected: "violin"
    2. inferential — "How many distinct segments are there?"  expected: "three"
    3. affective — "Which segment sounds best?"  expected: "the second segment"

Original question: {question}
Reference answer (correct): {reference}
PIAC category of the original question: {category}
Answer format: {answer_format}

Reply with ONLY a JSON object and nothing else:
{{"probes": [{{"level": "<perceptual|inferential|affective|contextual>", "question": "<sub-question>", "expected": "<short expected answer>"}}, ...]}}"""


def build_decompose_prompt(question: str, reference: str, category: str = "",
                           answer_format: str = "") -> str:
    return DECOMPOSE_PROMPT.format(
        taxonomy=describe(),
        rule=RULE_OF_THUMB,
        question=str(question).strip(),
        reference=str(reference).strip(),
        category=(category or "unspecified").strip(),
        answer_format=(answer_format or "a short answer").strip(),
    )

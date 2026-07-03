"""Qwen skill classification — what musical topic a question probes.

PIAC *category* is the epistemic axis (perceptual/inferential/affective/contextual)
and is already assigned by ``src.piac.annotate`` into ``data/benchmarks/<name>/<name>_ready.csv``.
This module adds the orthogonal *skill* axis: the concrete musical topic (pitch,
harmony, tempo, genre, emotion, composer, …), each mapping to a tone/time axis
(``taxonomy.SKILL_AXIS``). Skills let us report "apparent vs actual acquisition"
per musical topic, not just per epistemic category.

Backed by local Qwen3 (``make_client("local")``); resumable via a ``.skills.jsonl``.
"""

from __future__ import annotations

import json
import re

from models.client import make_client

from .taxonomy import (
    CATEGORIES, FLEXIBILITY_NOTE, RULE_OF_THUMB, SKILL_AXIS, SKILLS, describe,
)

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


def build_piac_prompt(question: str, reference: str, answer_format: str = "") -> str:
    return PIAC_PROMPT.format(
        taxonomy=describe(), flexibility=FLEXIBILITY_NOTE, rule=RULE_OF_THUMB,
        question=str(question).strip(), reference=str(reference).strip(),
        answer_format=(answer_format or "a short answer").strip(),
    )


def parse_piac(text: str) -> dict:
    piac, rationale = "", ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            piac = str(obj.get("piac", "")).strip().lower()
            rationale = str(obj.get("rationale", "")).strip()[:200]
        except json.JSONDecodeError:
            pass
    if piac not in CATEGORIES:  # fall back to first category word mentioned
        piac = next((c for c in CATEGORIES if re.search(rf"\b{c}\b", text, re.I)), "")
    return {"piac": piac, "piac_rationale": rationale}


class PIACClassifier:
    """PIAC category classifier using the full taxonomy definitions (local Qwen3)."""

    def __init__(self, spec: str = "local", max_tokens: int = 180):
        self.client = make_client(spec)
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return self.client.model_id

    def classify(self, question: str, reference: str, answer_format: str = "") -> dict:
        reply = self.client.generate(
            build_piac_prompt(question, reference, answer_format), max_tokens=self.max_tokens)
        return parse_piac(reply)

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


def build_prompt(question: str, reference: str, answer_format: str = "") -> str:
    return SKILL_PROMPT.format(
        skills=", ".join(SKILLS),
        question=str(question).strip(),
        reference=str(reference).strip(),
        answer_format=(answer_format or "a short answer").strip(),
    )


def parse_skills(text: str) -> dict:
    skills, rationale = [], ""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            raw = obj.get("skills", [])
            if isinstance(raw, str):
                raw = [raw]
            skills = [s.strip().lower() for s in raw if str(s).strip().lower() in SKILL_AXIS]
            rationale = str(obj.get("rationale", "")).strip()[:200]
        except json.JSONDecodeError:
            pass
    if not skills:  # fall back: any known skill word mentioned
        skills = [s for s in SKILLS if re.search(rf"\b{s}\b", text, re.I)][:3]
    # de-dupe, cap at 3
    seen, out = set(), []
    for s in skills:
        if s not in seen:
            seen.add(s)
            out.append(s)
    out = out[:3] or ["other"]
    axes = sorted({SKILL_AXIS.get(s, "other") for s in out})
    return {"skills": out, "skill_axes": axes, "skill_rationale": rationale}


class SkillClassifier:
    def __init__(self, spec: str = "local", max_tokens: int = 160):
        self.client = make_client(spec)
        self.max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        return self.client.model_id

    def classify(self, question: str, reference: str, answer_format: str = "") -> dict:
        reply = self.client.generate(build_prompt(question, reference, answer_format),
                                     max_tokens=self.max_tokens)
        return parse_skills(reply)

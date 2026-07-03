"""
Question category breakdown: load all questions from available loaders and
write a CSV with one row per question, including skills inferred from the
question text via keyword matching against the skill taxonomy.
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from catalog import load_all, load_items

_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "paper" / "figures"

FIELDS = ["benchmark", "question", "choices", "answer", "skills", "category", "sub_category"]

# Keywords that signal each skill. Order matters: checked top-to-bottom, all matches kept.
SKILL_KEYWORDS: dict[str, list[str]] = {
    # perception
    "pitch":      ["pitch", "note", "frequency", "higher", "lower", "sharp", "flat", "semitone", "octave", "tune", "in tune", "off.key"],
    "timbre":     ["timbre", "tone quality", "brightness", "warmth", "texture", "color", "tonal color", "sound quality"],
    "loudness":   ["loud", "quiet", "volume", "dynamic", "soft", "forte", "piano", "amplitude"],
    "rhythm":     ["rhythm", "rhythmic", "beat", "syncopat", "groove", "pattern", "pulse"],
    "tempo":      ["tempo", "bpm", "speed", "fast", "slow", "quick", "rapid", "pace"],
    "onset":      ["onset", "attack", "start", "beginning of the sound"],
    "duration":   ["duration", "length", "how long", "short", "brief", "extended"],
    # structure
    "melody":     ["melody", "melodic", "motif", "tune", "theme", "melodious"],
    "harmony":    ["harmony", "harmonic", "consonan", "dissonan", "chord progression"],
    "chord":      ["chord", "triad", "arpeggio", "voicing"],
    "key":        ["key", "major", "minor", "tonal", "tonality", "scale", "mode"],
    "meter":      ["meter", "time signature", "4/4", "3/4", "6/8", "beat pattern"],
    "form":       ["form", "structure", "section", "verse", "chorus", "bridge", "ABA", "rondo"],
    "polyphony":  ["polyphon", "counterpoint", "voice", "layered", "multiple instrument"],
    # knowledge
    "genre":      ["genre", "style", "classical", "jazz", "rock", "pop", "blues", "folk", "hip.hop", "electronic", "country", "reggae", "opera", "type of music"],
    "style":      ["style", "period", "baroque", "romantic", "modernist", "impressionist", "contemporary"],
    "instrument": ["instrument", "guitar", "piano", "violin", "drum", "bass", "trumpet", "flute", "cello", "saxophone", "viola", "oboe", "clarinet", "singer", "vocal", "voice"],
    "era":        ["era", "century", "period", "decade", "year", "historical", "ancient", "medieval", "renaissance"],
    "composer":   ["composer", "composed by", "written by", "artist", "musician", "performer", "who made", "who wrote", "who sang"],
    "theory":     ["theory", "interval", "cadence", "modulation", "transposition", "counterpoint"],
    # reasoning
    "comparison": ["compare", "which is", "better", "worse", "more", "less", "differ", "same", "similar", "contrast", "versus"],
    "counting":   ["how many", "count", "number of", "total"],
    "ordering":   ["order", "rank", "first", "second", "third", "sequence", "before", "after"],
    "analogy":    ["analogy", "like", "similar to", "resembles", "comparable"],
    "inference":  ["suggest", "imply", "indicate", "conclude", "infer", "most likely", "probable", "suitable for"],
    # affect
    "emotion":    ["emotion", "feel", "feeling", "express", "mood", "sentiment", "convey", "evoke"],
    "mood":       ["mood", "atmosphere", "vibe", "ambiance"],
    "valence":    ["positive", "negative", "pleasant", "unpleasant", "happy", "sad", "joyful", "melanchol", "upbeat", "dark"],
    "arousal":    ["energetic", "calm", "exciting", "relaxing", "intense", "soothing", "arousal", "lively"],
}

_COMPILED = {skill: re.compile("|".join(kws), re.IGNORECASE) for skill, kws in SKILL_KEYWORDS.items()}


def infer_skills(question: str) -> list[str]:
    return [skill for skill, pattern in _COMPILED.items() if pattern.search(question)]


def question_category_breakdown(benchmarks: list[dict], out_dir: Path = _DEFAULT_OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for b in benchmarks:
        name = b["name"]
        questions = load_items(name)
        if not questions:
            print(f"  No normalized data for {name}, skipping.")
            continue
        for q in questions:
            skills = infer_skills(q["question"])
            rows.append({
                "benchmark":    name,
                "question":     q["question"],
                "choices":      "|".join(q["choices"]) if q.get("choices") else "",
                "answer":       q["answer"],
                "skills":       "|".join(skills),
                "category":     q.get("category", ""),
                "sub_category": q.get("sub_category", ""),
            })
        print(f"  {name}: {len(questions)} questions")

    csv_path = out_dir / "question_categories.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved question_categories.csv ({len(rows)} questions)")


if __name__ == "__main__":
    benchmarks = load_all()
    question_category_breakdown(benchmarks)

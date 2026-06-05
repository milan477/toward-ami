"""
Gap analysis: which skills are underrepresented, and across how many
test conditions (instrument × duration × format × ...) do they appear?
"""

from collections import defaultdict
from catalog import load_all

# Full taxonomy of skills we care about — every leaf we'd want covered.
SKILL_TAXONOMY = {
    "perception": ["pitch", "timbre", "loudness", "rhythm", "tempo", "onset", "duration"],
    "structure":  ["melody", "harmony", "chord", "key", "meter", "form", "polyphony"],
    "knowledge":  ["genre", "style", "instrument", "era", "composer", "theory"],
    "reasoning":  ["comparison", "counting", "ordering", "analogy", "inference"],
    "affect":     ["emotion", "mood", "valence", "arousal"],
}

ALL_SKILLS = [s for skills in SKILL_TAXONOMY.values() for s in skills]


def gap_report(benchmarks: list[dict]) -> None:
    coverage: dict[str, list[str]] = defaultdict(list)
    for b in benchmarks:
        for skill in b.get("primary_skill") or []:
            coverage[skill].append(b["name"])

    print("=" * 60)
    print("SKILL COVERAGE REPORT")
    print("=" * 60)
    for category, skills in SKILL_TAXONOMY.items():
        print(f"\n[{category.upper()}]")
        for skill in skills:
            benches = coverage.get(skill, [])
            tag = "OK" if len(benches) >= 2 else ("WEAK" if len(benches) == 1 else "MISSING")
            bench_str = ", ".join(benches) if benches else "—"
            print(f"  {tag:7s}  {skill:20s}  ({len(benches)} benchmark(s): {bench_str})")

    missing = [s for s in ALL_SKILLS if not coverage.get(s)]
    weak = [s for s in ALL_SKILLS if len(coverage.get(s, [])) == 1]
    print(f"\nSummary: {len(missing)} missing skills, {len(weak)} weakly covered skills")
    print("Missing:", missing or "none")
    print("Weak:   ", weak or "none")


if __name__ == "__main__":
    benchmarks = load_all()
    gap_report(benchmarks)

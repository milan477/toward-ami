"""
Gap analysis: which skills are underrepresented, and across how many
test conditions (instrument × duration × format × ...) do they appear?
"""

from collections import defaultdict
from pathlib import Path
from catalog import load_all

_DEFAULT_OUT = Path(__file__).parent.parent / "paper" / "figures"

SKILL_TAXONOMY = {
    "perception": ["pitch", "timbre", "loudness", "rhythm", "tempo", "onset", "duration"],
    "structure":  ["melody", "harmony", "chord", "key", "meter", "form", "polyphony"],
    "knowledge":  ["genre", "style", "instrument", "era", "composer", "theory"],
    "reasoning":  ["comparison", "counting", "ordering", "analogy", "inference"],
    "affect":     ["emotion", "mood", "valence", "arousal"],
}

ALL_SKILLS = [s for skills in SKILL_TAXONOMY.values() for s in skills]


def gap_report(benchmarks: list[dict], out_dir: Path = _DEFAULT_OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    coverage: dict[str, list[str]] = defaultdict(list)
    for b in benchmarks:
        for skill in b.get("primary_skill") or []:
            coverage[skill].append(b["name"])

    lines = []
    lines.append("=" * 60)
    lines.append("SKILL COVERAGE REPORT")
    lines.append("=" * 60)
    for category, skills in SKILL_TAXONOMY.items():
        lines.append(f"\n[{category.upper()}]")
        for skill in skills:
            benches = coverage.get(skill, [])
            tag = "OK" if len(benches) >= 2 else ("WEAK" if len(benches) == 1 else "MISSING")
            bench_str = ", ".join(benches) if benches else "—"
            lines.append(f"  {tag:7s}  {skill:20s}  ({len(benches)} benchmark(s): {bench_str})")

    missing = [s for s in ALL_SKILLS if not coverage.get(s)]
    weak = [s for s in ALL_SKILLS if len(coverage.get(s, [])) == 1]
    lines.append(f"\nSummary: {len(missing)} missing skills, {len(weak)} weakly covered skills")
    lines.append("Missing: " + (", ".join(missing) if missing else "none"))
    lines.append("Weak:    " + (", ".join(weak) if weak else "none"))

    report = "\n".join(lines)
    print(report)
    (out_dir / "gap_report.txt").write_text(report)
    print(f"Saved gap_report.txt")


if __name__ == "__main__":
    benchmarks = load_all()
    gap_report(benchmarks)

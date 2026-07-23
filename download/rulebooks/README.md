# Raw-to-normalized rulebooks

Each rulebook is the source-of-truth specification for one deterministic
`<benchmark>_raw.csv` → `<benchmark>_normalized.csv` conversion. The Python
normalizer in `download/benchmark_<name>.py` implements that rulebook.
Every benchmark rulebook must contain one table row for each of the nine common
fields and one table row for every benchmark-specific category column. Tests
compare those documented rows with the generated normalized CSV header.

Every normalized CSV starts with exactly these common columns:

`qid, bench, focus, question, answer, distractors, url, input_modality, output_modality`

`focus`, `answer`, `distractors`, `url`, and `input_modality` are JSON lists.
All additional columns are creator-provided taxonomies named
`category_<level>_<source_name>`. The level records the benchmark-specific
ordering documented in its rulebook; the source name prevents different
creator concepts from being conflated.

A raw column is omitted from the creator-category columns when its information
is already fully represented by a common normalized feature. For example, an
audio-domain column mapped completely into `focus` is not repeated as a
category. Parallel non-empty creator arrays may instead contribute their parent
labels to one category list, avoiding separate duplicate columns.

Normalization never calls an LLM. The enhanced stage copies every normalized
column and adds only `content_skill`, `piec`, and `question_nature`.
`content_skill` is a JSON list of two-item `[content, skill]` pairs, the CSV-safe
representation of a list of tuples.

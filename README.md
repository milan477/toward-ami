# Welcome to the official repository toward Artificial Musical Intelligence

This repository is designed to be a continuously-updated resource for training Audio-Language models or multimodal models that listen to audio and to let researchers collectively and organically define what Artificial Musical Intelligence should look like. Feel free to fork the repository to add benchmarks, models, or scores. 

## Interactive Benchmark Explorer

![Benchmark statistics dashboard](data/screenshots/screenshot_statistics.png)

The website includes an inspectable benchmark view for browsing the questions
behind each dataset. Researchers can filter a benchmark by modality, category,
action, and PIEC label, then immediately see the filtered question count, average
audio duration, and average number of distractors. The same view summarizes the
filtered subset with compact visual diagnostics: a sound-duration histogram and
pie charts for distractors, modality, category, action, and PIEC distribution.
Long category legends stay compact with a `show all` control.

Benchmark audio is hosted once on Hugging Face under
`milan477/toward-ami`. The committed website data stores only question metadata
and hosted audio URLs, so the cards play those clips directly without keeping
the multi-gigabyte audio corpus in git or under `docs/`. Local `data/audio/`
files are just a generated cache for downloading, rebuilding duration stats, or
running experiments.

Screenshots of these website states live in `data/screenshots/` as visual
references for the site functionality.

## Benchmark data pipeline

Normalization is deterministic and benchmark-specific. It maps local raw CSVs
to the source-extractable shared schema `qid, bench, focus, question, answer,
distractors, url, input_modality, output_modality`. Creator taxonomies are kept
in self-describing ordered columns such as `category_1_category` and
`category_2_subcategory`. Every mapping decision is documented under
`download/rulebooks/`.

```bash
python download/normalize.py mmar
python download/normalize.py all
```

The LLM enhancement stage reads `<name>_normalized_selected.csv` and writes
`<name>_normalized_selected_enhanced.csv`. One structured call per question adds open-ended
`action_content` pairs, PIEC, inherent question nature, a precise answer format,
and an example incorrect answer (blank for true/false); all creator category
columns are included as prompt context. Model, git commit, run configuration,
rendered prompt, and raw response are retained in the enhancement JSONL sidecar,
while the enhanced CSV adds only those five standardized columns.
Because CSV has no tuple type, `action_content` is serialized as JSON, e.g.
`[["identify", "pitch"], ["compare", "harmony"]]`.

Before an unanswered row is enhanced, an audio-capable transcriber produces a
speech transcript and injects it into the classification prompt. Transcripts and
their model, prompt, git commit, and audio-path provenance are cached in
`.<name>.normalized_selected.transcriptions.jsonl`. For now, the transcript is
also exposed in a `transcription` column in the enhanced CSV. For MMAR, only rows whose `focus` contains `speech`
are transcribed. By default the judge is reused when it supports audio; use
`--transcriber <model-spec>` to choose another audio-capable backend. When an
eligible row needs transcription and the judge is text-only, `--transcriber` is
required; the pipeline does not silently analyze that row without STT.

The same preprocessing flow creates `question_oeq` and `answer_oeq`: a maximally
open-ended rewrite placed immediately after `question`, plus its self-contained
reference answer placed after `answer`. Rewrites use
the known answer, distractors, creator metadata, and transcript to disambiguate
the task, but are instructed not to expose answer-derived hints or unnecessary
setup. Binary answers are expanded only into facts logically established by the
original pair (for example, `No` becomes `The scream` when asking which element
is not part of the music). Full rewrite provenance is cached in
`.<name>.normalized_selected.question_oeq.jsonl`. Existing enhanced files can be
backfilled without rerunning their analysis annotations:

```bash
python -m src.run analysis rewrite-questions mmar --limit 20 \
  --model openrouter:google/gemini-3-flash-preview
```

```bash
python -m src.run analysis enhance mmar --limit 20
python -m src.run analysis enhance mmar --limit 20 \
  --judge openrouter:google/gemini-3-flash-preview \
  --transcriber openrouter:google/gemini-3-flash-preview
python -m src.run analysis pipeline mmar
```

The enhancement pipeline also creates `question_task`, an imperative,
meaning-preserving formulation of the original question. Each candidate is
checked by a separate equivalence/imperative validation call before it is added
to `<name>_normalized_selected_enhanced.csv`; prompts, responses, validation,
model information, and rationale are stored in adjacent provenance columns and
the generated JSONL cache. Choose the model independently when needed:

```bash
python -m src.run analysis pipeline mmar \
  --task-rewriter openrouter:google/gemini-3-flash-preview
```

Experiments 2, 3, 5, and 6 consume analysis-time columns from the enhanced CSV;
they do not transcribe or rewrite questions during an experiment run.

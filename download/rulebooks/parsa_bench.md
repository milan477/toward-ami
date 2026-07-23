# PARSA-Bench

Row rule: concatenate the task CSVs in the declared `CSV_FILES` order; one raw
row becomes one normalized row. Because task schemas differ, source values use
the ordered field-name fallback lists in `benchmark_parsa_bench.py`.

## Normalized-field rules

| Normalized field | Source | Rule |
|---|---|---|
| `qid` | normalized row position | Assign `parsa_bench_q_<n>` using the 1-based order of the concatenated task rows. |
| `bench` | constant | Set to `parsa_bench`. |
| `focus` | benchmark definition | Set to `["speech"]`. |
| `question` | question fallback fields | Take the first non-empty value among `question`, `instruction`, `prompt`, `input`, `text`, `sentence`, `query`, `utterance`, and `transcription`. |
| `answer` | answer fallback fields | Take the first non-empty answer/label/target field, resolve it against choices when present, and store it as `[answer]` or `[]`. |
| `distractors` | choice fallback fields | Parse `choices`, `options`, or lettered option columns; remove the resolved answer and store the remainder as a JSON list. |
| `url` | audio-path fallback fields | Use the first audio/path/file field; when absent, build `<task>/unknown_<zero-based-row>.wav`. Store as a one-item list. |
| `input_modality` | benchmark interface | Set to `["audio", "text"]`. |
| `output_modality` | benchmark interface | Set to `text`. |
| `category_1_task` | `task` | Copy the creator task directory derived from the source CSV path. |
| `category_2_task_file` | `task_file` | Copy the full creator task CSV path. |

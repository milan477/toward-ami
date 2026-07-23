# PitchBench

Row rule: one raw row produces one normalized row for each non-empty
prompt/answer representation among MIDI, ABC, solfège, and frequency. It can
therefore produce up to four normalized rows.

## Normalized-field rules

| Normalized field | Source | Rule |
|---|---|---|
| `qid` | expanded normalized row position | Assign `pitchbench_q_<n>` using the 1-based order after subset grouping and representation expansion. |
| `bench` | constant | Set to `pitchbench`. |
| `focus` | benchmark definition | Set to `["music"]`. |
| `question` | selected `prompt_<format>` | Collapse whitespace and copy the prompt for the current representation. |
| `answer` | selected `gt_<format>` | Store the ground-truth value for the current representation as a one-item JSON list. |
| `distractors` | no source distractors | Set to `[]`. |
| `url` | `subset`, `audio_path` | Build the subset-relative audio path and store it as a one-item list. |
| `input_modality` | benchmark interface | Set to `["audio", "text"]`. |
| `output_modality` | benchmark interface | Set to `text`. |
| `category_1_subset` | `subset` | Remove the `pitchbench_<experiment>_` prefix, replace underscores with spaces, and capitalize the resulting tested-skill label. |
| `category_2_source` | `source` | Replace underscores with spaces, capitalize, and store the creator source label. |
| `category_3_answer_format` | expanded representation | Store `midi`, `abc`, `solfege`, or `freq` for the current expanded question. |

Task-generation parameters remain in raw.

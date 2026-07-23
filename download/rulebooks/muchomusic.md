# MuChoMusic

Row rule: one raw row becomes one normalized row.

## Normalized-field rules

| Normalized field | Source | Rule |
|---|---|---|
| `qid` | normalized row position | Assign `muchomusic_q_<n>` using the 1-based source-row order. |
| `bench` | constant | Set to `muchomusic`. |
| `focus` | benchmark definition | Set to `["music"]`. |
| `question` | `question` | Collapse whitespace and copy as one string. |
| `answer` | `correct_answer` | Resolve against all four options and store as a one-item JSON list. |
| `distractors` | `distractor_1_answer`, `distractor_2_answer`, `distractor_3_answer` | Store the three non-answer options as a JSON list. |
| `url` | `dataset`, `dataset_identifier` | Build `<dataset>:<dataset_identifier>` and store it as a one-item list. |
| `input_modality` | benchmark interface | Set to `["audio", "text"]`. |
| `output_modality` | benchmark interface | Set to `text`. |
| `category_1_category` | `music_knowledge`, `music_reasoning` | Start with `[]`; add `knowledge` when `music_knowledge` is non-empty and add `reasoning` when `music_reasoning` is non-empty. Store the resulting labels as one JSON list. |
| `category_2_skills` | `music_knowledge`, `music_reasoning` | Merge the two arrays in knowledge-then-reasoning order, remove duplicates, and store the detailed creator skills as one JSON list. |
| `category_3_genre` | `genre` | Copy the creator-provided genre label. |

The detailed knowledge/reasoning arrays share `category_2_skills` rather than
becoming two columns.
Annotation-quality measurements and source identifiers remain in raw; only the
source identifiers used to construct `url` enter normalized.

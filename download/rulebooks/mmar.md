# MMAR

Row rule: one raw row becomes one normalized row.

## Normalized-field rules

| Normalized field | Source | Rule |
|---|---|---|
| `qid` | normalized row position | Assign `mmar_q_<n>` using the 1-based source-row order. |
| `bench` | constant | Set to `mmar`. |
| `focus` | `modality` | Extract every atomic value among `music`, `speech`, and `sound`; store as a JSON list. |
| `question` | `question` | Collapse whitespace and copy as one string. |
| `answer` | `answer`, `choices` | Resolve option text, letter, or index against `choices`; store the result as a one-item list. |
| `distractors` | `choices`, resolved answer | Remove the resolved answer and store the remaining choices as a JSON list. |
| `url` | `audio_path` | Store the clip path as a one-item JSON list. |
| `input_modality` | benchmark interface | Set to `["audio", "text"]`. |
| `output_modality` | benchmark interface | Set to `text`. |
| `category_1_category` | `category` | Copy the creator's top-level category. |
| `category_2_subcategory` | `sub-category` | Copy the creator's lower-level category. |
| `category_3_language` | `language` | Copy the creator-provided language label. |
| `category_4_source` | `source` | Copy the creator-provided source label. |

`modality` is represented by `focus` and is not duplicated as a category.

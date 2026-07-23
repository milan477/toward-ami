# MMAU

Row rule: parse `other_attributes` as JSON; one raw row becomes one normalized
row.

## Normalized-field rules

| Normalized field | Source | Rule |
|---|---|---|
| `qid` | normalized row position | Assign `mmau_q_<n>` using the 1-based source-row order. |
| `bench` | constant | Set to `mmau`. |
| `focus` | `other_attributes.task` | Extract every atomic value among `music`, `speech`, and `sound`; store as a JSON list. |
| `question` | `instruction` | Collapse whitespace and copy as one string. |
| `answer` | `answer`, `choices` | Resolve option text, letter, or index against `choices`; store as a one-item list. |
| `distractors` | `choices`, resolved answer | Remove the resolved answer and store the remaining choices as a JSON list. |
| `url` | `other_attributes.id` | Build `<id>.wav`; fall back to the zero-based raw row id when `id` is absent; store as a one-item list. |
| `input_modality` | benchmark interface | Set to `["audio", "text"]`. |
| `output_modality` | benchmark interface | Set to `text`. |
| `category_1_category` | `other_attributes.category` | Copy the creator's top-level category. |
| `category_2_subcategory` | `other_attributes.sub-category` | Copy the creator's lower-level category. |
| `category_3_difficulty` | `other_attributes.difficulty` | Copy the creator-provided difficulty label. |

`other_attributes.task` is represented by `focus` and is not duplicated as a
category.

# AHA

Row rule: retain the source `test` split; `train` remains in raw only. One
retained raw row becomes one normalized row.

## Normalized-field rules

| Normalized field | Source | Rule |
|---|---|---|
| `qid` | normalized row position | Assign `aha_q_<n>`, where `n` is the 1-based position after filtering to `test`. |
| `bench` | constant | Set to `aha`. |
| `focus` | benchmark definition | Set to `["sound"]` because AHA questions concern audio events. |
| `question` | `prompt` | Collapse whitespace and copy as one string. |
| `answer` | `chosen` | Store the non-empty chosen response as `[chosen]`; otherwise `[]`. |
| `distractors` | `rejected` | Store `[rejected]` only when it is non-empty and differs from `chosen`; otherwise `[]`. |
| `url` | `audio` | Store the source audio reference as a one-item JSON list. |
| `input_modality` | benchmark interface | Set to `["audio", "text"]`. |
| `output_modality` | benchmark interface | Set to `text`. |
| `category_1_split` | `split` | Copy the creator-provided split label; normalized rows therefore contain `test`. |

`caption` is source context rather than a creator category and remains in raw.

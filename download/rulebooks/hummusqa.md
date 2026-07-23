# HumMusQA

Row rule: one raw row becomes one normalized row.

## Normalized-field rules

| Normalized field | Source | Rule |
|---|---|---|
| `qid` | normalized row position | Assign `hummusqa_q_<n>` using the 1-based source-row order. |
| `bench` | constant | Set to `hummusqa`. |
| `focus` | benchmark definition | Set to `["music"]`. |
| `question` | `Question` | Collapse whitespace and copy as one string. |
| `answer` | `True answer` | Resolve against all four options and store as a one-item JSON list. |
| `distractors` | `Distractor 1`, `Distractor 2`, `Distractor 3` | Store the three non-answer options as a JSON list. |
| `url` | `Song link`, normalized row position | Build the downloaded excerpt name `q<n>_<track-id>.mp3` and store it as a one-item list. |
| `input_modality` | benchmark interface | Set to `["audio", "text"]`. |
| `output_modality` | benchmark interface | Set to `text`. |
| `category_1_main_category` | `Main Category` | Copy the creator's main category verbatim after whitespace cleanup. |
| `category_2_secondary_categories` | `Secondary Categories` | Split the semicolon-delimited labels and store them as a JSON list. |
| `category_3_difficulty` | `Difficulty` | Copy the creator-provided difficulty label. |

Track, artist, album, and license fields are metadata rather than categories and
remain in raw.

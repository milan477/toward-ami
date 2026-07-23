# MMAU-Pro

Row rule: one raw row becomes one normalized row.

## Normalized-field rules

| Normalized field | Source | Rule |
|---|---|---|
| `qid` | normalized row position | Assign `mmau_pro_q_<n>` using the 1-based source-row order. |
| `bench` | constant | Set to `mmau_pro`. |
| `focus` | `category`, `sub-cat` | Extract `music`, `speech`, or `sound`; additionally map `voice_chat` to speech and `spatial_audio` to sound. Store as a JSON list. |
| `question` | `question` | Collapse whitespace and copy as one string. |
| `answer` | `answer`, `choices` | Resolve the answer against `choices`; store `[answer]`, or `[]` for rows without an answer. |
| `distractors` | `choices`, resolved answer | Remove the resolved answer and store every remaining choice as a JSON list. |
| `url` | `audio_path` | Preserve the complete source array as a JSON list, including multi-clip questions. |
| `input_modality` | benchmark interface | Set to `["audio", "text"]`. |
| `output_modality` | benchmark interface | Set to `text`. |
| `category_1_category` | `perceptual_skills`, `reasoning_skills` | Start with `[]`; add `perceptual` when `perceptual_skills` is non-empty and add `reasoning` when `reasoning_skills` is non-empty. Store the resulting labels as one JSON list. |
| `category_2_skills` | `perceptual_skills`, `reasoning_skills` | Merge the two arrays in perceptual-then-reasoning order, remove duplicates, and store the detailed creator skills as one JSON list. |
| `category_3_subcategory` | `sub-cat` | Copy the creator's lower-level category. |
| `category_4_task_classification` | `task_classification` | Copy the creator-provided task classification. |
| `category_5_task_identifier` | `task_identifier` | Copy the creator-provided task identifier. |
| `category_6_length_type` | `length_type` | Copy the creator-provided clip-length class. |

The raw `category` audio-domain value is already fully represented by `focus`,
so it is not repeated. The two detailed skill arrays share `category_2_skills`
rather than becoming two columns. `transcription` and `kwargs` are source
metadata rather than creator categories and remain in raw.

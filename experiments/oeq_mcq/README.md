# MCQ vs OEQ study (MMAR music subset)

Tests whether multiple-choice (MCQ) inflates ALM scores relative to open-ended
(OEQ), broken down by the four listener actions: **HEAR / ANALYZE / FEEL / KNOW**
(see `taxonomy.py`).

## Pipeline

| Step | Module | What it does |
|------|--------|--------------|
| 1–2 | `sample.py` | Pull the MMAR music subset (`data/cleaned/mmar.csv`), draw a stratified ~50-question sheet, write `data/classification.csv` for **manual** level labelling. |
| 3 | `prompts.py` | Build MCQ (shuffled lettered options) and OEQ ("answer in 1–2 sentences", options stripped) variants. |
| 4 | `run.py` | Query one model with both variants **+ audio**. MCQ graded automatically. |
| 5 | `judge.py` | LLM-as-judge scores each OEQ answer for **accuracy + grounding**, using the level's eval criterion. |
| 6 | `table.py` | MCQ-vs-OEQ table per level, with the **Gap (MCQ−OEQ)**. |

## Run it

```bash
# 1-2. sample, then hand-label the `level` column (HEAR/ANALYZE/FEEL/KNOW)
python -m experiments.oeq_mcq.sample --n 50
#      → edit experiments/oeq_mcq/data/classification.csv  (see LEVELS.txt)

# 4. run both variants on a model (audio sent when supported)
python -m experiments.oeq_mcq.run --model flamingo
python -m experiments.oeq_mcq.run --model openai:gpt-4o-audio-preview
python -m experiments.oeq_mcq.run --model openrouter:google/gemini-2.0-flash-001
python -m experiments.oeq_mcq.run --model flamingo --preview      # prompts only, no calls

# 5. judge the OEQ answers (latest run by default)
python -m experiments.oeq_mcq.judge --judge openai:gpt-4o

# 6. build the table
python -m experiments.oeq_mcq.table
```

## Models & keys

Model specs (`--model` / `--judge`), see `experiments/helpers/models.py`:

- `flamingo` — local Audio Flamingo server (`models/audio-flamingo-next-instruct.py`),
  start it first; URL via `FLAMINGO_URL` (default `http://localhost:8001`).
- `openai:<model>` — needs `OPENAI_API_KEY`. Audio-capable models (e.g.
  `gpt-4o-audio-preview`) receive the clip; others get text only.
- `openrouter:<vendor/model>` — needs `OPENROUTER_API_KEY`. Audio sent when the
  model id looks audio-capable.

Outputs land in `experiments/results/exp_3_oeq_vs_mcq/<timestamp>/`
(`results_*.json`, `judged_*.json`, `table.md`, `table.csv`) — committed, never
overwritten, with full model/prompt/commit metadata.

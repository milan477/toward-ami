# MMAR Music Understanding Explorer — static site

A self-contained GitHub Pages site that browses the benchmark questions with
audio, shows each question's PIAC category, lets you compare model answers
(MCQ + open-ended, with hallucination flags), and has an overview results table
plus a Prompts tab.

## Targeted Updates

```bash
python renderers/site/build_site.py --list
python renderers/site/build_site.py --target questions --no-audio
python renderers/site/build_site.py --target benchmarks
python renderers/site/build_site.py --target prompts
```

The builder is intentionally target-based: update only the generated artifact
that changed instead of rewriting the whole website. Repeat `--target` to update
multiple specific pieces in one command.

Targets:

- `questions` writes `docs/data/questions.json` and `docs/data/benchmark_questions.json`.
- `benchmarks` writes `docs/data/benchmarks.json`.
- `models` writes `docs/data/models.json`.
- `overview` writes `docs/data/overview.json`.
- `evaluation` writes `docs/data/evaluation.json`.
- `prompts` writes `docs/data/prompts.json`.
- `news` writes `docs/data/news.json`.
- `meta` writes `docs/data/meta.json`.
- `paper` copies `paper/paper.pdf` to `docs/paper.pdf`.
- `audio` transcodes source clips into `docs/audio/`.

Inputs (all committed except the audio/data sources, which are generated):

- `data/benchmarks/mmar/mmar_normalized_selected_annotated.csv` — questions + PIAC categories (join key: audio stem)
- `results/<benchmark>/<model>/…` — MCQ summaries + PIAC-judged OEQ answers
- `data/audio/mmar/*.wav` — source clips, transcoded to mono OGG/Vorbis (~45 MB
  total) so the payload fits GitHub Pages

Output is the fully static `docs/` folder: hand-authored `index.html`,
`styles.css`, `app.js`, targeted generated `data/*.json`, and optional
`audio/*.ogg`.

## Publish on GitHub Pages

1. Commit `docs/` (including `docs/audio/`).
2. Repo **Settings → Pages → Build and deployment → Deploy from a branch**.
3. Branch **`main`**, folder **`/docs`**. Save.

The site is entirely client-side (no build step on GitHub's side; `.nojekyll`
disables Jekyll processing).

# MMAR Music Understanding Explorer — static site

A self-contained GitHub Pages site that browses the MMAR music questions with
audio, shows each question's PIAC category, lets you flip between **Audio Flamingo
Next** and **Gemini 3 Flash** answers (MCQ + open-ended, with hallucination
flags), and has an overview results table plus a Prompts tab.

## Build

```bash
python renderers/site/build_site.py            # transcode audio (WAV→OGG) + emit docs/data/
python renderers/site/build_site.py --no-audio # data only (reuse existing docs/audio/*.ogg)
```

Inputs (all committed except the audio/data sources, which are generated):

- `data/benchmarks/mmar/mmar_ready.csv` — questions + PIAC categories (join key: audio stem)
- `results/mmar/af-next/…` and `results/mmar/gemini-3-flash-preview/…` — MCQ
  summaries + PIAC-judged OEQ answers
- `data/audio/mmar/*.wav` — source clips, transcoded to mono OGG/Vorbis (~45 MB
  total) so the payload fits GitHub Pages

Output is the fully static `docs/` folder: `index.html`, `styles.css`, `app.js`,
`data/*.json`, `audio/*.ogg`.

## Publish on GitHub Pages

1. Commit `docs/` (including `docs/audio/`).
2. Repo **Settings → Pages → Build and deployment → Deploy from a branch**.
3. Branch **`main`**, folder **`/docs`**. Save.

The site is entirely client-side (no build step on GitHub's side; `.nojekyll`
disables Jekyll processing).

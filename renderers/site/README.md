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
- `literature-results` rebuilds `data/results/literature_results.sqlite3` from
  checked-in, source-tagged extracts and writes `docs/data/literature_results.json`.
- `evaluation` writes `docs/data/evaluation.json`.
- `prompts` writes `docs/data/prompts.json`.
- `news` writes `docs/data/news.json`.
- `meta` writes `docs/data/meta.json`.
- `paper` copies `paper/paper.pdf` to `docs/paper.pdf`.
- `audio` is a legacy local-development target for `docs/audio/`; the published
  site normally uses hosted Hugging Face audio.

Inputs:

- `data/benchmarks/<benchmark>/<benchmark>_normalized.csv` or
  `_normalized_selected.csv` — source question metadata.
- `results/<exp_nr_name>/<benchmark>/<model>/<date>/…` — one immutable run;
  experiment 0 keeps MCQ and PIAC-judged OEQ outputs in `mcq/` and `oeq/`
- `AMI_AUDIO_BASE_URL` — hosted audio root, currently
  `https://huggingface.co/datasets/milan477/toward-ami/resolve/main`.
  Hosted paths are derived from each benchmark's normalized `audio_url`, so
  local `data/audio/` is not required for website audio links.

Output is the fully static `docs/` folder: hand-authored `index.html`,
`styles.css`, `app.js`, and targeted generated `data/*.json`.

## Publish on GitHub Pages

1. Rebuild the changed target, for example:
   `AMI_AUDIO_BASE_URL=https://huggingface.co/datasets/milan477/toward-ami/resolve/main python renderers/site/build_site.py --target questions --no-audio`
2. Commit the changed files under `docs/`.
3. Repo **Settings → Pages → Build and deployment → Deploy from a branch**.
4. Branch **`main`**, folder **`/docs`**. Save.

The site is entirely client-side (no build step on GitHub's side; `.nojekyll`
disables Jekyll processing).

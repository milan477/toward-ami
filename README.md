# Welcome to the official repository toward Artificial Musical Intelligence

This repository is designed to be a continuously-updated resource for training Audio-Language models or multimodal models that listen to audio and to let researchers collectively and organically define what Artificial Musical Intelligence should look like. Feel free to fork the repository to add benchmarks, models, or scores. 

## Interactive Benchmark Explorer

![Benchmark statistics dashboard](data/screenshots/screenshot_statistics.png)

The website includes an inspectable benchmark view for browsing the questions
behind each dataset. Researchers can filter a benchmark by modality, category,
skill, and PIAC label, then immediately see the filtered question count, average
audio duration, and average number of distractors. The same view summarizes the
filtered subset with compact visual diagnostics: a sound-duration histogram and
pie charts for distractors, modality, category, skill, and PIAC distribution.
Long category legends stay compact with a `show all` control.

Benchmark audio is hosted once on Hugging Face under
`milan477/toward-ami`. The committed website data stores only question metadata
and hosted audio URLs, so the cards play those clips directly without keeping
the multi-gigabyte audio corpus in git or under `docs/`. Local `data/audio/`
files are just a generated cache for downloading, rebuilding duration stats, or
running experiments.

Screenshots of these website states live in `data/screenshots/` as visual
references for the site functionality.

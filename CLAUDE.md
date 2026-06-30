# ami-eval

Meta-study: characterizing ALM music benchmarks, identifying gaps, and proposing better evaluation methods.

## Layout

```
download/
  run.py                   # dispatcher: python download/run.py <name>|all|--list
  common.py                # shared normalize helpers + canonical schema
  <name>.py                # one specialized download_<name>() per dataset
analysis/
  taxonomy.py              # characterize benchmarks → tables + figures
  overlap.py               # benchmark overlap analysis
  timeline.py              # usage frequency + score evolution over time
  gaps.py                  # gap/coverage analysis
experiments/
  run.py                   # single entry point (mirrors PitchBench)
  scripts/
    exp_1_llm_baseline.py  # text-only LLM scores on existing benchmarks
    exp_2_perturbation.py  # parameterized perturbations of existing questions
  helpers/
    api.py                 # model query helpers
    results.py             # save/load results with metadata
  results/                 # committed, timestamped, never overwritten
paper/
  figures/                 # generated plots (committed)
data/
  raw/<name>.csv           # source dataset stored exactly as is (generated)
  normalized/<name>.csv    # canonical schema, shared across datasets (generated)
  scores/                  # scraped model scores (generated, not committed)
```

## Downloading datasets

Each dataset has a specialized `download_<name>()` in `download/<name>.py`, registered
in `download/run.py`. It writes two CSVs: `data/raw/<name>.csv` (source, exactly as is)
and `data/normalized/<name>.csv` (canonical schema). The normalized schema is defined in
`download/common.py`:

```
benchmark, question, question_type, correct_answer, distractors,
audio_url, category_1, category_2, category_3  (+ extras appended if needed)
```

`distractors` is a JSON list of the wrong options with whitespace collapsed, e.g.
`["distractor 1","distractor 2"]`.

```bash
python download/run.py mmar        # one dataset
python download/run.py all         # every registered dataset
python download/run.py --list      # show registered datasets
```

## Browsing questions + audio

A dependency-free web UI (Python stdlib `http.server`) to page through questions
and play their recordings:

```bash
python frontend/server.py                       # open http://localhost:8000
python frontend/server.py --data-dir data/cleaned --port 9000
```

It reads `data/normalized/*.csv` and serves clips from `data/audio/<dataset>/`,
matching each question's `audio_url` to whatever is on disk (so questions whose
audio hasn't been downloaded just show without a player). Supports dataset/
category/type filters, search, an "has audio" toggle, and audio seeking.

## Running analysis

```bash
python analysis/taxonomy.py        # generate taxonomy figures
python analysis/overlap.py         # overlap matrix
python analysis/timeline.py        # usage/score timelines
python analysis/gaps.py            # gap report
```

## Running experiments

```bash
python experiments/run.py exp_1_llm_baseline
python experiments/run.py exp_2_perturbation
python experiments/run.py --list
```

## Rules

- `data/normalized/<name>.csv` is the source of truth for analysis — never hardcoded dicts.
- Each dataset gets its own specialized download function; conversions are per-dataset since source formats differ.
- Every result file includes: model info, git commit, all prompts, all config values.
- `experiments/results/` is never overwritten — each run gets a timestamped directory.
- Figures saved to `paper/figures/` are the ones that go in the paper — regenerated deterministically.
- `data/` is gitignored (generated); `experiments/results/` and `paper/figures/` are committed.
- don't remove debugging statements

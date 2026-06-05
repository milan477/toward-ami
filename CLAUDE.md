# ami-eval

Meta-study: characterizing ALM music benchmarks, identifying gaps, and proposing better evaluation methods.

## Layout

```
catalog/
  schema.yaml              # field definitions for benchmark entries
  benchmarks/*.yaml        # one file per benchmark/dataset
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
  scores/                  # scraped model scores (generated, not committed)
```

## Catalog format

Each benchmark is a YAML file in `catalog/benchmarks/`. See `catalog/schema.yaml` for all fields.

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

- Catalog entries are source of truth — all analysis reads from YAML, never from hardcoded dicts.
- Every result file includes: model info, git commit, all prompts, all config values.
- `experiments/results/` is never overwritten — each run gets a timestamped directory.
- Figures saved to `paper/figures/` are the ones that go in the paper — regenerated deterministically.
- `data/` is gitignored (generated); `experiments/results/` and `paper/figures/` are committed.

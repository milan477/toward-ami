# ami-eval

Meta-study: characterizing ALM music benchmarks, identifying gaps, and proposing better evaluation methods.

## Layout

```
download/
  run.py                   # dispatcher: python download/run.py <name>|all|--list
  common.py                # shared normalize helpers + canonical schema + bench_path()
  clean.py                 # normalized → cleaned (music subset)
  audio.py                 # fetch the audio clips the cleaned rows reference
  benchmark_<name>.py      # one specialized download_<name>() per dataset
models/                    # everything model-related
  client.py                # make_client() + client classes (flamingo/openai/openrouter/local)
  api.py                   # low-level model query helpers
  flamingo_server.py       # FastAPI server for Audio Flamingo Next
  dummy.py                 # dummy baseline model
src/                       # experiment + analysis code
  run.py                   # experiment entry point (scripts/exp_*.py)
  helpers/
    results.py             # save/load results with metadata (→ repo-root results/)
    judge.py               # general 0–4 LLM-as-judge
  piac/                    # the PIAC pipeline (current direction)
    pipeline.py            # orchestrator: cleaned CSV → probe-ready "ready" CSV
    annotate.py            # local-Qwen PIAC category + answer_format annotation
    classify.py taxonomy.py decompose.py prompts.py judge.py
    run_model.py run_oeq.py run_probes.py analyze.py
  scripts/
    exp_1_llm_baseline.py  # text-only LLM scores on existing benchmarks
    exp_2_perturbation.py  # parameterized perturbations of existing questions
    run_mmar_af_next*.py   # Audio Flamingo Next runners (MCQ / OEQ)
  analysis/
    taxonomy.py overlap.py timeline.py gaps.py catalog.py …  # characterize benchmarks
renderers/                 # frontend renderers, one folder each
  server/                  # server.py + index.html — browse questions + audio
  oeq_report/              # static OEQ results viewer
  skill_space/             # skill_space.html
  site/                    # build_site.py — populates docs/
docs/                      # the deployed website (toward-ami.com)
paper/
  figures/                 # generated plots (committed)
data/                      # generated, gitignored
  audio/<name>/            # downloaded clips
  benchmarks/<name>/       # <name>_{raw,normalized,cleaned,ready}.csv
results/                   # committed, timestamped, never overwritten
```

## Downloading datasets

Each dataset has a specialized `download_<name>()` in `download/benchmark_<name>.py`,
registered in `download/run.py`. It writes two CSVs into `data/benchmarks/<name>/`:
`<name>_raw.csv` (source, exactly as is) and `<name>_normalized.csv` (canonical
schema). Stage paths come from `bench_path(name, stage)` in `download/common.py`;
the normalized schema is defined there too:

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
python download/clean.py mmar      # normalized → cleaned (music subset)
python download/audio.py mmar      # fetch the referenced audio
```

## Browsing questions + audio

A dependency-free web UI (Python stdlib `http.server`) to page through questions
and play their recordings:

```bash
python renderers/server/server.py                    # open http://localhost:8000
python renderers/server/server.py --data-dir data/af_next --port 9000
```

It searches `--data-dir` recursively (default `data/benchmarks`) and serves clips
from `data/audio/<dataset>/`, keying each CSV by its filename stem (e.g.
`mmar_normalized`, `mmar_ready`). Audio is matched to each question's `audio_url`
by whatever is on disk (so questions whose audio hasn't been downloaded just show
without a player). Supports dataset/category/type filters, search, an "has audio"
toggle, and audio seeking.

When a dataset carries `qid` + `category` columns (e.g. the Qwen-annotated
`data/benchmarks/<name>/<name>_ready.csv`, see below), each card also shows the
assigned content category and an inline editor — a category dropdown
(perceptual/inferential/affective/contextual) and an answer-format field — that
writes edits straight back to the CSV via `POST /api/update`.

A model run can also be browsed this way: `run_mmar_af_next.py` writes a
frontend-viewable CSV (`data/af_next/<input>.csv` = full schema + `category` +
`af_pred_answer`/`af_correct`/`af_response`), so each card shows the model's
answer with a ✓/✗ next to the audio and category:

```bash
python src/scripts/run_mmar_af_next.py --data data/benchmarks/mmar/mmar_ready.csv --modality music
python renderers/server/server.py --data-dir data/af_next     # browse AF-Next predictions
```

## The PIAC pipeline

`src/piac/pipeline.py` is the orchestrator. Given a dataset name it resolves
`data/benchmarks/<name>/<name>_cleaned.csv`, ensures every music-subset question
is PIAC-annotated (reusing `src/piac/annotate.py`), adds skill labels + eval
strategy, and writes `data/benchmarks/<name>/<name>_ready.csv` — ready to probe.

```bash
python -m src.piac.pipeline mmar          # full music subset
python -m src.piac.pipeline mmar --limit 20   # POC: classify 20 new rows
```

`src/piac/annotate.py` uses a local Qwen model (no API key) to prepopulate, per
question, an `answer_format` (what a correct open-ended answer looks like) and a
content `category` — **perceptual** (measurable from the signal), **inferential**
(trained analysis of the signal), **affective** (the listener's subjective
experience), **contextual** (factual world knowledge beyond the signal); re-runs
preserve manual edits. Review/correct the labels in the frontend (above).

```bash
python -m src.piac.annotate                 # cleaned mmar, local Qwen
python -m src.piac.annotate --overwrite     # re-annotate all rows
```

The general 0–4 LLM-as-judge lives at `src/helpers/judge.py` (also local-Qwen by
default); any `make_client` spec works as the judge/annotator backend
(`local:...`, `openai:...`, `openrouter:...`).

## Running analysis

```bash
python src/analysis/taxonomy.py    # generate taxonomy figures
python src/analysis/overlap.py     # overlap matrix
python src/analysis/timeline.py    # usage/score timelines
python src/analysis/gaps.py        # gap report
```

## Running experiments

```bash
python src/run.py exp_1_llm_baseline
python src/run.py exp_2_perturbation
python src/run.py --list
```

## Building the website

```bash
python renderers/site/build_site.py    # regenerate docs/ from data + results
```

## Rules

- `data/benchmarks/<name>/<name>_normalized.csv` is the source of truth for analysis — never hardcoded dicts.
- Each dataset gets its own specialized download function; conversions are per-dataset since source formats differ.
- Every result file includes: model info, git commit, all prompts, all config values.
- `results/` is never overwritten — each run gets a timestamped directory.
- Figures saved to `paper/figures/` are the ones that go in the paper — regenerated deterministically.
- `data/` is gitignored (generated); `results/` and `paper/figures/` are committed.
- don't remove debugging statements

"""
Exp 2: Perturbation experiment.
Take questions from an existing benchmark and vary one acoustic parameter
at a time (instrument, duration, effects, transposition) to measure
how much model performance drifts from the baseline.

Structure:
  baseline condition  →  matched perturbed condition
  score(baseline) - score(perturbed) = performance drift

Perturbation axes (extend as needed):
  - instrument:    render the same musical content on a different instrument
  - duration:      truncate or pad the audio clip
  - transposition: shift pitch by N semitones
  - reverb:        add room reverb
  - noise:         add white noise at varying SNR
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "helpers"))    # src/helpers → results
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "models"))  # models → api

from api import get_model_info, query_model
from results import get_run_metadata, save_results

CONFIG = {
    "benchmark": "FILL_ME",      # which benchmark to perturb
    "perturbation": "duration",  # instrument | duration | transposition | reverb | noise
    "n_items": 20,
    "param_values": [4, 8, 15, 30],  # e.g. durations in seconds
    "prompt_template": "What is the {skill} of this audio? Answer concisely.",
}


def preview() -> None:
    print(f"Perturbation: {CONFIG['perturbation']}")
    print(f"Benchmark:    {CONFIG['benchmark']}")
    print(f"Param values: {CONFIG['param_values']}")
    print(f"N items:      {CONFIG['n_items']}")


def run() -> None:
    model_info = get_model_info()
    metadata = get_run_metadata("exp_2_perturbation", model_info["model_id"], CONFIG)

    # TODO: implement once a target benchmark + perturbation pipeline is chosen.
    # Steps:
    #   1. Load n_items questions from CONFIG["benchmark"]
    #   2. For each item × param_value, generate/load the perturbed audio
    #   3. Query model, record response + correctness
    #   4. Compute drift = baseline_acc - perturbed_acc per param_value
    raise NotImplementedError(
        "Implement after selecting a target benchmark and perturbation pipeline."
    )

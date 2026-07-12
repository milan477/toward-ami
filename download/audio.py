"""Audio downloader registry for benchmark datasets."""

import importlib


DATASETS = {
    "mmar": ("benchmark_mmar", "download_mmar_audio"),
    "mmau": ("benchmark_mmau", "download_mmau_audio"),
    "mmau_pro": ("benchmark_mmau_pro", "download_mmau_pro_audio"),
    "muchomusic": ("benchmark_muchomusic", "download_muchomusic_audio"),
    "hummusqa": ("benchmark_hummusqa", "download_hummusqa_audio"),
    "pitchbench": ("benchmark_pitchbench", "download_pitchbench_audio"),
}


def download_audio(name: str):
    if name == "all":
        for dataset in DATASETS:
            download_audio(dataset)
        return None
    module_name, fn_name = DATASETS[name]
    return getattr(importlib.import_module(module_name), fn_name)()

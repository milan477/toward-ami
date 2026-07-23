import json
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from download.benchmark_pitchbench import _subset_skill
from renderers.site.build_site import (
    _audio_stems,
    _site_category_values,
    _stage_path,
    hosted_audio_urls,
)


class SiteQuestionSchemaTests(unittest.TestCase):
    def test_site_falls_back_when_selected_stage_is_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            dataset = Path(temp) / "demo"
            dataset.mkdir()
            columns = ["qid", "question"]
            for suffix, rows in (
                ("normalized_selected", []),
                ("normalized", [{"qid": "demo_q_1", "question": "Question"}]),
            ):
                path = dataset / f"demo_{suffix}.csv"
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)

            self.assertEqual(_stage_path(dataset), dataset / "demo_normalized.csv")

    def test_pitchbench_subset_becomes_a_skill_label(self):
        self.assertEqual(
            _subset_skill("pitchbench_a1_single_pitch_id"),
            "Single pitch id",
        )

    def test_named_categories_and_modalities_stay_separate(self):
        row = {
            "focus": '["music"]',
            "input_modality": '["audio", "text"]',
            "output_modality": "text",
            "category_1_main_category": "Historical context",
            "category_2_secondary_categories": json.dumps([
                "Historical and Cultural Context",
                "Instrumentation",
                "Metre and Rhythm",
            ]),
        }

        self.assertEqual(
            _site_category_values("hummusqa", row),
            {
                "focus": ["music"],
                "input_modality": ["audio", "text"],
                "output_modality": ["text"],
                "category_1_main_category": ["Historical context"],
                "category_2_secondary_categories": [
                    "Historical and Cultural Context",
                    "Instrumentation",
                    "Metre and Rhythm",
                ],
            },
        )

    def test_all_json_audio_references_get_hosted_urls(self):
        raw = '["./audio/one.wav", "./audio/subset/two.mp3"]'

        self.assertEqual(_audio_stems(raw), ["one", "two"])
        with patch(
            "renderers.site.build_site.HOSTED_AUDIO_BASE_URL",
            "https://example.test/audio",
        ):
            self.assertEqual(
                hosted_audio_urls("demo", raw),
                [
                    "https://example.test/audio/demo/one.wav",
                    "https://example.test/audio/demo/subset/two.mp3",
                ],
            )


if __name__ == "__main__":
    unittest.main()

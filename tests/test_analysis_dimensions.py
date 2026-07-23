from __future__ import annotations

import json
import csv
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import download.common as download_common
from download.benchmark_hummusqa import _normalize_row as normalize_hummusqa_row
from download.benchmark_mmar import _normalize_row as normalize_mmar_row
from download.benchmark_mmau_pro import _normalize_row as normalize_mmau_pro_row
from download.benchmark_muchomusic import _normalize_row as normalize_muchomusic_row
from download.common import NORMALIZED_COLUMNS, focus_values
from src.analysis.annotators import QuestionDimensionsAnnotator
from src.analysis.annotate import _analysis_complete, enhance
from src.config import ANALYSIS_COLS
from src.analysis.dimensions import creator_context
from src.analysis.transcribe import AudioTranscriber, should_transcribe


class DimensionNormalizationTests(unittest.TestCase):
    def test_focus_values_split_mixed_source_labels(self):
        self.assertEqual(
            focus_values("mix-sound-music-speech"),
            ["music", "speech", "sound"],
        )

    def test_mmar_has_only_core_and_named_creator_categories(self):
        row = normalize_mmar_row({
            "question": "Which instrument is playing?",
            "choices": ["violin", "piano"],
            "answer": "violin",
            "audio_path": "clip.wav",
            "modality": "mix-music-speech",
            "category": "Perception Layer",
            "sub-category": "Music Theory",
            "language": "English",
            "source": "AudioSet",
        })
        self.assertEqual(json.loads(row["focus"]), ["music", "speech"])
        self.assertEqual(json.loads(row["answer"]), ["violin"])
        self.assertEqual(json.loads(row["distractors"]), ["piano"])
        self.assertEqual(json.loads(row["url"]), ["clip.wav"])
        self.assertEqual(row["category_1_category"], "Perception Layer")
        self.assertEqual(row["category_2_subcategory"], "Music Theory")
        self.assertEqual(
            set(row) - set(NORMALIZED_COLUMNS),
            {
                "category_1_category", "category_2_subcategory",
                "category_3_language", "category_4_source",
            },
        )

    def test_hummusqa_keeps_creator_taxonomy_in_order(self):
        row = normalize_hummusqa_row({
            "Song link": "https://example.test/123",
            "Question": "What is the melodic contour?",
            "True answer": "ascending",
            "Distractor 1": "descending",
            "Distractor 2": "static",
            "Distractor 3": "mixed",
            "Main Category": "Melody",
            "Secondary Categories": "Structure; Performance",
            "Difficulty": "High",
        }, 0)
        self.assertEqual(row["category_1_main_category"], "Melody")
        self.assertEqual(
            json.loads(row["category_2_secondary_categories"]),
            ["Structure", "Performance"],
        )
        self.assertEqual(row["category_3_difficulty"], "High")

    def test_mmau_pro_uses_requested_category_names(self):
        row = normalize_mmau_pro_row({
            "question": "What is heard?", "answer": "music",
            "choices": ["music", "speech"], "audio_path": ["a.wav", "b.wav"],
            "category": "music", "sub-cat": "timbre",
            "perceptual_skills": ["instrument"],
            "reasoning_skills": ["causal reasoning"],
        })
        self.assertEqual(
            json.loads(row["category_1_category"]), ["perceptual", "reasoning"]
        )
        self.assertEqual(
            json.loads(row["category_2_skills"]),
            ["instrument", "causal reasoning"],
        )
        self.assertEqual(row["category_3_subcategory"], "timbre")
        self.assertEqual(json.loads(row["url"]), ["a.wav", "b.wav"])

    def test_muchomusic_merges_knowledge_and_reasoning_skills(self):
        row = normalize_muchomusic_row({
            "question": "What is heard?",
            "correct_answer": "riff",
            "distractor_1_answer": "scale",
            "distractor_2_answer": "chord",
            "distractor_3_answer": "silence",
            "dataset": "sdd",
            "dataset_identifier": "1",
            "genre": "rock",
            "music_knowledge": "['melody', 'harmony']",
            "music_reasoning": "['comparison', 'harmony']",
        })
        self.assertEqual(
            json.loads(row["category_1_category"]), ["knowledge", "reasoning"]
        )
        self.assertEqual(
            json.loads(row["category_2_skills"]),
            ["melody", "harmony", "comparison"],
        )
        self.assertEqual(row["category_3_genre"], "rock")

    def test_every_rulebook_covers_each_core_and_category_column(self):
        project = Path(__file__).parents[1]
        root = project / "download" / "rulebooks"
        for name in (
            "aha", "hummusqa", "mmar", "mmau", "mmau_pro", "muchomusic",
            "parsa_bench", "pitchbench",
        ):
            rulebook = root / f"{name}.md"
            self.assertTrue(rulebook.exists(), name)
            if name == "parsa_bench":
                expected = [
                    *NORMALIZED_COLUMNS,
                    "category_1_task",
                    "category_2_task_file",
                ]
            else:
                normalized = (
                    project / "data" / "benchmarks" / name / f"{name}_normalized.csv"
                )
                with normalized.open(newline="", encoding="utf-8-sig") as handle:
                    expected = next(csv.reader(handle))
            documented = re.findall(
                r"^\| `([^`]+)` \|",
                rulebook.read_text(encoding="utf-8"),
                flags=re.MULTILINE,
            )
            self.assertEqual(documented, expected, name)


class EnhancementTests(unittest.TestCase):
    def test_enhance_backfills_task_rewrite_without_reannotating(self):
        class FakeClient:
            model_id = "fake"
            supports_audio = False

            def generate(self, prompt, max_tokens=256):
                if '"imperative"' in prompt:
                    return json.dumps({
                        "equivalent": True,
                        "imperative": True,
                        "answer_preserved": True,
                        "rationale": "The pitch-identification task is unchanged.",
                    })
                return json.dumps({
                    "rewritten_question": "Identify the pitch being played."
                })

            def info(self):
                return {"name": "fake", "model_id": self.model_id}

        class CompleteAnnotator:
            client = FakeClient()
            name = "fake_dimensions"
            max_tokens = 100
            output_columns = tuple(ANALYSIS_COLS)

            def annotate(self, _row):
                raise AssertionError("completed dimensions must not be re-annotated")

        with tempfile.TemporaryDirectory() as temp:
            old_bench_dir = download_common.BENCH_DIR
            download_common.BENCH_DIR = Path(temp)
            try:
                dataset_dir = Path(temp) / "tiny"
                dataset_dir.mkdir()
                source = {
                    "qid": "tiny_q_1", "bench": "tiny", "focus": '["music"]',
                    "question": "What pitch is played?", "answer": '["A4"]',
                    "distractors": "[]", "url": '["a.wav"]',
                    "input_modality": '["audio", "text"]',
                    "output_modality": "text",
                }
                with (dataset_dir / "tiny_normalized_selected.csv").open(
                    "w", newline="", encoding="utf-8"
                ) as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(source))
                    writer.writeheader()
                    writer.writerow(source)
                prior = {
                    **source,
                    "question_oeq": "What pitch is played?",
                    "answer_oeq": '["A4"]',
                    "transcription": "",
                    "action_content": '[["identify", "pitch"]]',
                    "piec": "perceptual",
                    "question_nature": "specific_label",
                    "answer_format": "a pitch name",
                    "example_incorrect_answer": "B4",
                }
                with (dataset_dir / "tiny_normalized_selected_enhanced.csv").open(
                    "w", newline="", encoding="utf-8"
                ) as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(prior))
                    writer.writeheader()
                    writer.writerow(prior)

                with patch(
                    "src.analysis.annotate.build_annotators",
                    return_value=[CompleteAnnotator()],
                ):
                    output = enhance("tiny", judge_spec="fake")
                with output.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    row = next(reader)
                self.assertEqual(row["question_task"], "Identify the pitch being played.")
                self.assertNotIn("task_rewrite_equivalent", reader.fieldnames)
                self.assertNotIn("task_rewrite_imperative", reader.fieldnames)
            finally:
                download_common.BENCH_DIR = old_bench_dir

    def test_combined_llm_response_produces_all_enhanced_dimensions(self):
        response = json.dumps({
            "action_content": [
                ["Quantify/Measure", "Microtiming"],
                {"content": "Orchestration Density", "action": "Compare/Relate"},
            ],
            "piec": "experiential",
            "question_nature": "specific label",
            "answer_format": "a note in scientific pitch notation",
            "example_incorrect_answer": "B4",
        })
        parsed = QuestionDimensionsAnnotator(client=None).parse(response)
        self.assertEqual(
            json.loads(parsed["action_content"]),
            [
                ["quantify/measure", "microtiming"],
                ["compare/relate", "orchestration density"],
            ],
        )
        self.assertEqual(parsed["piec"], "experiential")
        self.assertEqual(parsed["question_nature"], "specific_label")
        self.assertEqual(
            parsed["answer_format"], "a note in scientific pitch notation"
        )
        self.assertEqual(parsed["example_incorrect_answer"], "B4")

    def test_prompt_distinguishes_listener_experience_from_inference(self):
        prompt = QuestionDimensionsAnnotator(client=None).prompt({
            "question": "Where does the tension feel strongest to you?",
            "answer": '["measure 8"]',
            "distractors": "[]",
        })
        self.assertIn("consensus is neither required nor desired", prompt)
        self.assertIn("composer's inspiration", prompt)
        self.assertIn("general agreement is desired", prompt)
        self.assertIn("harmony, pitch, mood, genre, expression, instrument", prompt)
        self.assertIn("not restricted to a vocabulary", prompt)
        self.assertIn('[["understand", "speech"]]', prompt)
        self.assertIn('["infer", "intent"]', prompt)
        self.assertIn('["count", "sounds"]', prompt)
        self.assertIn("not the concrete object, event, answer, or scenario", prompt)
        self.assertIn('["segment", "parts"]', prompt)
        self.assertIn('["count", "fragments"]', prompt)
        self.assertIn('["compare", "timbre"]', prompt)
        self.assertIn('["infer", "quality"]', prompt)
        self.assertIn(
            "If the question is answerable from the speech alone, it is inferential",
            prompt,
        )
        self.assertIn("### experiential", prompt)

    def test_prompt_includes_audio_transcription(self):
        prompt = QuestionDimensionsAnnotator(client=None).prompt({
            "question": "What did the speaker request?",
            "answer": '["Please close the door"]',
            "distractors": "[]",
            "transcription": "Please close the door.",
        })
        self.assertIn("Audio speech transcription", prompt)
        self.assertIn("Please close the door.", prompt)

    def test_mmar_transcribes_only_speech_focus(self):
        self.assertTrue(should_transcribe("mmar", {
            "focus": '["music", "speech"]', "url": '["clip.wav"]'
        }))
        self.assertFalse(should_transcribe("mmar", {
            "focus": '["music"]', "url": '["clip.wav"]'
        }))

    def test_audio_transcription_is_cached_with_provenance(self):
        class FakeTranscriptionClient:
            model_id = "fake-stt"
            supports_audio = True

            def __init__(self):
                self.calls = 0

            def generate(self, prompt, audio_path=None, max_tokens=256):
                self.calls += 1
                self.last_audio_path = audio_path
                return "  Please   close the door.  "

        fake = FakeTranscriptionClient()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio_dir = root / "audio"
            (audio_dir / "mmar").mkdir(parents=True)
            (audio_dir / "mmar" / "clip.wav").write_bytes(b"audio")
            old_bench_dir = download_common.BENCH_DIR
            download_common.BENCH_DIR = root / "benchmarks"
            with patch("src.analysis.transcribe.AUDIO_DIR", audio_dir), patch(
                "models.client.make_client", return_value=fake
            ):
                transcriber = AudioTranscriber("mmar", "fake-stt")
                row = {
                    "qid": "mmar_q_1",
                    "focus": '["speech"]',
                    "url": '["clip.wav"]',
                }
                self.assertEqual(
                    transcriber.transcribe(row), "Please close the door."
                )
                self.assertEqual(
                    transcriber.transcribe(row), "Please close the door."
                )
                transcriber.close()
            download_common.BENCH_DIR = old_bench_dir
            self.assertEqual(fake.calls, 1)
            sidecar = (
                root / "benchmarks" / "mmar"
                / ".mmar.normalized_selected.transcriptions.jsonl"
            )
            record = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(record["transcription_model"], "fake-stt")
            self.assertEqual(record["transcription"], "Please close the door.")

    def test_true_false_has_no_incorrect_example(self):
        response = json.dumps({
            "action_content": [["identify", "pitch"]],
            "piec": "perceptual",
            "question_nature": "true_false",
            "answer_format": "true or false",
            "example_incorrect_answer": "False",
        })
        parsed = QuestionDimensionsAnnotator(client=None).parse(response)
        self.assertEqual(parsed["example_incorrect_answer"], "")
        self.assertTrue(_analysis_complete(parsed))

    def test_ordinal_value_remains_distinct(self):
        response = json.dumps({
            "action_content": [["count", "sounds"]],
            "piec": "perceptual",
            "question_nature": "ordinal_value",
            "answer_format": "an integer",
            "example_incorrect_answer": "4",
        })
        parsed = QuestionDimensionsAnnotator(client=None).parse(response)
        self.assertEqual(parsed["question_nature"], "ordinal_value")

    def test_emotional_is_not_a_piec_category(self):
        parsed = QuestionDimensionsAnnotator(client=None).parse(json.dumps({
            "action_content": [["identify", "mood"]],
            "piec": "emotional",
            "question_nature": "specific_label",
            "answer_format": "a mood label",
            "example_incorrect_answer": "joyful",
        }))
        self.assertEqual(parsed["piec"], "")

    def test_correct_example_is_replaced_by_creator_distractor(self):
        class FakeClient:
            model_id = "fake"
            supports_audio = False

            def generate(self, prompt, max_tokens=256):
                return json.dumps({
                    "action_content": [["identify", "pitch"]],
                    "piec": "perceptual",
                    "question_nature": "specific_label",
                    "answer_format": "a note in scientific pitch notation",
                    "example_incorrect_answer": "A4",
                })

        result = QuestionDimensionsAnnotator(FakeClient()).annotate({
            "question": "What note is played?",
            "answer": '["A4"]',
            "distractors": '["B4"]',
        })
        self.assertEqual(result["example_incorrect_answer"], "B4")

    def test_creator_context_includes_only_named_category_columns(self):
        context = creator_context({
            "category_1_category": "Pitch Identification",
            "answer": '["A4"]',
            "focus": '["music"]',
        })
        self.assertIn("Pitch Identification", context)
        self.assertNotIn("answer", context)
        self.assertNotIn("focus", context)

    def test_enhance_adds_exact_standardized_columns_and_preserves_source(self):
        class FakeClient:
            model_id = "fake"
            supports_audio = False

            def generate(self, prompt, max_tokens=256):
                if "rewritten_question" in prompt:
                    return json.dumps({
                        "rewritten_question": "Identify the pitch being played."
                    })
                if '"imperative"' in prompt:
                    return json.dumps({
                        "equivalent": True,
                        "imperative": True,
                        "answer_preserved": True,
                        "rationale": "The requested pitch is unchanged.",
                    })
                return json.dumps({
                    "question_oeq": "What pitch is played?",
                    "answer_oeq": ["A4"],
                })

            def info(self):
                return {"name": "fake", "model_id": self.model_id}

        class FakeAnnotator:
            client = FakeClient()
            name = "fake_dimensions"
            max_tokens = 100
            output_columns = tuple(ANALYSIS_COLS)

            def annotate(self, row):
                return {
                    "action_content": '[["identify", "pitch"]]',
                    "piec": "perceptual",
                    "question_nature": "specific_label",
                    "answer_format": "a note in scientific pitch notation",
                    "example_incorrect_answer": "B4",
                    "enhancement_prompt": "fake prompt",
                    "enhancement_raw_response": "fake response",
                }

        with tempfile.TemporaryDirectory() as temp:
            old_bench_dir = download_common.BENCH_DIR
            download_common.BENCH_DIR = Path(temp)
            try:
                dataset_dir = Path(temp) / "tiny"
                dataset_dir.mkdir()
                normalized_row = {
                    "qid": "tiny_q_1", "bench": "tiny", "focus": '["music"]',
                    "question": "What pitch is played?", "answer": '["A4"]',
                    "distractors": "[]", "url": '["a.wav"]',
                    "input_modality": '["audio", "text"]',
                    "output_modality": "text",
                    "category_1_category": "Pitch Identification",
                }
                with (dataset_dir / "tiny_normalized_selected.csv").open(
                    "w", newline="", encoding="utf-8"
                ) as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(normalized_row))
                    writer.writeheader()
                    writer.writerow(normalized_row)
                cache = dataset_dir / ".tiny.normalized_selected.enhancement.jsonl"
                cache.write_text(json.dumps({
                    "qid": "tiny_q_1",
                    "piec": "experiential",
                    "question_nature": "open_ended",
                }) + "\n")
                with patch(
                    "src.analysis.annotate.build_annotators",
                    return_value=[FakeAnnotator()],
                ), patch(
                    "src.analysis.annotate.should_transcribe", return_value=False
                ):
                    output = enhance("tiny", judge_spec="fake")
                with output.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    row = next(reader)
                    columns = reader.fieldnames
                self.assertEqual(
                    output.name, "tiny_normalized_selected_enhanced.csv"
                )
                self.assertEqual(
                    columns[columns.index("question") + 1], "question_oeq"
                )
                self.assertEqual(
                    columns[columns.index("question_oeq") + 1], "question_task"
                )
                self.assertEqual(columns[columns.index("answer") + 1], "answer_oeq")
                self.assertEqual(row["question_oeq"], "What pitch is played?")
                self.assertEqual(row["question_task"], "Identify the pitch being played.")
                self.assertEqual(row["answer_oeq"], '["A4"]')
                self.assertEqual(row["qid"], "tiny_q_1")
                self.assertEqual(row["category_1_category"], "Pitch Identification")
                self.assertEqual(row["action_content"], '[["identify", "pitch"]]')
                self.assertEqual(row["piec"], "perceptual")
                self.assertEqual(
                    row["answer_format"], "a note in scientific pitch notation"
                )
                self.assertEqual(row["example_incorrect_answer"], "B4")
                self.assertEqual(columns[-6:], ["transcription", *ANALYSIS_COLS])
                self.assertEqual(row["transcription"], "")
                self.assertNotIn("enhancement_model", row)

                cached = json.loads(cache.read_text().splitlines()[-1])
                self.assertEqual(cached["enhancement_model"], "fake")
                self.assertEqual(cached["enhancement_prompt"], "fake prompt")
                self.assertEqual(cached["piec"], "perceptual")
            finally:
                download_common.BENCH_DIR = old_bench_dir


if __name__ == "__main__":
    unittest.main()

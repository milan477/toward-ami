import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from src.experiments.variants import (
    build_variant_item,
    extract_option_text,
    get_variant,
    required_columns,
)
from src.analysis.task_rewrite import TASK_QUESTION_COLUMN, TaskQuestionRewriter


ROW = {
    "qid": "demo_q_1",
    "question": "Which instrument is playing?",
    "question_oeq": "What instrument can be heard in the recording?",
    "answer": '["Violin"]',
    "answer_oeq": '["A violin can be heard."]',
    "distractors": '["Piano", "Flute"]',
    "piec": "perceptual",
    "question_nature": "specific_label",
    "answer_format": "an instrument name",
}


class ExperimentVariantTests(unittest.TestCase):
    def test_experiment_six_rejects_rewrite_that_changes_desired_answer(self):
        class RetryClient:
            model_id = "fake-rewriter"

            def __init__(self):
                self.responses = iter([
                    '{"rewritten_question":"Identify whether the singing is indoors."}',
                    '{"equivalent":true,"imperative":true,"answer_preserved":false,"rationale":"The outdoors alternative was removed, changing the desired answer space."}',
                    '{"rewritten_question":"Choose whether the singing location is indoors or outdoors."}',
                    '{"equivalent":true,"imperative":true,"answer_preserved":true,"rationale":"The same binary answer is requested."}',
                ])

            def generate(self, prompt, audio_path=None, max_tokens=256):
                return next(self.responses)

            def info(self):
                return {"name": "fake", "model_id": self.model_id}

        with tempfile.TemporaryDirectory() as temporary:
            rewriter = TaskQuestionRewriter(
                "demo",
                "fake",
                client=RetryClient(),
                cache_path=Path(temporary) / "rewrites.jsonl",
            )
            result = rewriter.rewrite({
                **ROW,
                "question": "Is the singing location indoors or outdoors?",
                "answer": '["Outdoors"]',
                "distractors": '["Indoors"]',
            })
            rewriter.close()

        self.assertEqual(
            result[TASK_QUESTION_COLUMN],
            "Choose whether the singing location is indoors or outdoors.",
        )

    def test_experiment_six_rejects_non_equivalent_rewrite(self):
        class RetryClient:
            model_id = "fake-rewriter"

            def __init__(self):
                self.prompts = []
                self.responses = iter([
                    '{"rewritten_question":"Identify the singer."}',
                    '{"equivalent":false,"imperative":true,"answer_preserved":false,"rationale":"The requested location was removed."}',
                    '{"rewritten_question":"Choose between indoors or outdoors for the singing location."}',
                    '{"equivalent":true,"imperative":true,"answer_preserved":true,"rationale":"The location alternatives are preserved."}',
                ])

            def generate(self, prompt, audio_path=None, max_tokens=256):
                self.prompts.append(prompt)
                return next(self.responses)

            def info(self):
                return {"name": "fake", "model_id": self.model_id}

        row = {
            **ROW,
            "question": "Is the singing location indoors or outdoors?",
        }
        client = RetryClient()
        with tempfile.TemporaryDirectory() as temporary:
            rewriter = TaskQuestionRewriter(
                "demo", "fake", client=client,
                cache_path=Path(temporary) / "rewrites.jsonl",
            )
            result = rewriter.rewrite(row)
            rewriter.close()

        self.assertEqual(len(client.prompts), 4)
        self.assertIn("requested location was removed", client.prompts[2])
        self.assertEqual(
            result[TASK_QUESTION_COLUMN],
            "Choose between indoors or outdoors for the singing location.",
        )

    def test_experiment_six_rewrites_to_verified_imperative_task(self):
        class RewriteClient:
            model_id = "fake-rewriter"

            def __init__(self):
                self.calls = []
                self.responses = [
                    json.dumps({
                        "rewritten_question": (
                            "Choose between indoors or outdoors to describe the "
                            "location of the woman singing."
                        )
                    }),
                    json.dumps({
                        "equivalent": True,
                        "imperative": True,
                        "answer_preserved": True,
                        "rationale": "The task and alternatives are unchanged.",
                    }),
                ]

            def generate(self, prompt, audio_path=None, max_tokens=256):
                self.calls.append((prompt, audio_path, max_tokens))
                return self.responses.pop(0)

            def info(self):
                return {"name": "fake", "model_id": self.model_id}

        row = {
            **ROW,
            "question": (
                "In the video, the woman is singing. Is the location indoors or outdoors?"
            ),
        }
        client = RewriteClient()
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = Path(temporary) / "rewrites.jsonl"
            rewriter = TaskQuestionRewriter(
                "demo",
                "fake",
                client=client,
                cache_path=cache_path,
            )
            rewritten = rewriter.rewrite(row)
            cached = rewriter.rewrite(row)
            self.assertTrue(
                rewriter.has_verified_rewrite(row, rewritten[TASK_QUESTION_COLUMN])
            )
            self.assertFalse(
                rewriter.has_verified_rewrite(
                    {**row, "answer": '["A different answer"]'},
                    rewritten[TASK_QUESTION_COLUMN],
                )
            )
            rewriter.close()
            sidecar = json.loads(cache_path.read_text(encoding="utf-8").splitlines()[-1])

        self.assertEqual(rewritten, cached)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(set(rewritten), {TASK_QUESTION_COLUMN})
        self.assertTrue(sidecar["task_rewrite_equivalent"])
        self.assertTrue(sidecar["task_rewrite_imperative"])
        self.assertTrue(sidecar["task_rewrite_answer_preserved"])
        self.assertEqual(sidecar["task_rewrite_model_spec"], "fake")
        self.assertIn("task_rewrite_attempts", sidecar)
        self.assertEqual(
            rewritten[TASK_QUESTION_COLUMN],
            "Choose between indoors or outdoors to describe the location of the woman singing.",
        )
        variant = get_variant(6)
        item = build_variant_item({**row, **rewritten}, variant)
        self.assertTrue(variant.use_audio)
        self.assertEqual(variant.response_mode, "letter")
        self.assertIn(rewritten[TASK_QUESTION_COLUMN], item["prompt"])
        self.assertNotIn(row["question"], item["prompt"])

    def test_query_runner_routes_audio_and_stt_per_variant(self):
        pandas = types.ModuleType("pandas")
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda *_args, **_kwargs: None

        class Frame:
            def iterrows(self):
                return iter([(
                    0,
                    dict(ROW, url='["clip.wav"]', transcription="spoken evidence"),
                )])

        class Client:
            model_id = "fake-model"

            def __init__(self):
                self.calls = []

            def generate(self, prompt, audio_path=None, max_tokens=256):
                self.calls.append((prompt, audio_path, max_tokens))
                return "A"

        with patch.dict(sys.modules, {"pandas": pandas, "dotenv": dotenv}):
            sys.modules.pop("src.experiments.runner", None)
            from src.experiments.runner import query_variant_answers

            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                audio = root / "clip.wav"
                audio.write_bytes(b"audio")
                for number, expected_audio in ((0, str(audio)), (1, None), (2, None)):
                    client = Client()
                    query_variant_answers(
                        Frame(),
                        {"clip.wav": audio},
                        client,
                        root / f"exp-{number}.jsonl",
                        get_variant(number),
                    )
                    self.assertEqual(client.calls[0][1], expected_audio)
                    if number == 2:
                        self.assertIn("spoken evidence", client.calls[0][0])

    def test_experiment_zero_requests_and_scores_full_option_text(self):
        variant = get_variant(0)
        item = build_variant_item(ROW, variant)
        self.assertTrue(variant.use_audio)
        self.assertEqual(variant.response_mode, "option_text")
        self.assertIn("complete text of the correct option", item["prompt"])
        self.assertEqual(extract_option_text('"Violin."', item["options"]), "Violin")
        self.assertIsNone(extract_option_text(item["correct_letter"], item["options"]))

    def test_experiment_one_removes_audio(self):
        variant = get_variant(1)
        item = build_variant_item(ROW, variant)
        self.assertFalse(variant.use_audio)
        self.assertNotIn("Listen to the audio", item["prompt"])
        self.assertIn("only the written question", item["prompt"])

    def test_experiment_two_uses_stt_but_not_audio(self):
        variant = get_variant(2)
        item = build_variant_item(
            ROW, variant, transcription="The speaker says violin."
        )
        self.assertFalse(variant.use_audio)
        self.assertTrue(variant.use_stt)
        self.assertIn("You do not have access to the audio", item["prompt"])
        self.assertIn(
            "<transcription>The speaker says violin.</transcription>",
            item["prompt"],
        )

    def test_preprocessing_dependencies_define_enhanced_columns(self):
        self.assertFalse(get_variant(0).requires_enhanced)
        self.assertEqual(get_variant(2).dependencies, ("transcription",))
        self.assertIn("transcription", required_columns(get_variant(2)))
        self.assertEqual(get_variant(3).dependencies, ("classification",))
        self.assertIn("answer_format", required_columns(get_variant(3)))
        self.assertEqual(
            get_variant(5).dependencies,
            ("classification", "oeq_rewrite"),
        )
        self.assertIn("question_oeq", required_columns(get_variant(5)))
        self.assertEqual(get_variant(6).dependencies, ("task_rewrite",))
        self.assertIn("question_task", required_columns(get_variant(6)))
        self.assertNotIn("task_rewrite_equivalent", required_columns(get_variant(6)))
        self.assertNotIn("task_rewrite_imperative", required_columns(get_variant(6)))

    def test_experiment_three_removes_options_and_adds_format_and_type(self):
        item = build_variant_item(ROW, get_variant(3))
        self.assertNotIn("Piano", item["prompt"])
        self.assertNotIn("Flute", item["prompt"])
        self.assertIn("Question type: specific_label", item["prompt"])
        self.assertIn("Answer format: an instrument name", item["prompt"])

    def test_experiment_four_is_original_letter_mcq_with_audio(self):
        item = build_variant_item(ROW, get_variant(4))
        self.assertEqual(get_variant(4).response_mode, "letter")
        self.assertIn("only the letter", item["prompt"])
        self.assertIn(ROW["question"], item["prompt"])
        self.assertIn("Piano", item["prompt"])

    def test_experiment_five_uses_piec_rewrite_and_rewritten_answer(self):
        item = build_variant_item(ROW, get_variant(5))
        self.assertEqual(item["question"], ROW["question_oeq"])
        self.assertEqual(item["reference_answer"], "A violin can be heard.")
        self.assertIn("rewritten perceptual question", item["prompt"])
        self.assertNotIn("Piano", item["prompt"])
        self.assertNotIn("Answer format:", item["prompt"])


if __name__ == "__main__":
    unittest.main()

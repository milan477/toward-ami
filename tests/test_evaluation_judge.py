from __future__ import annotations

import unittest

from src.evaluation.judge import build_prompt, parse_judge


class PIECEvaluationTests(unittest.TestCase):
    def test_binary_result_includes_confidence(self):
        parsed = parse_judge(
            '{"score": 1, "confidence": "mid", '
            '"rationale": "Sadness is compatible with melancholic."}'
        )
        self.assertEqual(parsed["score"], 1)
        self.assertEqual(parsed["score_norm"], 1)
        self.assertEqual(parsed["confidence"], "mid")
        self.assertEqual(parsed["verdict"], "correct")

    def test_intermediate_score_is_not_accepted(self):
        parsed = parse_judge(
            '{"score": 3, "confidence": "high", "rationale": "legacy"}'
        )
        self.assertIsNone(parsed["score"])

    def test_inferential_prompt_receives_full_context(self):
        prompt = build_prompt(
            "inferential",
            "Where was this recorded?",
            "Outdoors",
            "In the mountains",
            "a location",
            {
                "original_question": "Is the location indoors or outdoors?",
                "correct_answer": "Outdoors",
                "question_nature": "specific_label",
                "action_content": '[["infer", "recording environment"]]',
                "creator_categories": '{"source": "MMAR"}',
                "distractors": '["Indoors"]',
                "transcription": "Birds and distant traffic are audible.",
            },
        )
        self.assertIn("general consensus is desired", prompt)
        self.assertIn("in the mountains", prompt.lower())
        self.assertIn("Birds and distant traffic", prompt)
        self.assertIn("Is the location indoors or outdoors?", prompt)

    def test_experiential_prompt_documents_compatible_feelings(self):
        prompt = build_prompt(
            "experiential", "How does it feel?", "Melancholic", "Sadness"
        )
        self.assertIn("'melancholic' and answer 'sadness'", prompt)
        self.assertIn("MID confidence", prompt)


if __name__ == "__main__":
    unittest.main()

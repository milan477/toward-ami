import csv
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from src.reporting.openrouter_costs import (
    DETAIL_FIELDS,
    TOTAL_FIELDS,
    record_openrouter_call,
)


def _response(call_id: str, cost: str, prompt_tokens: int, completion_tokens: int) -> dict:
    return {
        "id": call_id,
        "usage": {
            "cost": cost,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }


def _rows(path):
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


class OpenRouterCostsTest(unittest.TestCase):
    def test_openrouter_client_requests_and_records_usage(self):
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda *_args, **_kwargs: None
        requests = types.ModuleType("requests")
        api_response = {
            **_response("gen-client", "0.004", 30, 5),
            "choices": [{"message": {"content": "the response"}}],
        }
        http_response = Mock(status_code=200, text="", json=lambda: api_response)
        requests.post = Mock(return_value=http_response)

        with patch.dict(sys.modules, {"dotenv": dotenv, "requests": requests}):
            sys.modules.pop("models.client", None)
            from models.client import OpenRouterClient

            with (
                patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}),
                patch(
                    "src.reporting.openrouter_costs.record_openrouter_call"
                ) as record_call,
            ):
                result = OpenRouterClient("vendor/model").generate("the prompt")

        self.assertEqual(result, "the response")
        body = requests.post.call_args.kwargs["json"]
        self.assertEqual(body["usage"], {"include": True})
        record_call.assert_called_once_with(api_response, "the prompt", "the response")

    def test_records_daily_details_and_rebuilds_totals(self):
        first = datetime(2026, 7, 20, 23, 59, tzinfo=timezone.utc)
        second = datetime(2026, 7, 21, 8, 15, tzinfo=timezone.utc)
        latest = datetime(2026, 7, 21, 9, 30, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as temporary:
            calls_dir = Path(temporary)
            record_openrouter_call(
                _response("gen-1", "0.00125", 12, 3),
                "first\nprompt",
                "first\r\nresponse",
                called_at=first,
                calls_dir=calls_dir,
            )
            record_openrouter_call(
                _response("gen-2", "0.002", 20, 4),
                "second prompt",
                "second response",
                called_at=second,
                calls_dir=calls_dir,
            )
            record_openrouter_call(
                _response("gen-3", "0.00075", 8, 2),
                "third prompt",
                "third response",
                called_at=latest,
                calls_dir=calls_dir,
            )

            day_one = _rows(calls_dir / "2026-07-20.csv")
            self.assertEqual(list(day_one[0]), DETAIL_FIELDS)
            self.assertEqual(
                day_one[0],
                {
                    "id": "gen-1",
                    "cost": "0.00125",
                    "input length": "12",
                    "output length": "15",
                    "date": "2026-07-20T23:59:00+00:00",
                    "#tokens prompt": "12",
                    "#tokens response": "3",
                    "prompt": "first prompt",
                    "response": "first response",
                },
            )
            self.assertEqual(len(_rows(calls_dir / "2026-07-21.csv")), 2)

            totals = _rows(calls_dir / "total.csv")
            self.assertEqual(list(totals[0]), TOTAL_FIELDS)
            self.assertEqual(
                totals,
                [
                    {
                        "date": "2026-07-20",
                        "cost": "0.00125",
                        "calls": "1",
                        "last call": "2026-07-20T23:59:00+00:00",
                    },
                    {
                        "date": "2026-07-21",
                        "cost": "0.00275",
                        "calls": "2",
                        "last call": "2026-07-21T09:30:00+00:00",
                    },
                    {
                        "date": "TOTAL",
                        "cost": "0.00400",
                        "calls": "3",
                        "last call": "2026-07-21T09:30:00+00:00",
                    },
                ],
            )


if __name__ == "__main__":
    unittest.main()

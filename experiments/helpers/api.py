"""Model query helpers. Mirrors PitchBench interface."""

import os
import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")


def query_model(prompt: str, audio_path: str | None = None) -> str:
    """Send a prompt (optionally with audio) to the model server."""
    if audio_path:
        with open(audio_path, "rb") as f:
            resp = requests.post(
                f"{API_URL}/query",
                data={"prompt": prompt},
                files={"audio": f},
                timeout=60,
            )
    else:
        resp = requests.post(
            f"{API_URL}/query",
            json={"prompt": prompt},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()["response"]


def query_text_only(prompt: str) -> str:
    """Query model with no audio — used for LLM-only baseline."""
    return query_model(prompt, audio_path=None)


def get_model_info() -> dict:
    resp = requests.get(f"{API_URL}/info", timeout=10)
    resp.raise_for_status()
    return resp.json()


def model_slug(info: dict) -> str:
    return info.get("model_id", "unknown").replace("/", "_")

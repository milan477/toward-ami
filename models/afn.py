#!/usr/bin/env python
"""Remote Audio Flamingo Next client (Cloudflare tunnel).

As a library client (via ``make_client("afn")``)::

    from models.client import make_client
    client = make_client("afn")
    text = client.generate("What do you hear?", audio_path="clip.wav")

As a CLI::

    python -m models.afn path/to/audio.wav "What is happening in this audio?"

Env vars: ``AFN_BASE_URL``, ``AFN_API_KEY`` (override the defaults below).
The tunnel URL is ephemeral and changes on every server restart.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_TIMEOUT = 180


def _base_url(url: str | None = None) -> str:
    return (url or os.environ.get("AFN_BASE_URL")).rstrip("/")


def _api_key(key: str | None = None) -> str:
    return key or os.environ.get("AFN_API_KEY")


def generate(
    audio_path: str,
    prompt: str,
    max_new_tokens: int | None = None,
    repetition_penalty: float | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """POST audio + prompt to ``/v1/audio/generate`` and return the reply text."""
    with open(audio_path, "rb") as f:
        resp = requests.post(
            f"{_base_url(base_url)}/v1/audio/generate",
            headers={"Authorization": f"Bearer {_api_key(api_key)}"},
            files={"audio": f},
            data={
                "prompt": prompt,
                **({"max_new_tokens": max_new_tokens} if max_new_tokens else {}),
                **({"repetition_penalty": repetition_penalty} if repetition_penalty else {}),
            },
            timeout=timeout,
        )
    resp.raise_for_status()
    return resp.json()["text"]


class AFNClient:
    """``ModelClient``-compatible wrapper around the remote AFN HTTP API."""

    name = "afn"
    supports_audio = True

    def __init__(self, url: str | None = None, api_key: str | None = None):
        self.url = _base_url(url)
        self.api_key = _api_key(api_key)
        self.model_id = "audio-flamingo-next"

    def info(self) -> dict:
        return {
            "name": self.name,
            "model_id": self.model_id,
            "supports_audio": self.supports_audio,
            "url": self.url,
        }

    def generate(
        self,
        prompt: str,
        audio_path: str | None = None,
        max_tokens: int = 256,
    ) -> str:
        if not audio_path:
            raise ValueError("AFN requires audio; no audio_path given.")
        return generate(
            audio_path,
            prompt,
            max_new_tokens=max_tokens,
            base_url=self.url,
            api_key=self.api_key,
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("audio", help="path to an audio file (wav/mp3/etc.)")
    p.add_argument("prompt", help="text prompt/question about the audio")
    p.add_argument("--max-new-tokens", type=int, default=None)
    p.add_argument("--repetition-penalty", type=float, default=None)
    args = p.parse_args()

    try:
        text = generate(
            args.audio,
            args.prompt,
            args.max_new_tokens,
            args.repetition_penalty,
        )
    except requests.HTTPError as e:
        print(f"error: {e.response.status_code} {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(text)


if __name__ == "__main__":
    main()

"""Pluggable model clients with a single interface, audio when supported.

Backends (selected by a `spec` string):
    flamingo                          local Audio Flamingo FastAPI server (:8001)
    flamingo@http://host:port         ... at a custom URL
    openai:gpt-4o-audio-preview       OpenAI; audio-capable models ingest the clip
    openrouter:<vendor/model>         OpenRouter (OpenAI-compatible); audio if able

Env vars: OPENAI_API_KEY, OPENROUTER_API_KEY, FLAMINGO_URL.

    from experiments.helpers.models import make_client
    client = make_client("openai:gpt-4o-audio-preview")
    text = client.generate("What instrument is this?", audio_path="clip.wav")
"""

import base64
import os
from pathlib import Path

import requests

TIMEOUT = 180


def _b64_audio(audio_path: str) -> tuple[str, str]:
    data = base64.b64encode(Path(audio_path).read_bytes()).decode("ascii")
    fmt = Path(audio_path).suffix.lstrip(".").lower() or "wav"
    return data, ("mp3" if fmt in ("mpeg", "mpga") else fmt)


class ModelClient:
    name: str
    model_id: str
    supports_audio: bool

    def generate(self, prompt: str, audio_path: str | None = None, max_tokens: int = 256) -> str:
        raise NotImplementedError

    def info(self) -> dict:
        return {"name": self.name, "model_id": self.model_id, "supports_audio": self.supports_audio}


# --- Flamingo (local FastAPI server) --------------------------------------

class FlamingoClient(ModelClient):
    name = "flamingo"
    supports_audio = True

    def __init__(self, url: str | None = None):
        self.url = (url or os.getenv("FLAMINGO_URL", "http://localhost:8001")).rstrip("/")
        self.model_id = "audio-flamingo"

    def info(self) -> dict:
        try:
            h = requests.get(f"{self.url}/health", timeout=10).json()
            self.model_id = h.get("model", self.model_id)
        except Exception:
            pass
        return {**super().info(), "url": self.url}

    def generate(self, prompt, audio_path=None, max_tokens=256):
        if not audio_path:
            raise ValueError("Flamingo requires audio; no audio_path given.")
        with open(audio_path, "rb") as f:
            resp = requests.post(
                f"{self.url}/analyze/upload",
                data={"prompt": prompt, "max_new_tokens": max_tokens},
                files={"file": f},
                timeout=TIMEOUT,
            )
        resp.raise_for_status()
        return resp.json()["result"]


# --- OpenAI-compatible chat completions (OpenAI + OpenRouter) -------------

class _ChatCompletionsClient(ModelClient):
    base_url: str
    env_key: str

    def __init__(self, model_id: str, supports_audio: bool | None = None):
        self.model_id = model_id
        self.supports_audio = (
            supports_audio if supports_audio is not None else _guess_audio(model_id)
        )

    def _headers(self) -> dict:
        key = os.getenv(self.env_key)
        if not key:
            raise RuntimeError(f"{self.env_key} not set (needed for {self.name}).")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def generate(self, prompt, audio_path=None, max_tokens=256):
        if audio_path and self.supports_audio:
            data, fmt = _b64_audio(audio_path)
            content = [
                {"type": "text", "text": prompt},
                {"type": "input_audio", "input_audio": {"data": data, "format": fmt}},
            ]
        else:
            content = prompt
        body = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        resp = requests.post(f"{self.base_url}/chat/completions",
                             headers=self._headers(), json=body, timeout=TIMEOUT)
        if resp.status_code != 200:
            raise RuntimeError(f"{self.name} {resp.status_code}: {resp.text[:400]}")
        return resp.json()["choices"][0]["message"]["content"]


class OpenAIClient(_ChatCompletionsClient):
    name = "openai"
    base_url = "https://api.openai.com/v1"
    env_key = "OPENAI_API_KEY"


class OpenRouterClient(_ChatCompletionsClient):
    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    env_key = "OPENROUTER_API_KEY"


_AUDIO_HINTS = ("audio", "gpt-4o", "gemini", "qwen2-audio", "qwen2.5-omni")


def _guess_audio(model_id: str) -> bool:
    m = model_id.lower()
    return any(h in m for h in _AUDIO_HINTS)


# --- Factory --------------------------------------------------------------

def make_client(spec: str) -> ModelClient:
    """Build a client from a spec like 'flamingo', 'openai:MODEL', 'openrouter:MODEL'."""
    if spec.startswith("flamingo"):
        url = spec.split("@", 1)[1] if "@" in spec else None
        return FlamingoClient(url)
    if ":" not in spec:
        raise ValueError(f"Bad model spec {spec!r}. Use 'backend:model' or 'flamingo'.")
    backend, model_id = spec.split(":", 1)
    if backend == "openai":
        return OpenAIClient(model_id)
    if backend == "openrouter":
        return OpenRouterClient(model_id)
    raise ValueError(f"Unknown backend {backend!r} in spec {spec!r}.")

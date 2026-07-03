"""
General local LLM client.

Backends
--------
ollama   – Ollama REST API (http://localhost:11434 by default)
hf       – HuggingFace transformers text-generation pipeline (local weights)

Environment variables
---------------------
LLM_BACKEND     "ollama" | "hf"           (default: ollama)
OLLAMA_URL      base URL for Ollama        (default: http://localhost:11434)
OLLAMA_MODEL    model tag for Ollama       (default: llama3.2)
HF_MODEL        HuggingFace model id/path  (default: microsoft/Phi-3-mini-4k-instruct)
"""

import os
from typing import Any

_BACKEND   = os.getenv("LLM_BACKEND",    "ollama")
_OLLAMA_URL   = os.getenv("OLLAMA_URL",  "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL","llama3.2")
_HF_MODEL     = os.getenv("HF_MODEL",    "microsoft/Phi-3-mini-4k-instruct")


class LLMClient:
    """Unified text-generation client (Ollama or HuggingFace transformers)."""

    def __init__(self, backend: str, **config: Any) -> None:
        if backend not in ("ollama", "hf"):
            raise ValueError(f"backend must be 'ollama' or 'hf', got {backend!r}")
        self.backend = backend
        self._config = config
        self._hf_pipe = None   # lazy

    # --- factories --------------------------------------------------------

    @classmethod
    def from_ollama(
        cls,
        model: str = _OLLAMA_MODEL,
        url:   str = _OLLAMA_URL,
    ) -> "LLMClient":
        return cls("ollama", model=model, url=url)

    @classmethod
    def from_hf(
        cls,
        model_id: str = _HF_MODEL,
        **pipeline_kwargs: Any,
    ) -> "LLMClient":
        """
        Wraps a HuggingFace transformers text-generation pipeline.
        Extra kwargs are forwarded to transformers.pipeline() (e.g. device_map,
        torch_dtype, trust_remote_code).
        """
        return cls("hf", model_id=model_id, **pipeline_kwargs)

    @classmethod
    def from_env(cls) -> "LLMClient":
        """Construct from environment variables."""
        if _BACKEND == "hf":
            return cls.from_hf(_HF_MODEL)
        return cls.from_ollama(_OLLAMA_MODEL, _OLLAMA_URL)

    # --- generation -------------------------------------------------------

    def generate(self, prompt: str, max_new_tokens: int = 1024) -> str:
        if self.backend == "ollama":
            return self._ollama_generate(prompt)
        return self._hf_generate(prompt, max_new_tokens)

    def _ollama_generate(self, prompt: str) -> str:
        import requests  # soft dep — only needed at call time
        resp = requests.post(
            f"{self._config['url']}/api/generate",
            json={
                "model":  self._config["model"],
                "prompt": prompt,
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def _hf_generate(self, prompt: str, max_new_tokens: int) -> str:
        if self._hf_pipe is None:
            from transformers import pipeline as hf_pipeline  # soft dep
            kw = {k: v for k, v in self._config.items() if k != "model_id"}
            self._hf_pipe = hf_pipeline(
                "text-generation",
                model=self._config["model_id"],
                **kw,
            )
        outputs = self._hf_pipe(
            prompt,
            max_new_tokens=max_new_tokens,
            return_full_text=False,
            do_sample=False,
        )
        return outputs[0]["generated_text"]

    def __repr__(self) -> str:
        if self.backend == "ollama":
            return f"LLMClient(ollama, model={self._config['model']!r})"
        return f"LLMClient(hf, model={self._config['model_id']!r})"

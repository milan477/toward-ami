"""Direct in-process Audio Flamingo Next client."""

from __future__ import annotations

import gc
import os

DEFAULT_MODEL_ID = "nvidia/audio-flamingo-next-hf"
DEFAULT_MAX_TOKENS = 192


def patch_multiwindow(model) -> bool:
    """Fix the audio tower's empty trailing multi-window timestamp bug in place."""
    import torch

    base = getattr(model, "model", model)
    cls = type(base)
    if getattr(cls, "_multiwindow_patched", False):
        return True

    def _build_audio_timestamps(self, input_ids, post_lengths, max_post_length):
        audio_token_mask = input_ids == self.config.audio_token_id
        diff = torch.diff(torch.nn.functional.pad(audio_token_mask.int(), (1, 1), value=0), dim=1)
        _, starts = torch.where(diff == 1)
        _, ends = torch.where(diff == -1)
        sample_lengths = (ends - starts).to(torch.long)

        audio_embed_frame_step = self.config.audio_frame_step * 4
        frame_offsets = (
            torch.arange(max_post_length, device=post_lengths.device, dtype=torch.float32)
            * audio_embed_frame_step
        )
        cumsum_post = torch.cat(
            [torch.zeros(1, device=post_lengths.device), torch.cumsum(post_lengths, dim=0)[:-1]]
        )
        cumsum_samples = torch.cumsum(sample_lengths, dim=0)
        sample_indices = torch.searchsorted(cumsum_samples, cumsum_post, right=True)
        sample_indices = sample_indices.clamp(max=sample_lengths.shape[0] - 1)
        sample_start_rows = torch.searchsorted(
            sample_indices, torch.arange(sample_lengths.shape[0], device=post_lengths.device)
        )
        window_indices = (
            torch.arange(post_lengths.shape[0], device=post_lengths.device)
            - sample_start_rows[sample_indices]
        )
        return window_indices.unsqueeze(1) * max_post_length * audio_embed_frame_step + frame_offsets

    cls._build_audio_timestamps = _build_audio_timestamps
    cls._multiwindow_patched = True
    return True


class DirectAFNextClient:
    """Audio Flamingo Next loaded directly with Transformers."""

    name = "af-next"
    supports_audio = True

    def __init__(self, model_id: str = DEFAULT_MODEL_ID, max_audio_seconds: float | None = None):
        self.model_id = model_id
        self.max_audio_seconds = max_audio_seconds
        self._processor = None
        self._model = None
        self._patched = False

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModel, AutoProcessor

            print(f"[af-next] loading {self.model_id} ...", flush=True)
            self._processor = AutoProcessor.from_pretrained(self.model_id)
            self._model = AutoModel.from_pretrained(
                self.model_id,
                torch_dtype=torch.bfloat16,
                device_map="auto",
            ).eval()
            self._patched = patch_multiwindow(self._model)
            print(
                f"[af-next] ready on {next(self._model.parameters()).device} "
                f"(class={type(self._model).__name__}, multiwindow_patch={self._patched})",
                flush=True,
            )
        return self._processor, self._model

    def info(self) -> dict:
        return {
            "name": self.name,
            "model_id": self.model_id,
            "supports_audio": self.supports_audio,
            "backend": "direct-in-process",
            "multiwindow_patch": True,
            "audio_truncation": self.max_audio_seconds,
        }

    def _prepare_audio(self, audio_path: str) -> tuple[str, bool]:
        if self.max_audio_seconds is None:
            return audio_path, False
        import soundfile as sf

        info = sf.info(audio_path)
        if info.frames / info.samplerate < self.max_audio_seconds:
            return audio_path, False
        import tempfile

        data, sr = sf.read(audio_path)
        clip = data[: int(self.max_audio_seconds * sr)]
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        sf.write(tmp, clip, sr)
        return tmp, True

    def generate(self, prompt: str, audio_path: str | None = None, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        if not audio_path:
            raise ValueError("af-next requires audio; no audio_path given.")
        import torch

        processor, model = self._load()
        path, is_temp = self._prepare_audio(audio_path)
        try:
            conversation = [[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "audio", "path": path},
                ],
            }]]
            batch = processor.apply_chat_template(
                conversation, tokenize=True, add_generation_prompt=True, return_dict=True,
            ).to(model.device)
            if "input_features" in batch:
                batch["input_features"] = batch["input_features"].to(model.dtype)
            with torch.inference_mode():
                outputs = model.generate(
                    **batch, max_new_tokens=max_tokens, repetition_penalty=1.2,
                )
            prompt_len = batch["input_ids"].shape[1]
            return processor.batch_decode(
                outputs[:, prompt_len:], skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
        finally:
            if is_temp:
                os.unlink(path)

    def unload(self) -> None:
        self._model = None
        self._processor = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

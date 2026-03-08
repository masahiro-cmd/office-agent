"""llama.cpp HTTP server backend adapter (OpenAI-compatible endpoint)."""

from __future__ import annotations

import logging

import requests

from office_agent.config import Config
from office_agent.llm.base import LLMBackend

logger = logging.getLogger(__name__)


class LlamaCppBackend(LLMBackend):
    """
    Connects to a locally running llama.cpp HTTP server.

    Start with: `llama-server --model model.gguf --port 8080`

    Uses the OpenAI-compatible /v1/chat/completions endpoint.
    """

    def __init__(self, config: Config) -> None:
        self._base_url = config.llamacpp_url.rstrip("/")
        self._model = config.model
        self._timeout = config.llm_timeout

    @property
    def backend_name(self) -> str:
        return f"llamacpp/{self._model}"

    def generate(self, prompt: str, system: str = "") -> str:
        """POST to /v1/chat/completions and return the assistant message."""
        url = f"{self._base_url}/v1/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }

        logger.debug(f"POST {url} model={self._model}")
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot connect to llama.cpp server at {self._base_url}. "
                "Run `llama-server --model <model.gguf>` first."
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"llama.cpp request timed out after {self._timeout}s"
            ) from exc

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"llama.cpp returned empty choices: {data}")
        return choices[0].get("message", {}).get("content", "")

"""Ollama LLM backend adapter."""

from __future__ import annotations

import logging

import requests

from office_agent.config import Config
from office_agent.llm.base import LLMBackend

logger = logging.getLogger(__name__)


class OllamaBackend(LLMBackend):
    """
    Connects to a locally running Ollama server (http://localhost:11434).

    Start Ollama with: `ollama serve`
    Pull a model with: `ollama pull llama3.2:3b`
    """

    def __init__(self, config: Config) -> None:
        self._base_url = config.ollama_url.rstrip("/")
        self._model = config.model
        self._timeout = config.llm_timeout
        self._use_json_format = config.ollama_json_format

    @property
    def backend_name(self) -> str:
        return f"ollama/{self._model}"

    def generate(self, prompt: str, system: str = "") -> str:
        """POST to /api/generate and return the full response text."""
        url = f"{self._base_url}/api/generate"
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if self._use_json_format:
            payload["format"] = "json"

        logger.debug(f"POST {url} model={self._model}")
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Run `ollama serve` first."
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Ollama request timed out after {self._timeout}s"
            ) from exc

        data = resp.json()
        return data.get("response", "")

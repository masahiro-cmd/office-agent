"""llama.cpp HTTP server backend adapter (OpenAI-compatible endpoint)."""

from __future__ import annotations

import logging

import requests

from office_agent.config import Config
from office_agent.llm.base import LLMBackend
from office_agent.llm.exceptions import LLMConnectionError, LLMTimeoutError

logger = logging.getLogger(__name__)

# Seconds to wait for the health endpoint; kept short so the GUI stays responsive.
_HEALTH_TIMEOUT = 5


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

    def check_health(self) -> dict[str, bool]:
        """GET /health; llama-server answers 503 while the model is still loading."""
        url = f"{self._base_url}/health"
        try:
            resp = requests.get(url, timeout=_HEALTH_TIMEOUT)
        except requests.RequestException as exc:
            logger.warning(f"llama.cpp health check failed ({url}): {exc}")
            return {"running": False, "model_available": False}

        # Any HTTP answer means the server is up; only 200 means the model is loaded.
        return {"running": True, "model_available": resp.status_code == 200}

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
            raise LLMConnectionError(
                f"Cannot connect to llama.cpp server at {self._base_url}. "
                "Run `llama-server --model <model.gguf>` first."
            ) from exc
        except requests.Timeout as exc:
            raise LLMTimeoutError(
                f"llama.cpp request timed out after {self._timeout}s"
            ) from exc

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"llama.cpp returned empty choices: {data}")
        return choices[0].get("message", {}).get("content", "")

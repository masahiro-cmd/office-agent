"""LLM backend package. Provides create_backend() factory."""

from __future__ import annotations

from office_agent.config import Config
from office_agent.llm.base import LLMBackend


def create_backend(config: Config) -> LLMBackend:
    """Instantiate the LLM backend specified in config."""
    backend = config.backend.lower()
    if backend == "ollama":
        from office_agent.llm.ollama import OllamaBackend
        return OllamaBackend(config)
    if backend == "llamacpp":
        from office_agent.llm.llamacpp import LlamaCppBackend
        return LlamaCppBackend(config)
    if backend == "mock":
        from office_agent.llm.mock import MockBackend
        return MockBackend(config)
    raise ValueError(f"Unknown LLM backend: {backend!r}. Choose from: ollama, llamacpp, mock")


__all__ = ["LLMBackend", "create_backend"]

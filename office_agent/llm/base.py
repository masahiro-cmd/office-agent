"""Abstract base class for LLM backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMBackend(ABC):
    """
    Abstract interface for all LLM backends.

    Concrete implementations: OllamaBackend, LlamaCppBackend, MockBackend.
    """

    @abstractmethod
    def generate(self, prompt: str, system: str = "") -> str:
        """
        Send a prompt to the LLM and return the raw text response.

        Args:
            prompt: The user prompt (task instructions, examples, etc.)
            system: Optional system/instruction prompt.

        Returns:
            Raw string response from the model.

        Raises:
            RuntimeError: On connection failure or timeout.
        """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable name of this backend (for logging)."""

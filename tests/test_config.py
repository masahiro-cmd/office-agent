"""Tests for Config: backend selection used by the GUI."""

from __future__ import annotations

import pytest

from office_agent.config import Config
from office_agent.llm import create_backend
from office_agent.llm.llamacpp import LlamaCppBackend
from office_agent.llm.ollama import OllamaBackend

_GUI_URL = "http://gui-host:11434"
_GUI_MODEL = "gui-model:1b"


class TestConfigForGui:
    def test_defaults_to_ollama_with_gui_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OFFICE_AGENT_BACKEND", raising=False)
        cfg = Config.for_gui(_GUI_URL, _GUI_MODEL)
        assert cfg.backend == "ollama"
        assert cfg.ollama_url == _GUI_URL
        assert cfg.model == _GUI_MODEL
        assert isinstance(create_backend(cfg), OllamaBackend)

    def test_llamacpp_env_ignores_gui_ollama_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OFFICE_AGENT_BACKEND", "llamacpp")
        monkeypatch.setenv("OFFICE_AGENT_LLAMACPP_URL", "http://127.0.0.1:8080")
        monkeypatch.setenv("OFFICE_AGENT_MODEL", "standard")
        cfg = Config.for_gui(_GUI_URL, _GUI_MODEL)
        assert cfg.backend == "llamacpp"
        assert cfg.llamacpp_url == "http://127.0.0.1:8080"
        assert cfg.model == "standard"
        backend = create_backend(cfg)
        assert isinstance(backend, LlamaCppBackend)
        assert backend.backend_name == "llamacpp/standard"

    def test_backend_env_is_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OFFICE_AGENT_BACKEND", "Ollama")
        cfg = Config.for_gui(_GUI_URL, _GUI_MODEL)
        assert cfg.ollama_url == _GUI_URL
        assert cfg.model == _GUI_MODEL

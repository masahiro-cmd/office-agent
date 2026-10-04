"""Tests for LLM backends: error paths and payload validation."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from office_agent.config import Config
from office_agent.llm.exceptions import LLMConnectionError, LLMTimeoutError
from office_agent.llm.llamacpp import LlamaCppBackend
from office_agent.llm.ollama import OllamaBackend

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _ollama_cfg(json_format: bool = True) -> Config:
    cfg = Config()
    cfg.ollama_url = "http://localhost:11434"
    cfg.model = "llama3.2:3b"
    cfg.llm_timeout = 30
    cfg.ollama_json_format = json_format
    return cfg


def _llamacpp_cfg() -> Config:
    cfg = Config()
    cfg.llamacpp_url = "http://localhost:8080"
    cfg.model = "test-model"
    cfg.llm_timeout = 30
    return cfg


def _ok_mock(body: dict) -> Mock:
    """Return a mock requests.Response that succeeds with the given JSON body."""
    resp = Mock()
    resp.json.return_value = body
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# OllamaBackend tests
# ---------------------------------------------------------------------------


class TestOllamaBackend:
    def test_successful_generate(self) -> None:
        with patch("requests.post", return_value=_ok_mock({"response": "hello world"})):
            backend = OllamaBackend(_ollama_cfg())
            assert backend.generate("some prompt") == "hello world"

    def test_connection_error(self) -> None:
        with patch("requests.post", side_effect=requests.ConnectionError()):
            backend = OllamaBackend(_ollama_cfg())
            with pytest.raises(RuntimeError, match="Cannot connect to Ollama"):
                backend.generate("some prompt")

    def test_timeout(self) -> None:
        with patch("requests.post", side_effect=requests.Timeout()):
            backend = OllamaBackend(_ollama_cfg())
            with pytest.raises(RuntimeError, match="timed out"):
                backend.generate("some prompt")

    def test_http_error(self) -> None:
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        with patch("requests.post", return_value=mock_resp):
            backend = OllamaBackend(_ollama_cfg())
            with pytest.raises(requests.HTTPError):
                backend.generate("some prompt")

    def test_json_format_in_payload(self) -> None:
        with patch(
            "requests.post", return_value=_ok_mock({"response": "{}"})
        ) as mock_post:
            backend = OllamaBackend(_ollama_cfg(json_format=True))
            backend.generate("some prompt")
            _, kwargs = mock_post.call_args
            assert kwargs["json"].get("format") == "json"

    def test_no_json_format_when_disabled(self) -> None:
        with patch(
            "requests.post", return_value=_ok_mock({"response": "{}"})
        ) as mock_post:
            backend = OllamaBackend(_ollama_cfg(json_format=False))
            backend.generate("some prompt")
            _, kwargs = mock_post.call_args
            assert "format" not in kwargs["json"]

    def test_backend_name(self) -> None:
        backend = OllamaBackend(_ollama_cfg())
        assert backend.backend_name == "ollama/llama3.2:3b"

    def test_check_health_model_available(self) -> None:
        body = {"models": [{"name": "llama3.2:3b"}]}
        with patch("requests.get", return_value=_ok_mock(body)):
            health = OllamaBackend(_ollama_cfg()).check_health()
            assert health == {"running": True, "model_available": True}

    def test_check_health_model_missing(self) -> None:
        body = {"models": [{"name": "other:latest"}]}
        with patch("requests.get", return_value=_ok_mock(body)):
            health = OllamaBackend(_ollama_cfg()).check_health()
            assert health == {"running": True, "model_available": False}

    def test_check_health_not_running(self) -> None:
        with patch("requests.get", side_effect=requests.ConnectionError()):
            health = OllamaBackend(_ollama_cfg()).check_health()
            assert health == {"running": False, "model_available": False}


# ---------------------------------------------------------------------------
# LlamaCppBackend tests
# ---------------------------------------------------------------------------


class TestLlamaCppBackend:
    def test_successful_generate(self) -> None:
        body = {"choices": [{"message": {"content": "generated text"}}]}
        with patch("requests.post", return_value=_ok_mock(body)):
            backend = LlamaCppBackend(_llamacpp_cfg())
            assert backend.generate("some prompt") == "generated text"

    def test_connection_error(self) -> None:
        with patch("requests.post", side_effect=requests.ConnectionError()):
            backend = LlamaCppBackend(_llamacpp_cfg())
            with pytest.raises(RuntimeError, match="Cannot connect to llama.cpp"):
                backend.generate("some prompt")

    def test_timeout(self) -> None:
        with patch("requests.post", side_effect=requests.Timeout()):
            backend = LlamaCppBackend(_llamacpp_cfg())
            with pytest.raises(RuntimeError, match="timed out"):
                backend.generate("some prompt")

    def test_empty_choices(self) -> None:
        body = {"choices": []}
        with patch("requests.post", return_value=_ok_mock(body)):
            backend = LlamaCppBackend(_llamacpp_cfg())
            with pytest.raises(RuntimeError, match="empty choices"):
                backend.generate("some prompt")

    def test_check_health_ready(self) -> None:
        with patch("requests.get", return_value=Mock(status_code=200)):
            health = LlamaCppBackend(_llamacpp_cfg()).check_health()
            assert health == {"running": True, "model_available": True}

    def test_check_health_model_loading(self) -> None:
        with patch("requests.get", return_value=Mock(status_code=503)):
            health = LlamaCppBackend(_llamacpp_cfg()).check_health()
            assert health == {"running": True, "model_available": False}

    def test_check_health_not_running(self) -> None:
        with patch("requests.get", side_effect=requests.ConnectionError()):
            health = LlamaCppBackend(_llamacpp_cfg()).check_health()
            assert health == {"running": False, "model_available": False}


# ---------------------------------------------------------------------------
# Typed errors — the GUI maps these to user-facing messages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("backend_cls", "cfg_factory"),
    [(OllamaBackend, _ollama_cfg), (LlamaCppBackend, _llamacpp_cfg)],
)
class TestTypedErrors:
    def test_connection_error_type(self, backend_cls, cfg_factory) -> None:
        with patch("requests.post", side_effect=requests.ConnectionError()):
            with pytest.raises(LLMConnectionError):
                backend_cls(cfg_factory()).generate("some prompt")

    def test_timeout_error_type(self, backend_cls, cfg_factory) -> None:
        with patch("requests.post", side_effect=requests.Timeout()):
            with pytest.raises(LLMTimeoutError):
                backend_cls(cfg_factory()).generate("some prompt")

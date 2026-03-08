"""Tests for the Orchestrator and ToolRegistry security."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from office_agent.agent.core import Orchestrator, _detect_tool, _extract_json
from office_agent.config import Config
from office_agent.llm.base import LLMBackend
from office_agent.llm.mock import MockBackend
from office_agent.tools import ALLOWED_TOOLS, ToolRegistry

# ---------------------------------------------------------------------------
# ToolRegistry whitelist tests
# ---------------------------------------------------------------------------

class TestToolRegistryWhitelist:
    def test_allowed_tools_constant(self) -> None:
        assert "create_docx" in ALLOWED_TOOLS
        assert "create_xlsx" in ALLOWED_TOOLS
        assert "create_pptx" in ALLOWED_TOOLS
        assert "generate_vba" in ALLOWED_TOOLS
        assert "read_local_text_file" in ALLOWED_TOOLS

    def test_disallowed_tool_raises(self, registry: ToolRegistry) -> None:
        with pytest.raises(PermissionError, match="not allowed"):
            registry.call("exec_shell")

    def test_disallowed_tool_os_system(self, registry: ToolRegistry) -> None:
        with pytest.raises(PermissionError):
            registry.call("os.system")

    def test_disallowed_tool_empty_string(self, registry: ToolRegistry) -> None:
        with pytest.raises(PermissionError):
            registry.call("")


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_plain_json(self) -> None:
        text = '{"key": "value"}'
        assert _extract_json(text) == {"key": "value"}

    def test_json_with_fences(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        assert _extract_json(text) == {"key": "value"}

    def test_json_with_prefix_text(self) -> None:
        text = 'Here is the plan:\n{"key": "value"}'
        assert _extract_json(text) == {"key": "value"}

    def test_invalid_json_raises(self) -> None:
        with pytest.raises((ValueError, Exception)):
            _extract_json("not json at all")


# ---------------------------------------------------------------------------
# Tool detection
# ---------------------------------------------------------------------------

class TestDetectTool:
    def test_detect_docx(self, sample_docx_plan: dict) -> None:
        assert _detect_tool(sample_docx_plan) == "create_docx"

    def test_detect_xlsx(self, sample_xlsx_plan: dict) -> None:
        assert _detect_tool(sample_xlsx_plan) == "create_xlsx"

    def test_detect_pptx(self, sample_pptx_plan: dict) -> None:
        assert _detect_tool(sample_pptx_plan) == "create_pptx"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            _detect_tool({"unknown_key": []})


# ---------------------------------------------------------------------------
# Orchestrator end-to-end with mock
# ---------------------------------------------------------------------------

class TestOrchestratorMock:
    def _make_orchestrator(self, override: dict, tmp_path: Path) -> tuple[Orchestrator, Config]:
        cfg = Config()
        cfg.backend = "mock"
        cfg.out_dir = tmp_path / "out"
        cfg.template_dir = tmp_path / "templates"
        llm = MockBackend(override_response=override)
        registry = ToolRegistry()
        orch = Orchestrator(llm=llm, registry=registry, config=cfg)
        return orch, cfg

    def test_run_docx(self, sample_docx_plan: dict, tmp_path: Path) -> None:
        orch, cfg = self._make_orchestrator(sample_docx_plan, tmp_path)
        result = orch.run(
            task="報告書を作って",
            input_files=[],
            out_dir=str(cfg.out_dir),
            template_dir=str(cfg.template_dir),
        )
        assert result["tool_used"] == "create_docx"
        assert Path(result["output_path"]).exists()

    def test_run_xlsx(self, sample_xlsx_plan: dict, tmp_path: Path) -> None:
        orch, cfg = self._make_orchestrator(sample_xlsx_plan, tmp_path)
        result = orch.run(
            task="Excelを作って",
            input_files=[],
            out_dir=str(cfg.out_dir),
            template_dir=str(cfg.template_dir),
        )
        assert result["tool_used"] == "create_xlsx"
        assert Path(result["output_path"]).exists()

    def test_run_pptx(self, sample_pptx_plan: dict, tmp_path: Path) -> None:
        orch, cfg = self._make_orchestrator(sample_pptx_plan, tmp_path)
        result = orch.run(
            task="プレゼンを作って",
            input_files=[],
            out_dir=str(cfg.out_dir),
            template_dir=str(cfg.template_dir),
        )
        assert result["tool_used"] == "create_pptx"
        assert Path(result["output_path"]).exists()


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------


class _FailThenSucceedBackend(LLMBackend):
    """Returns invalid JSON for the first ``fail_times`` calls, then valid JSON."""

    def __init__(self, valid_response: dict, fail_times: int = 1) -> None:
        self._valid = json.dumps(valid_response)
        self._fail = fail_times
        self._calls = 0

    @property
    def backend_name(self) -> str:
        return "fail_then_succeed"

    def generate(self, prompt: str, system: str = "") -> str:
        self._calls += 1
        if self._calls <= self._fail:
            return "not json at all"
        return self._valid


class TestOrchestratorRetry:
    def _make_orchestrator(
        self, llm: LLMBackend, tmp_path: Path, max_retries: int = 3
    ) -> tuple[Orchestrator, Config]:
        cfg = Config()
        cfg.backend = "mock"
        cfg.out_dir = tmp_path / "out"
        cfg.template_dir = tmp_path / "templates"
        cfg.max_retries = max_retries
        registry = ToolRegistry()
        orch = Orchestrator(llm=llm, registry=registry, config=cfg)
        return orch, cfg

    def test_retry_on_first_invalid_json(self, sample_docx_plan: dict, tmp_path: Path) -> None:
        llm = _FailThenSucceedBackend(valid_response=sample_docx_plan, fail_times=1)
        orch, cfg = self._make_orchestrator(llm, tmp_path, max_retries=3)
        result = orch.run(
            task="報告書を作って",
            input_files=[],
            out_dir=str(cfg.out_dir),
            template_dir=str(cfg.template_dir),
        )
        assert "output_path" in result
        assert Path(result["output_path"]).exists()

    def test_max_retries_exceeded(self, sample_docx_plan: dict, tmp_path: Path) -> None:
        # fail_times=10 ensures all 3 retries return invalid JSON
        llm = _FailThenSucceedBackend(valid_response=sample_docx_plan, fail_times=10)
        orch, cfg = self._make_orchestrator(llm, tmp_path, max_retries=3)
        with pytest.raises(RuntimeError):
            orch.run(
                task="報告書を作って",
                input_files=[],
                out_dir=str(cfg.out_dir),
                template_dir=str(cfg.template_dir),
            )

    def test_plan_json_saved(self, sample_docx_plan: dict, tmp_path: Path) -> None:
        llm = _FailThenSucceedBackend(valid_response=sample_docx_plan, fail_times=0)
        orch, cfg = self._make_orchestrator(llm, tmp_path, max_retries=3)
        result = orch.run(
            task="報告書を作って",
            input_files=[],
            out_dir=str(cfg.out_dir),
            template_dir=str(cfg.template_dir),
        )
        assert "plan_path" in result
        plan_path = Path(result["plan_path"])
        assert plan_path.exists()
        saved = json.loads(plan_path.read_text(encoding="utf-8"))
        assert "sections" in saved

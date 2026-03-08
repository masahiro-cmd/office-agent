"""pytest fixtures shared across all test modules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from office_agent.config import Config
from office_agent.llm.mock import MockBackend
from office_agent.tools import ToolRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config(tmp_path: Path) -> Config:
    """Config pointing to tmp_path for output, using mock backend."""
    cfg = Config()
    cfg.backend = "mock"
    cfg.out_dir = tmp_path / "out"
    cfg.template_dir = tmp_path / "templates"
    cfg.allowed_read_dirs = [str(tmp_path), "/tmp"]
    return cfg


# ---------------------------------------------------------------------------
# LLM fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm() -> MockBackend:
    """MockBackend with default canned responses."""
    return MockBackend()


@pytest.fixture
def mock_llm_docx(sample_docx_plan: dict) -> MockBackend:
    return MockBackend(override_response=sample_docx_plan)


@pytest.fixture
def mock_llm_xlsx(sample_xlsx_plan: dict) -> MockBackend:
    return MockBackend(override_response=sample_xlsx_plan)


@pytest.fixture
def mock_llm_pptx(sample_pptx_plan: dict) -> MockBackend:
    return MockBackend(override_response=sample_pptx_plan)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


# ---------------------------------------------------------------------------
# Sample plan fixtures (loaded from JSON)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_docx_plan() -> dict:
    return json.loads((FIXTURES_DIR / "sample_docx_plan.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_xlsx_plan() -> dict:
    return json.loads((FIXTURES_DIR / "sample_xlsx_plan.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_pptx_plan() -> dict:
    return json.loads((FIXTURES_DIR / "sample_pptx_plan.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Sample text file fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_text_file(tmp_path: Path) -> Path:
    """Create a small text file in tmp_path for file_tool tests."""
    f = tmp_path / "sample.txt"
    f.write_text("テストファイルの内容です。\nLine 2\nLine 3\n", encoding="utf-8")
    return f

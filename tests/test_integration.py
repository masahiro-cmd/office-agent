"""統合テスト: Ollama が起動している場合のみ実行。"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from office_agent.agent.core import Orchestrator
from office_agent.config import Config
from office_agent.llm.ollama import OllamaBackend
from office_agent.tools import ToolRegistry


def _ollama_running() -> bool:
    try:
        requests.get("http://localhost:11434", timeout=2)
        return True
    except Exception:
        return False


skip_if_no_ollama = pytest.mark.skipif(
    not _ollama_running(), reason="Ollama not running"
)


def _make_orchestrator(tmp_path: Path) -> tuple[Orchestrator, Config]:
    cfg = Config()
    cfg.backend = "ollama"
    cfg.out_dir = tmp_path / "out"
    cfg.template_dir = tmp_path / "templates"
    llm = OllamaBackend(cfg)
    registry = ToolRegistry()
    orch = Orchestrator(llm=llm, registry=registry, config=cfg)
    return orch, cfg


@skip_if_no_ollama
def test_ollama_docx(tmp_path: Path) -> None:
    """Ollama で Word 文書が生成されること。"""
    orch, cfg = _make_orchestrator(tmp_path)
    result = orch.run(
        task="月次報告書をWordで作って",
        input_files=[],
        out_dir=str(cfg.out_dir),
        template_dir=str(cfg.template_dir),
    )
    assert result["tool_used"] == "create_docx"
    assert Path(result["output_path"]).exists()
    assert Path(result["plan_path"]).exists()


@skip_if_no_ollama
def test_ollama_xlsx(tmp_path: Path) -> None:
    """Ollama で Excel ファイルが生成されること。"""
    orch, cfg = _make_orchestrator(tmp_path)
    result = orch.run(
        task="売上集計Excelを作って",
        input_files=[],
        out_dir=str(cfg.out_dir),
        template_dir=str(cfg.template_dir),
    )
    assert result["tool_used"] == "create_xlsx"
    assert Path(result["output_path"]).exists()
    assert Path(result["plan_path"]).exists()


@skip_if_no_ollama
def test_ollama_pptx(tmp_path: Path) -> None:
    """Ollama で PowerPoint ファイルが生成されること。"""
    orch, cfg = _make_orchestrator(tmp_path)
    result = orch.run(
        task="製品紹介プレゼンを3枚作って",
        input_files=[],
        out_dir=str(cfg.out_dir),
        template_dir=str(cfg.template_dir),
    )
    assert result["tool_used"] == "create_pptx"
    assert Path(result["output_path"]).exists()
    assert Path(result["plan_path"]).exists()

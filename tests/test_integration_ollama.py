"""
Integration tests for OllamaBackend — skipped when Ollama is not running.

Run with:
    pytest tests/test_integration_ollama.py -v -m integration
"""
import pytest
import requests

from office_agent.config import Config
from office_agent.llm.ollama import OllamaBackend
from office_agent.agent.core import Orchestrator
from office_agent.tools import ToolRegistry


def _ollama_running() -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_running(),
    reason="Ollama not running (http://localhost:11434). Run `ollama serve` to enable.",
)


@pytest.fixture
def ollama_cfg():
    cfg = Config()
    cfg.backend = "ollama"
    cfg.model = "llama3.2:3b"  # OFFICE_AGENT_MODEL で上書き可
    cfg.llm_timeout = 120
    return cfg


@pytest.mark.integration
class TestOllamaHealthCheck:
    def test_running(self, ollama_cfg):
        b = OllamaBackend(ollama_cfg)
        result = b.check_health()
        assert result["running"] is True

    def test_model_listed(self, ollama_cfg):
        b = OllamaBackend(ollama_cfg)
        result = b.check_health()
        if not result["model_available"]:
            pytest.skip(
                f"Model '{ollama_cfg.model}' not pulled. "
                f"Run: ollama pull {ollama_cfg.model}"
            )


@pytest.mark.integration
class TestOllamaGenerate:
    def test_generate_returns_text(self, ollama_cfg):
        b = OllamaBackend(ollama_cfg)
        if not b.check_health().get("model_available"):
            pytest.skip(f"Model '{ollama_cfg.model}' not available")
        result = b.generate('Return the JSON: {"test": true}', system="")
        assert isinstance(result, str) and len(result) > 0


@pytest.mark.integration
@pytest.mark.slow
class TestOllamaFullPipeline:
    def test_docx_generation(self, ollama_cfg, tmp_path):
        b = OllamaBackend(ollama_cfg)
        if not b.check_health().get("model_available"):
            pytest.skip(f"Model '{ollama_cfg.model}' not available")
        registry = ToolRegistry()
        orchestrator = Orchestrator(llm=b, registry=registry, config=ollama_cfg)
        result = orchestrator.run(
            task="簡単な月次報告書をWordで作って",
            input_files=[],
            out_dir=str(tmp_path),
            template_dir="./templates",
        )
        assert "output_path" in result
        from pathlib import Path
        assert Path(result["output_path"]).exists()
        import json
        plan = json.loads(Path(result["plan_path"]).read_text())
        for sec in plan["sections"]:
            assert sec.get("content") or sec.get("bullets"), \
                f"Section '{sec['heading']}' has no content or bullets"

    def test_xlsx_generation(self, ollama_cfg, tmp_path):
        b = OllamaBackend(ollama_cfg)
        if not b.check_health().get("model_available"):
            pytest.skip(f"Model '{ollama_cfg.model}' not available")
        registry = ToolRegistry()
        orchestrator = Orchestrator(llm=b, registry=registry, config=ollama_cfg)
        result = orchestrator.run(
            task="売上集計ExcelをSUM数式付きで作って",
            input_files=[],
            out_dir=str(tmp_path),
            template_dir="./templates",
        )
        assert "output_path" in result
        from pathlib import Path
        assert Path(result["output_path"]).exists()
        import json
        plan = json.loads(Path(result["plan_path"]).read_text())
        assert len(plan["sheets"][0]["rows"]) >= 3, "Too few data rows"

    def test_pptx_generation(self, ollama_cfg, tmp_path):
        b = OllamaBackend(ollama_cfg)
        if not b.check_health().get("model_available"):
            pytest.skip(f"Model '{ollama_cfg.model}' not available")
        registry = ToolRegistry()
        orchestrator = Orchestrator(llm=b, registry=registry, config=ollama_cfg)
        result = orchestrator.run(
            task="製品紹介プレゼンを3枚作って",
            input_files=[],
            out_dir=str(tmp_path),
            template_dir="./templates",
        )
        assert "output_path" in result
        from pathlib import Path
        assert Path(result["output_path"]).exists()
        import json
        plan = json.loads(Path(result["plan_path"]).read_text())
        content_slides = [s for s in plan["slides"] if s["slide_type"] == "content"]
        assert all(len(s.get("bullets", [])) >= 2 for s in content_slides), \
            "Content slides need at least 2 bullets"

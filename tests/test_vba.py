"""Tests for generate_vba tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from office_agent.tools.vba_tool import generate_vba


@pytest.fixture
def vba_plan() -> dict:
    return {
        "vba_modules": [
            {
                "name": "Module1",
                "code": "Sub HelloWorld()\n    MsgBox \"Hello\"\nEnd Sub",
                "description": "サンプルマクロ",
            },
            {
                "name": "Module2",
                "code": (
                    "Function Add(a As Integer, b As Integer) As Integer\n"
                    "    Add = a + b\nEnd Function"
                ),
                "description": "加算関数",
            },
        ]
    }


def test_generate_vba_creates_bas_files(vba_plan: dict, tmp_path: Path) -> None:
    result = generate_vba(plan=vba_plan, out_dir=str(tmp_path))
    assert result["tool_used"] == "generate_vba"
    paths = result["output_paths"]
    bas_files = [p for p in paths if p.endswith(".bas")]
    assert len(bas_files) == len(vba_plan["vba_modules"])


def test_generate_vba_creates_markdown(vba_plan: dict, tmp_path: Path) -> None:
    result = generate_vba(plan=vba_plan, out_dir=str(tmp_path))
    md_files = [p for p in result["output_paths"] if p.endswith(".md")]
    assert len(md_files) == 1
    content = Path(md_files[0]).read_text(encoding="utf-8")
    assert "Module1" in content
    assert "Module2" in content


def test_generate_vba_code_content(vba_plan: dict, tmp_path: Path) -> None:
    result = generate_vba(plan=vba_plan, out_dir=str(tmp_path))
    bas_path = next(p for p in result["output_paths"] if "Module1" in p)
    content = Path(bas_path).read_text(encoding="utf-8")
    assert 'VB_Name = "Module1"' in content
    assert "HelloWorld" in content


def test_generate_vba_empty_modules_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="vba_modules"):
        generate_vba(plan={"vba_modules": []}, out_dir=str(tmp_path))


def test_tool_registry_vba(registry, vba_plan: dict, tmp_path: Path) -> None:
    result = registry.call("generate_vba", plan=vba_plan, out_dir=str(tmp_path))
    assert result["tool_used"] == "generate_vba"

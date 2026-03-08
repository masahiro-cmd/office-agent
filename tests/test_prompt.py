"""Tests for agent.prompt: detect_doc_type and build_plan_prompt."""

from __future__ import annotations

import pytest

from office_agent.agent.prompt import build_plan_prompt, detect_doc_type

# ---------------------------------------------------------------------------
# detect_doc_type
# ---------------------------------------------------------------------------


class TestDetectDocType:
    def test_excel_keyword(self) -> None:
        assert detect_doc_type("Excelで集計したい") == "xlsx"

    def test_xlsx_keyword(self) -> None:
        assert detect_doc_type("xlsxファイルを作って") == "xlsx"

    @pytest.mark.parametrize(
        "task", ["集計レポートを作って", "スプレッドシートを作って", "表計算で管理したい"]
    )
    def test_japanese_xlsx_keywords(self, task: str) -> None:
        assert detect_doc_type(task) == "xlsx"

    def test_pptx_keyword(self) -> None:
        assert detect_doc_type("PowerPointスライドを作って") == "pptx"

    @pytest.mark.parametrize(
        "task", ["プレゼン資料を作って", "スライドを作成して", "発表資料が必要"]
    )
    def test_japanese_pptx_keywords(self, task: str) -> None:
        assert detect_doc_type(task) == "pptx"

    def test_docx_default(self) -> None:
        assert detect_doc_type("月次報告書を作って") == "docx"

    def test_case_insensitive(self) -> None:
        assert detect_doc_type("EXCEL集計") == "xlsx"


# ---------------------------------------------------------------------------
# build_plan_prompt
# ---------------------------------------------------------------------------


class TestBuildPlanPrompt:
    def test_docx_prompt_only_docx_example(self) -> None:
        prompt, _ = build_plan_prompt("月次報告書を作って", [])
        assert "sections" in prompt
        assert "sheets" not in prompt
        assert "slides" not in prompt

    def test_xlsx_prompt_only_xlsx_example(self) -> None:
        prompt, _ = build_plan_prompt("Excelで集計して", [])
        assert "sheets" in prompt
        assert "sections" not in prompt
        assert "slides" not in prompt

    def test_pptx_prompt_only_pptx_example(self) -> None:
        prompt, _ = build_plan_prompt("プレゼンを作って", [])
        assert "slides" in prompt
        assert "sections" not in prompt
        assert "sheets" not in prompt

    def test_file_context_in_prompt(self) -> None:
        prompt, _ = build_plan_prompt("月次報告書を作って", ["data.csv"])
        assert "data.csv" in prompt

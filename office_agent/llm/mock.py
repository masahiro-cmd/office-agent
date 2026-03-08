"""Mock LLM backend for testing – returns pre-defined JSON responses."""

from __future__ import annotations

import json
import logging

from office_agent.config import Config
from office_agent.llm.base import LLMBackend

logger = logging.getLogger(__name__)

# Default mock responses keyed by keywords detected in the prompt
_MOCK_DOCX = {
    "document_type": "report",
    "title": "サンプル報告書",
    "metadata": {
        "author": "テストユーザー",
        "date": "2026-03-08",
        "department": "開発部",
    },
    "sections": [
        {
            "heading": "はじめに",
            "level": 1,
            "content": "本報告書はテスト用サンプルです。",
            "bullets": ["ポイント1", "ポイント2"],
            "table": None,
            "footnote": None,
        },
        {
            "heading": "まとめ",
            "level": 1,
            "content": "以上が報告内容です。",
            "bullets": [],
            "table": {
                "headers": ["項目", "値"],
                "rows": [["売上", "1000万円"], ["利益", "200万円"]],
            },
            "footnote": "※ 数値はサンプルです",
        },
    ],
}

_MOCK_XLSX = {
    "workbook_title": "サンプル売上集計",
    "sheets": [
        {
            "name": "売上",
            "headers": ["日付", "商品名", "数量", "金額"],
            "rows": [
                ["2026-03-01", "商品A", 10, 10000],
                ["2026-03-02", "商品B", 5, 25000],
            ],
            "formulas": [{"cell": "D4", "formula": "=SUM(D2:D3)"}],
            "filters": True,
            "freeze_pane": "A2",
        }
    ],
}

_MOCK_PPTX = {
    "presentation_title": "サンプルプレゼン",
    "template": "default",
    "slides": [
        {
            "slide_type": "title",
            "title": "サンプルプレゼンテーション",
            "bullets": [],
            "table": None,
            "notes": "",
        },
        {
            "slide_type": "content",
            "title": "主な内容",
            "bullets": ["ポイントA", "ポイントB", "ポイントC"],
            "table": None,
            "notes": "スピーカーノート例",
        },
    ],
}


class MockBackend(LLMBackend):
    """
    Returns canned JSON responses without calling any LLM.

    Useful for unit tests and offline demos.
    """

    def __init__(self, config: Config | None = None, override_response: dict | None = None) -> None:
        self._override = override_response

    @property
    def backend_name(self) -> str:
        return "mock"

    def generate(self, prompt: str, system: str = "") -> str:
        """Return a JSON string based on keywords in the task section of the prompt."""
        if self._override is not None:
            return json.dumps(self._override, ensure_ascii=False)

        # Extract only the task instruction line (before the examples section)
        task_section = prompt
        if "【出力形式の例】" in prompt:
            task_section = prompt[: prompt.index("【出力形式の例】")]

        task_lower = task_section.lower()
        if (
            "excel" in task_lower
            or "xlsx" in task_lower
            or "集計" in task_section
            or "スプレッド" in task_section
        ):
            response = _MOCK_XLSX
        elif (
            "powerpoint" in task_lower
            or "pptx" in task_lower
            or "スライド" in task_section
            or "プレゼン" in task_section
        ):
            response = _MOCK_PPTX
        else:
            # Default: Word document
            response = _MOCK_DOCX

        logger.debug(f"MockBackend returning: {list(response.keys())}")
        return json.dumps(response, ensure_ascii=False, indent=2)

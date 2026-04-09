"""Tests for validator.py placeholder detection."""

from __future__ import annotations

import pytest

from office_agent.agent.validator import (
    _check_placeholder_content,
    _check_content_quality,
    validate_plan,
)


class TestCheckPlaceholderContent:
    def test_clean_plan_passes(self):
        plan = {
            "document_type": "report",
            "title": "3月度営業報告書",
            "sections": [
                {"heading": "概要", "level": 1, "content": "売上は好調でした。", "bullets": []},
            ],
        }
        _check_placeholder_content(plan)  # should not raise

    def test_title_value_detected(self):
        plan = {"document_type": "report", "title": "title_value", "sections": []}
        with pytest.raises(ValueError, match="プレースホルダ値が検出されました"):
            _check_placeholder_content(plan)

    def test_heading_value_detected(self):
        plan = {
            "document_type": "report",
            "title": "正常なタイトル",
            "sections": [
                {"heading": "heading_value", "level": 1, "content": "内容", "bullets": []},
            ],
        }
        with pytest.raises(ValueError, match="heading_value"):
            _check_placeholder_content(plan)

    def test_content_value_detected(self):
        plan = {
            "document_type": "report",
            "title": "正常なタイトル",
            "sections": [
                {"heading": "概要", "level": 1, "content": "content_value", "bullets": []},
            ],
        }
        with pytest.raises(ValueError, match="content_value"):
            _check_placeholder_content(plan)

    def test_string_placeholder_detected(self):
        plan = {"workbook_title": "string_placeholder", "sheets": []}
        with pytest.raises(ValueError, match="string_placeholder"):
            _check_placeholder_content(plan)

    def test_nested_list_detected(self):
        plan = {
            "presentation_title": "正常なタイトル",
            "slides": [
                {
                    "slide_type": "content",
                    "title": "製品特徴",
                    "bullets": ["bullet_value"],
                    "notes": "",
                }
            ],
        }
        with pytest.raises(ValueError, match="bullet_value"):
            _check_placeholder_content(plan)

    def test_valid_enum_values_not_flagged(self):
        """slide_type の "title"/"content" は有効な enum 値なのでフラグされない。"""
        plan = {
            "presentation_title": "新製品紹介",
            "slides": [
                {"slide_type": "title", "title": "新製品紹介2026", "bullets": [], "notes": ""},
                {"slide_type": "content", "title": "製品の特徴", "bullets": ["高性能"], "notes": ""},
            ],
        }
        _check_placeholder_content(plan)  # should not raise

    def test_error_message_includes_field_path(self):
        plan = {"document_type": "report", "title": "title_value", "sections": []}
        with pytest.raises(ValueError) as exc_info:
            _check_placeholder_content(plan)
        assert "title" in str(exc_info.value)
        assert "title_value" in str(exc_info.value)

    def test_validate_plan_raises_on_placeholder(self):
        """validate_plan() がプレースホルダを含むプランで ValueError を raise する。"""
        plan = {
            "document_type": "report",
            "title": "heading_value",
            "sections": [
                {"heading": "概要", "level": 1, "content": "売上好調", "bullets": []},
            ],
        }
        with pytest.raises(ValueError, match="プレースホルダ値が検出されました"):
            validate_plan(plan)


class TestCheckContentQuality:
    def test_clean_docx_passes(self):
        plan = {
            "sections": [
                {"level": 1, "content": "売上は前月比110%でした。好調な推移が続いています。", "bullets": []},
            ],
        }
        _check_content_quality(plan)  # should not raise

    def test_empty_content_and_bullets_on_level1_detected(self):
        plan = {
            "sections": [
                {"level": 1, "content": "", "bullets": []},
            ],
        }
        with pytest.raises(ValueError, match="contentもbulletsも空です"):
            _check_content_quality(plan)

    def test_level2_section_empty_content_ok(self):
        """level=2 のセクションは content/bullets が空でも許可。"""
        plan = {
            "sections": [
                {"level": 2, "content": "", "bullets": []},
            ],
        }
        _check_content_quality(plan)  # should not raise

    def test_zero_rows_detected(self):
        plan = {
            "workbook_title": "集計",
            "sheets": [{"name": "Sheet1", "headers": ["A"], "rows": []}],
        }
        with pytest.raises(ValueError, match="rowsが空です"):
            _check_content_quality(plan)

    def test_sheet_with_rows_passes(self):
        plan = {
            "sheets": [
                {"name": "Sheet1", "headers": ["A"], "rows": [["値1"], ["値2"]]},
            ],
        }
        _check_content_quality(plan)  # should not raise

    def test_empty_bullets_on_content_slide_detected(self):
        plan = {
            "slides": [
                {"slide_type": "content", "title": "特徴", "bullets": [], "notes": ""},
            ],
        }
        with pytest.raises(ValueError, match="bulletsが空です"):
            _check_content_quality(plan)

    def test_title_slide_empty_bullets_ok(self):
        """title 型スライドは bullets が空でも許可。"""
        plan = {
            "slides": [
                {"slide_type": "title", "title": "タイトル", "bullets": [], "notes": ""},
            ],
        }
        _check_content_quality(plan)  # should not raise

    def test_validate_plan_raises_on_empty_content_slide(self):
        """validate_plan() が content型スライドの空 bullets で ValueError を raise する。"""
        plan = {
            "presentation_title": "新製品紹介",
            "slides": [
                {"slide_type": "title", "title": "表紙", "bullets": [], "notes": ""},
                {"slide_type": "content", "title": "特徴", "bullets": [], "notes": ""},
            ],
        }
        with pytest.raises(ValueError, match="bulletsが空です"):
            validate_plan(plan)

    def test_validate_plan_raises_on_zero_rows(self):
        """validate_plan() が rows=[] のシートで ValueError を raise する。"""
        plan = {
            "workbook_title": "集計",
            "sheets": [{"name": "Sheet1", "headers": ["日付", "金額"], "rows": []}],
        }
        with pytest.raises(ValueError, match="rowsが空です"):
            validate_plan(plan)

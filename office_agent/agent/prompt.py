"""LLM prompt templates for document plan generation."""

from __future__ import annotations

SYSTEM_PROMPT = """\
あなたはOffice文書設計AIです。
指示に従い、JSONオブジェクトのみを返してください。
余分なテキスト・コメント・説明は一切不要です。
"""

DOCX_EXAMPLE = """\
{
  "document_type": "report",
  "title": "月次売上報告書",
  "metadata": {"author": "営業部", "date": "2026-03-08", "department": "営業部"},
  "sections": [
    {
      "heading": "概要",
      "level": 1,
      "content": "本月の売上は前月比110%でした。",
      "bullets": [],
      "table": null,
      "footnote": null
    }
  ]
}"""

XLSX_EXAMPLE = """\
{
  "workbook_title": "月次売上集計",
  "sheets": [
    {
      "name": "売上",
      "headers": ["日付", "商品名", "数量", "金額"],
      "rows": [["2026-03-01", "商品A", 10, 10000]],
      "formulas": [{"cell": "D10", "formula": "=SUM(D2:D9)"}],
      "filters": true,
      "freeze_pane": "A2"
    }
  ]
}"""

PPTX_EXAMPLE = """\
{
  "presentation_title": "製品紹介",
  "template": "default",
  "slides": [
    {"slide_type": "title", "title": "製品紹介2026", "bullets": [], "table": null, "notes": ""},
    {"slide_type": "content", "title": "特徴",
     "bullets": ["高性能", "低コスト"], "table": null, "notes": ""}
  ]
}"""

_EXAMPLES = {
    "docx": ("Word文書", DOCX_EXAMPLE),
    "xlsx": ("Excel文書", XLSX_EXAMPLE),
    "pptx": ("PowerPointプレゼン", PPTX_EXAMPLE),
}


def detect_doc_type(task: str) -> str:
    """タスク文字列から文書種別を推定して返す ("docx"/"xlsx"/"pptx")."""
    t = task.lower()
    if any(k in t for k in ["excel", "xlsx", "集計", "スプレッド", "表計算"]):
        return "xlsx"
    if any(k in t for k in ["powerpoint", "pptx", "スライド", "プレゼン", "発表資料"]):
        return "pptx"
    return "docx"  # デフォルトは Word


def build_plan_prompt(task: str, input_files: list[str]) -> tuple[str, str]:
    """
    Build (user_prompt, system_prompt) for the LLM.

    Returns:
        (prompt, system): strings to pass to LLMBackend.generate()
    """
    file_context = ""
    if input_files:
        file_context = "\n\n【参照ファイル】\n" + "\n".join(f"- {f}" for f in input_files)

    doc_type = detect_doc_type(task)
    type_label, example = _EXAMPLES[doc_type]

    prompt = f"""\
以下の指示に従い、{type_label}の生成プランをJSONで返してください。

【指示】
{task}{file_context}

【出力形式の例】
{example}

JSONのみを返してください。
"""
    return prompt, SYSTEM_PROMPT

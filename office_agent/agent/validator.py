"""JSON Schema validation for document plans."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import jsonschema

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).parent.parent / "schemas"
_PLACEHOLDER_RE = re.compile(r'.+_(value|placeholder)$')


def _load_schema(name: str) -> dict:
    path = _SCHEMA_DIR / name
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _detect_schema_name(plan: dict) -> str:
    """Choose which schema file to use based on plan structure."""
    if "sections" in plan:
        return "docx_schema.json"
    if "sheets" in plan:
        return "xlsx_schema.json"
    if "slides" in plan:
        return "pptx_schema.json"
    raise ValueError(f"Unknown plan structure: keys={list(plan.keys())}")


def _check_placeholder_content(plan: object, _path: str = "") -> None:
    """Raise ValueError if any string value looks like an unfilled placeholder."""
    if isinstance(plan, dict):
        for key, val in plan.items():
            child_path = f"{_path}.{key}" if _path else key
            if isinstance(val, str) and _PLACEHOLDER_RE.match(val):
                raise ValueError(
                    f"プレースホルダ値が検出されました: {child_path}={val}"
                )
            elif isinstance(val, (dict, list)):
                _check_placeholder_content(val, child_path)
    elif isinstance(plan, list):
        for i, item in enumerate(plan):
            child_path = f"{_path}[{i}]"
            if isinstance(item, str) and _PLACEHOLDER_RE.match(item):
                raise ValueError(
                    f"プレースホルダ値が検出されました: {child_path}={item}"
                )
            elif isinstance(item, (dict, list)):
                _check_placeholder_content(item, child_path)


def _check_content_quality(plan: dict) -> None:
    """Raise ValueError if the plan contains structurally empty content."""
    if "sections" in plan:
        for sec in plan["sections"]:
            if sec.get("level", 1) == 1:
                if not sec.get("content") and not sec.get("bullets"):
                    raise ValueError("contentもbulletsも空です")
    if "sheets" in plan:
        for sheet in plan["sheets"]:
            if not sheet.get("rows"):
                raise ValueError("rowsが空です")
    if "slides" in plan:
        for slide in plan["slides"]:
            if slide.get("slide_type") == "content" and not slide.get("bullets"):
                raise ValueError("bulletsが空です")


def validate_plan(plan: dict) -> dict:
    """
    Validate a plan dict against the appropriate JSON schema.

    Raises:
        jsonschema.ValidationError: if the plan does not match the schema.
        ValueError: if the plan structure is unrecognised.

    Returns:
        The original plan dict (unchanged) on success.
    """
    schema_name = _detect_schema_name(plan)
    schema = _load_schema(schema_name)
    jsonschema.validate(instance=plan, schema=schema)
    _check_placeholder_content(plan)
    _check_content_quality(plan)
    logger.debug(f"Validated against {schema_name}")
    return plan

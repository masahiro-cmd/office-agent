"""JSON Schema validation for document plans."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import jsonschema

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).parent.parent / "schemas"


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
    logger.debug(f"Validated against {schema_name}")
    return plan

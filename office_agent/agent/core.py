"""Orchestrator: task analysis, tool routing, retry, and logging."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from office_agent.agent.prompt import build_plan_prompt
from office_agent.agent.validator import validate_plan
from office_agent.config import Config
from office_agent.llm.base import LLMBackend
from office_agent.tools import ToolRegistry

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    2-stage document generation orchestrator.

    Stage 1: LLM → structured JSON plan
    Stage 2: JSON Schema validation
    Stage 3: Office generation tool call
    """

    def __init__(
        self,
        llm: LLMBackend,
        registry: ToolRegistry,
        config: Config,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.config = config

    def run(
        self,
        task: str,
        input_files: list[str],
        out_dir: str,
        template_dir: str,
    ) -> dict:
        """
        Execute the full generation pipeline.

        Returns a dict with keys:
            - output_path: Path to the generated file
            - plan_path: Path to the saved JSON plan
            - tool_used: Name of the tool called
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Stage 1: Generate structured plan via LLM
        plan_json = self._generate_plan(task, input_files)

        # Stage 2: Validate against JSON schema
        validated = self._validate_plan(plan_json)

        # Stage 3: Execute the appropriate tool
        result = self._execute(validated, out_dir=out_dir, template_dir=template_dir)

        # Save plan JSON for debugging
        plan_path = out_path / f"{_safe_stem(result['output_path'])}_plan.json"
        plan_path.write_text(json.dumps(validated, ensure_ascii=False, indent=2))
        result["plan_path"] = str(plan_path)

        return result

    def _generate_plan(self, task: str, input_files: list[str]) -> dict:
        """Call LLM to produce a structured JSON document plan."""
        for attempt in range(1, self.config.max_retries + 1):
            logger.info(f"LLM plan generation attempt {attempt}/{self.config.max_retries}")
            prompt, system = build_plan_prompt(task, input_files)
            raw = self.llm.generate(prompt=prompt, system=system)
            logger.debug(f"LLM raw response:\n{raw[:500]}")
            try:
                plan = _extract_json(raw)
                logger.debug(f"Plan generated: {json.dumps(plan, ensure_ascii=False)[:200]}")
                return plan
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(f"JSON parse failed (attempt {attempt}): {exc}")
                if attempt == self.config.max_retries:
                    raise RuntimeError(
                        f"LLM did not return valid JSON after {self.config.max_retries} attempts"
                    ) from exc
        raise RuntimeError("Unreachable")

    def _validate_plan(self, plan_json: dict) -> dict:
        """Validate the plan dict against the appropriate JSON schema."""
        doc_type = plan_json.get("document_type") or plan_json.get("workbook_title") or ""
        validated = validate_plan(plan_json)
        logger.info(f"Plan validated (type hint: {doc_type!r})")
        return validated

    def _execute(self, plan: dict, out_dir: str, template_dir: str) -> dict:
        """Determine the correct tool and invoke it via ToolRegistry."""
        tool_name = _detect_tool(plan)
        logger.info(f"Executing tool: {tool_name}")
        result = self.registry.call(
            tool_name,
            plan=plan,
            out_dir=out_dir,
            template_dir=template_dir,
        )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response string."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first and last fence lines
        inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = inner.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start : end + 1])


def _safe_stem(output_path: str) -> str:
    """Return the stem (filename without extension) of output_path."""
    return Path(output_path).stem


def _detect_tool(plan: dict) -> str:
    """Infer which generation tool to call based on plan keys."""
    if "sections" in plan:
        return "create_docx"
    if "sheets" in plan:
        return "create_xlsx"
    if "slides" in plan:
        return "create_pptx"
    if "vba_modules" in plan:
        return "generate_vba"
    raise ValueError(f"Cannot determine document type from plan keys: {list(plan.keys())}")

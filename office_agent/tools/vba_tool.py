"""generate_vba: Generate VBA module code from a spec JSON. Does NOT execute code."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_vba(plan: dict, out_dir: str, template_dir: str = "./templates") -> dict:
    """
    Generate VBA module source files from a plan dict.

    SECURITY: This tool only writes .bas and .md files.
    It does NOT execute any code or macro.

    Args:
        plan: A dict with a "vba_modules" key containing a list of module specs.
              Each module spec: {"name": str, "code": str, "description": str}
        out_dir: Directory where the output files will be saved.
        template_dir: Not used (kept for consistent signature).

    Returns:
        {"output_paths": list[str], "tool_used": "generate_vba"}
    """
    modules: list[dict] = plan.get("vba_modules", [])
    if not modules:
        raise ValueError("plan must contain 'vba_modules' key with at least one module")

    out_path = Path(out_dir) / "vba"
    out_path.mkdir(parents=True, exist_ok=True)

    output_paths: list[str] = []

    # Generate a markdown summary
    md_lines = ["# VBA Modules\n"]

    for module in modules:
        name: str = module.get("name", "Module1")
        code: str = module.get("code", "")
        description: str = module.get("description", "")

        # Write .bas file
        bas_path = out_path / f"{name}.bas"
        bas_content = _format_bas(name, code, description)
        bas_path.write_text(bas_content, encoding="utf-8")
        output_paths.append(str(bas_path))
        logger.info(f"Saved VBA module: {bas_path}")

        # Add to markdown
        md_lines.append(f"## {name}\n")
        if description:
            md_lines.append(f"{description}\n")
        md_lines.append(f"```vba\n{code}\n```\n")

    # Write summary markdown
    md_path = out_path / "vba_modules.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    output_paths.append(str(md_path))

    return {"output_paths": output_paths, "tool_used": "generate_vba"}


def _format_bas(name: str, code: str, description: str) -> str:
    """Format a VBA module as a .bas file string."""
    lines = [
        f"Attribute VB_Name = \"{name}\"",
        "",
    ]
    if description:
        lines.append(f"' {description}")
        lines.append("")
    lines.append(code)
    return "\n".join(lines)

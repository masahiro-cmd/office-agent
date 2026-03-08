"""Tool registry with whitelist enforcement."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Whitelist of permitted tool names. Any tool not in this set will be rejected.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "create_docx",
        "create_xlsx",
        "create_pptx",
        "generate_vba",
        "read_local_text_file",
    }
)


class ToolRegistry:
    """
    Central dispatcher for all document generation tools.

    Security guarantee: only tools listed in ALLOWED_TOOLS can be invoked.
    Requests for any other tool name raise PermissionError immediately,
    regardless of what the LLM requested.
    """

    def call(self, tool_name: str, **kwargs: Any) -> dict:
        """
        Invoke a whitelisted tool by name.

        Args:
            tool_name: Must be one of ALLOWED_TOOLS.
            **kwargs: Arguments forwarded to the tool function.

        Returns:
            A dict with at minimum {"output_path": str, "tool_used": str}.

        Raises:
            PermissionError: If tool_name is not in ALLOWED_TOOLS.
            ValueError: If tool_name is valid but unknown (programming error).
        """
        if tool_name not in ALLOWED_TOOLS:
            raise PermissionError(
                f"Tool '{tool_name}' is not allowed. "
                f"Permitted tools: {sorted(ALLOWED_TOOLS)}"
            )

        logger.info(f"ToolRegistry: calling {tool_name}")

        if tool_name == "create_docx":
            from office_agent.tools.docx_tool import create_docx
            return create_docx(**kwargs)

        if tool_name == "create_xlsx":
            from office_agent.tools.xlsx_tool import create_xlsx
            return create_xlsx(**kwargs)

        if tool_name == "create_pptx":
            from office_agent.tools.pptx_tool import create_pptx
            return create_pptx(**kwargs)

        if tool_name == "generate_vba":
            from office_agent.tools.vba_tool import generate_vba
            return generate_vba(**kwargs)

        if tool_name == "read_local_text_file":
            from office_agent.tools.file_tool import read_local_text_file
            return read_local_text_file(**kwargs)

        # Should be unreachable given the whitelist check above
        raise ValueError(f"Tool '{tool_name}' is whitelisted but has no implementation.")


__all__ = ["ToolRegistry", "ALLOWED_TOOLS"]

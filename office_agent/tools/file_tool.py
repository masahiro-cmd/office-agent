"""read_local_text_file: Sandboxed local file reader."""

from __future__ import annotations

import logging
from pathlib import Path

from office_agent.config import Config

logger = logging.getLogger(__name__)

# Default allowed directories when no Config is provided
_DEFAULT_ALLOWED_DIRS: list[str] = [
    str(Path(".").resolve()),
    "/tmp",
]

# Maximum file size to read (safety limit: 5 MB)
_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024


def read_local_text_file(
    path: str,
    out_dir: str = "",
    template_dir: str = "",
    plan: dict | None = None,
    config: Config | None = None,
    allowed_dirs: list[str] | None = None,
) -> dict:
    """
    Read a local text file, enforcing a directory sandbox.

    The ``allowed_dirs`` list (or config.allowed_read_dirs) restricts which
    directories may be read. Attempts to read outside these directories
    (including path traversal attacks) raise PermissionError.

    Args:
        path: Absolute or relative path to the file.
        config: Optional Config instance for allowed_dirs.
        allowed_dirs: Explicit list of allowed directory prefixes (overrides config).
        out_dir / template_dir / plan: Ignored, present for uniform ToolRegistry signature.

    Returns:
        {"content": str, "path": str, "tool_used": "read_local_text_file"}

    Raises:
        PermissionError: If the resolved path is outside allowed directories.
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is too large or not a text file.
    """
    resolved = Path(path).resolve()

    # Determine allowed directories
    if allowed_dirs is not None:
        effective_allowed = [str(Path(d).resolve()) for d in allowed_dirs]
    elif config is not None:
        effective_allowed = config.allowed_read_dirs
    else:
        effective_allowed = _DEFAULT_ALLOWED_DIRS

    # Sandbox check: resolved path must start with one of the allowed dirs
    if not any(_is_within(resolved, Path(allowed)) for allowed in effective_allowed):
        raise PermissionError(
            f"Access denied: '{resolved}' is not within allowed directories: {effective_allowed}"
        )

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")

    if not resolved.is_file():
        raise ValueError(f"Not a file: {resolved}")

    size = resolved.stat().st_size
    if size > _MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File too large: {size} bytes (max {_MAX_FILE_SIZE_BYTES} bytes)"
        )

    content = resolved.read_text(encoding="utf-8", errors="replace")
    logger.info(f"Read file: {resolved} ({len(content)} chars)")

    return {
        "content": content,
        "path": str(resolved),
        "tool_used": "read_local_text_file",
    }


def _is_within(child: Path, parent: Path) -> bool:
    """Return True if child is inside parent (inclusive)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False

"""
applier.py: Verify and apply a signed update package (offline machine).

Extracts only whitelisted file extensions to prevent arbitrary file writes.
"""

from __future__ import annotations

import logging
import tarfile
from pathlib import Path

from office_agent.update.verifier import verify_package

logger = logging.getLogger(__name__)

# Only extract these file types from the update archive
_ALLOWED_EXTENSIONS = frozenset({".py", ".json", ".txt", ".toml", ".md"})


def apply_package(package_path: Path, target_dir: Path | None = None) -> dict:
    """
    Verify and apply a signed update package.

    Steps:
    1. SHA-256 verification (delegates to verifier.py)
    2. Extract whitelisted files to target_dir (default: current directory)

    Args:
        package_path: Path to the .tar.gz package.
        target_dir: Destination for extracted files (default: cwd).

    Returns:
        {"extracted_files": list[str], "version": str}

    Raises:
        PermissionError: If verification fails.
        ValueError: If the archive contains disallowed file types.
    """
    package_path = Path(package_path).resolve()
    target = Path(target_dir).resolve() if target_dir else Path(".").resolve()

    # Step 1: Verify
    if not verify_package(package_path):
        raise PermissionError(
            f"Package verification failed for {package_path}. Apply aborted."
        )

    extracted: list[str] = []

    # Step 2: Extract with safety checks
    with tarfile.open(package_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue

            member_path = Path(member.name)

            # Check extension whitelist
            if member_path.suffix not in _ALLOWED_EXTENSIONS:
                logger.warning(f"Skipping disallowed file type: {member.name}")
                continue

            # Prevent path traversal
            resolved_target = (target / member.name).resolve()
            if not str(resolved_target).startswith(str(target)):
                logger.warning(f"Skipping path traversal attempt: {member.name}")
                continue

            resolved_target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src:  # type: ignore[arg-type]
                resolved_target.write_bytes(src.read())

            extracted.append(str(resolved_target.relative_to(target)))
            logger.debug(f"Extracted: {member.name}")

    logger.info(f"Applied update: {len(extracted)} files extracted to {target}")

    # Extract version from manifest filename pattern
    name = package_path.name
    version = "unknown"
    if name.startswith("office_agent_") and name.endswith(".tar.gz"):
        version = name[len("office_agent_") : -len(".tar.gz")]

    return {"extracted_files": extracted, "version": version}

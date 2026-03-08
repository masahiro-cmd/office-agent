"""
verifier.py: SHA-256 verification of update packages (offline machine).

Uses only Python standard library (hashlib). No network access required.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def verify_package(package_path: Path) -> bool:
    """
    Verify that a .tar.gz update package matches its manifest.

    Looks for a sibling manifest file named:
        <stem>_manifest.json  (e.g. office_agent_0.2.0_manifest.json)

    Args:
        package_path: Path to the .tar.gz package file.

    Returns:
        True if verification passes, False otherwise.

    Raises:
        FileNotFoundError: If the package or manifest file does not exist.
    """
    package_path = Path(package_path).resolve()

    if not package_path.exists():
        raise FileNotFoundError(f"Package not found: {package_path}")

    # Locate manifest (same directory, sibling file)
    manifest_path = _find_manifest(package_path)
    if not manifest_path or not manifest_path.exists():
        logger.error(f"Manifest not found for {package_path}")
        return False

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_hash: str = manifest.get("sha256", "")

    if not expected_hash:
        logger.error("Manifest has no 'sha256' field")
        return False

    actual_hash = _sha256(package_path)
    if actual_hash != expected_hash:
        logger.error(
            f"Hash mismatch!\n  expected: {expected_hash}\n  actual:   {actual_hash}"
        )
        return False

    logger.info(f"Verification passed: {package_path.name} sha256={actual_hash[:16]}...")
    return True


def _find_manifest(package_path: Path) -> Path | None:
    """Derive the manifest path from the package path."""
    # Strip .tar.gz to get stem
    name = package_path.name
    if name.endswith(".tar.gz"):
        stem = name[: -len(".tar.gz")]
    else:
        stem = package_path.stem
    manifest_name = f"{stem}_manifest.json"
    return package_path.parent / manifest_name


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

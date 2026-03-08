"""
packager.py: Create a signed update package (run on online machine).

The package is a tar.gz archive accompanied by a SHA-256 manifest file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tarfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Files and directories to include in the update package
_INCLUDE_PATTERNS = [
    "office_agent/**/*.py",
    "office_agent/**/*.json",
    "requirements.txt",
    "pyproject.toml",
]

_MANIFEST_FILENAME = "manifest.json"


def create_update_package(version: str, out_dir: Path, source_dir: Path | None = None) -> dict:
    """
    Bundle the office_agent source into a versioned tar.gz with SHA-256 manifest.

    Args:
        version: Version string, e.g. "0.2.0"
        out_dir: Directory to write the package and manifest to.
        source_dir: Root of the source tree (defaults to cwd).

    Returns:
        {"package_path": str, "manifest_path": str, "version": str}
    """
    src = source_dir or Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    pkg_name = f"office_agent_{version}.tar.gz"
    pkg_path = out_dir / pkg_name

    collected: list[Path] = []
    for pattern in _INCLUDE_PATTERNS:
        collected.extend(src.glob(pattern))

    if not collected:
        raise FileNotFoundError(f"No source files found under {src}")

    # Build tar.gz
    with tarfile.open(pkg_path, "w:gz") as tar:
        for file_path in sorted(set(collected)):
            arcname = str(file_path.relative_to(src))
            tar.add(str(file_path), arcname=arcname)

    logger.info(f"Created archive: {pkg_path} ({len(collected)} files)")

    # Compute SHA-256 of the archive
    pkg_hash = _sha256(pkg_path)

    # Build manifest
    manifest = {
        "version": version,
        "package": pkg_name,
        "sha256": pkg_hash,
        "files": {
            str(f.relative_to(src)): _sha256(f)
            for f in sorted(set(collected))
        },
    }
    manifest_path = out_dir / f"office_agent_{version}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Created manifest: {manifest_path}")

    return {
        "package_path": str(pkg_path),
        "manifest_path": str(manifest_path),
        "version": version,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

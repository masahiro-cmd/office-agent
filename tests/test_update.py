"""Tests for the update system (packager, verifier, applier)."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from office_agent.update.applier import apply_package
from office_agent.update.packager import create_update_package
from office_agent.update.verifier import verify_package

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source_tree(root: Path) -> None:
    """Create a minimal source tree for packaging tests."""
    pkg = root / "office_agent"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    (pkg / "config.py").write_text("# config stub\n", encoding="utf-8")
    (root / "requirements.txt").write_text("click>=8.1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "office-agent"\n', encoding="utf-8")


# ---------------------------------------------------------------------------
# Packager tests
# ---------------------------------------------------------------------------

class TestPackager:
    def test_creates_archive(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        _make_source_tree(src)
        out = tmp_path / "packages"
        result = create_update_package(version="0.2.0", out_dir=out, source_dir=src)
        assert Path(result["package_path"]).exists()
        assert result["version"] == "0.2.0"

    def test_creates_manifest(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        _make_source_tree(src)
        out = tmp_path / "packages"
        result = create_update_package(version="0.2.0", out_dir=out, source_dir=src)
        manifest_path = Path(result["manifest_path"])
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == "0.2.0"
        assert "sha256" in manifest

    def test_archive_is_valid_tarball(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        _make_source_tree(src)
        out = tmp_path / "packages"
        result = create_update_package(version="0.3.0", out_dir=out, source_dir=src)
        assert tarfile.is_tarfile(result["package_path"])

    def test_no_source_files_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "empty_src"
        src.mkdir()
        out = tmp_path / "packages"
        with pytest.raises(FileNotFoundError):
            create_update_package(version="0.4.0", out_dir=out, source_dir=src)


# ---------------------------------------------------------------------------
# Verifier tests
# ---------------------------------------------------------------------------

class TestVerifier:
    def _make_package(self, tmp_path: Path, version: str = "0.2.0") -> tuple[Path, Path]:
        src = tmp_path / "src"
        src.mkdir(exist_ok=True)
        _make_source_tree(src)
        out = tmp_path / "packages"
        result = create_update_package(version=version, out_dir=out, source_dir=src)
        return Path(result["package_path"]), Path(result["manifest_path"])

    def test_valid_package_passes(self, tmp_path: Path) -> None:
        pkg_path, _ = self._make_package(tmp_path)
        assert verify_package(pkg_path) is True

    def test_tampered_package_fails(self, tmp_path: Path) -> None:
        pkg_path, _ = self._make_package(tmp_path)
        # Corrupt the archive
        with open(pkg_path, "ab") as f:
            f.write(b"CORRUPTED")
        assert verify_package(pkg_path) is False

    def test_missing_manifest_fails(self, tmp_path: Path) -> None:
        pkg_path, manifest_path = self._make_package(tmp_path)
        manifest_path.unlink()
        assert verify_package(pkg_path) is False

    def test_nonexistent_package_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            verify_package(tmp_path / "nonexistent.tar.gz")


# ---------------------------------------------------------------------------
# Applier tests
# ---------------------------------------------------------------------------

class TestApplier:
    def _make_package(self, tmp_path: Path, version: str = "0.2.0") -> Path:
        src = tmp_path / "src"
        src.mkdir(exist_ok=True)
        _make_source_tree(src)
        out = tmp_path / "packages"
        result = create_update_package(version=version, out_dir=out, source_dir=src)
        return Path(result["package_path"])

    def test_apply_verified_package(self, tmp_path: Path) -> None:
        pkg_path = self._make_package(tmp_path)
        target = tmp_path / "install"
        result = apply_package(package_path=pkg_path, target_dir=target)
        assert len(result["extracted_files"]) > 0
        assert result["version"] == "0.2.0"

    def test_apply_extracts_py_files(self, tmp_path: Path) -> None:
        pkg_path = self._make_package(tmp_path)
        target = tmp_path / "install"
        apply_package(package_path=pkg_path, target_dir=target)
        extracted_py = list(target.rglob("*.py"))
        assert len(extracted_py) > 0

    def test_apply_tampered_raises(self, tmp_path: Path) -> None:
        pkg_path = self._make_package(tmp_path)
        with open(pkg_path, "ab") as f:
            f.write(b"TAMPERED")
        with pytest.raises(PermissionError, match="verification failed"):
            apply_package(package_path=pkg_path)

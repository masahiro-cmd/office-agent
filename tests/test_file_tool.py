"""Tests for file_tool: sandbox, path traversal, and size limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from office_agent.config import Config
from office_agent.tools.file_tool import read_local_text_file


class TestReadLocalTextFile:
    def test_read_file_success(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("Hello, world!", encoding="utf-8")
        result = read_local_text_file(str(f), allowed_dirs=[str(tmp_path)])
        assert result["content"] == "Hello, world!"
        assert result["path"] == str(f.resolve())
        assert result["tool_used"] == "read_local_text_file"

    def test_read_file_outside_allowed_dirs(self, tmp_path: Path) -> None:
        # File lives in tmp_path, but only a non-parent subdir is allowed
        f = tmp_path / "secret.txt"
        f.write_text("secret", encoding="utf-8")
        allowed_subdir = tmp_path / "allowed_only"
        allowed_subdir.mkdir()
        with pytest.raises(PermissionError):
            read_local_text_file(str(f), allowed_dirs=[str(allowed_subdir)])

    def test_read_file_path_traversal(self, tmp_path: Path) -> None:
        # "../../etc/passwd" resolves outside tmp_path regardless of CWD
        with pytest.raises(PermissionError):
            read_local_text_file("../../etc/passwd", allowed_dirs=[str(tmp_path)])

    def test_read_file_not_found(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "nonexistent.txt")
        with pytest.raises(FileNotFoundError):
            read_local_text_file(missing, allowed_dirs=[str(tmp_path)])

    def test_read_file_not_a_file(self, tmp_path: Path) -> None:
        # Passing a directory path raises ValueError
        with pytest.raises(ValueError):
            read_local_text_file(str(tmp_path), allowed_dirs=[str(tmp_path)])

    def test_read_file_too_large(self, tmp_path: Path) -> None:
        large_file = tmp_path / "large.bin"
        large_file.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        with pytest.raises(ValueError, match="too large"):
            read_local_text_file(str(large_file), allowed_dirs=[str(tmp_path)])

    def test_read_file_uses_config(self, tmp_path: Path) -> None:
        cfg = Config()
        cfg.allowed_read_dirs = [str(tmp_path)]
        f = tmp_path / "config_test.txt"
        f.write_text("config content", encoding="utf-8")
        result = read_local_text_file(str(f), config=cfg)
        assert result["content"] == "config content"

    def test_read_file_explicit_allowed_dirs(self, tmp_path: Path) -> None:
        f = tmp_path / "explicit.txt"
        f.write_text("explicit content", encoding="utf-8")
        result = read_local_text_file(str(f), allowed_dirs=[str(tmp_path)])
        assert result["content"] == "explicit content"

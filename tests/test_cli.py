"""Tests for the CLI entry point (click commands)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from office_agent.cli import cli


def _make_package(tmp_path: Path, version: str = "0.1.0") -> Path:
    """Helper: create a real signed package for verify/apply tests."""
    from office_agent.update.packager import create_update_package

    result = create_update_package(version=version, out_dir=tmp_path)
    return Path(result["package_path"])


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_run_mock_docx(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["run", "--task", "報告書を作って", "--backend", "mock",
             "--out", str(tmp_path / "out")],
        )
        assert result.exit_code == 0, result.output
        assert "完了" in result.output

    def test_run_mock_xlsx(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--task",
                "売上集計Excelを作って",
                "--backend",
                "mock",
                "--out",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "完了" in result.output

    def test_run_mock_pptx(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--task",
                "製品紹介プレゼンを作って",
                "--backend",
                "mock",
                "--out",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "完了" in result.output

    def test_run_output_file_exists(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["run", "--task", "報告書を作って", "--backend", "mock", "--out", str(out_dir)],
        )
        assert result.exit_code == 0, result.output
        generated = list(out_dir.glob("*.docx"))
        assert len(generated) >= 1

    def test_run_missing_task(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["run"])
        assert result.exit_code == 2  # Click: missing required option

    def test_run_verbose(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--task",
                "報告書を作って",
                "--backend",
                "mock",
                "--out",
                str(tmp_path / "out"),
                "--verbose",
            ],
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# package-update / verify-update / apply-update commands
# ---------------------------------------------------------------------------


class TestUpdateCommands:
    def test_package_update(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["package-update", "--version", "0.2.0", "--out", str(tmp_path)],
        )
        assert result.exit_code == 0, result.output
        tar_files = list(tmp_path.glob("*.tar.gz"))
        assert len(tar_files) >= 1

    def test_verify_update_valid(self, tmp_path: Path) -> None:
        pkg_path = _make_package(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["verify-update", str(pkg_path)])
        assert result.exit_code == 0, result.output
        assert "検証成功" in result.output

    def test_verify_update_tampered(self, tmp_path: Path) -> None:
        pkg_path = _make_package(tmp_path)
        with open(pkg_path, "ab") as f:
            f.write(b"TAMPERED")
        runner = CliRunner()
        result = runner.invoke(cli, ["verify-update", str(pkg_path)])
        assert result.exit_code == 1
        assert "検証失敗" in result.output

    def test_apply_update(self, tmp_path: Path) -> None:
        pkg_path = _make_package(tmp_path / "pkg")
        runner = CliRunner()
        result = runner.invoke(cli, ["apply-update", str(pkg_path)])
        assert result.exit_code == 0, result.output
        assert "更新適用完了" in result.output

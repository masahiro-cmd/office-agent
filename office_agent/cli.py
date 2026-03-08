"""CLI entry point for office-agent using Click."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from office_agent.config import Config

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


@click.group()
@click.version_option()
def cli() -> None:
    """office-agent: Local offline AI agent for Microsoft Office document generation."""


@cli.command()
@click.option("--task", "-t", required=True, help="Natural language task description (Japanese OK)")
@click.option("--out", "-o", default="./out", show_default=True, help="Output directory")
@click.option(
    "--backend",
    "-b",
    default=None,
    type=click.Choice(["ollama", "llamacpp", "mock"]),
    help="LLM backend (overrides config/env)",
)
@click.option("--model", "-m", default=None, help="Model name (overrides config/env)")
@click.option(
    "--input-file",
    "-i",
    multiple=True,
    help="Input file paths (can be specified multiple times)",
)
@click.option("--template-dir", default="./templates", show_default=True, help="Template directory")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def run(
    task: str,
    out: str,
    backend: str | None,
    model: str | None,
    input_file: tuple[str, ...],
    template_dir: str,
    verbose: bool,
) -> None:
    """Generate an Office document from a natural language task description."""
    _setup_logging(verbose)

    config = Config.from_env()
    if backend:
        config.backend = backend
    if model:
        config.model = model
    config.out_dir = Path(out)
    config.template_dir = Path(template_dir)

    # Lazy import to avoid heavy deps at CLI load time
    from office_agent.agent.core import Orchestrator
    from office_agent.llm import create_backend
    from office_agent.tools import ToolRegistry

    llm = create_backend(config)
    registry = ToolRegistry()
    orchestrator = Orchestrator(llm=llm, registry=registry, config=config)

    click.echo(f"[office-agent] タスク: {task}")
    click.echo(f"[office-agent] バックエンド: {config.backend} / モデル: {config.model}")

    result = orchestrator.run(
        task=task,
        input_files=list(input_file),
        out_dir=str(config.out_dir),
        template_dir=str(config.template_dir),
    )

    click.echo(f"[office-agent] 完了: {result}")


@cli.command("package-update")
@click.option("--version", required=True, help="Version string for the update package")
@click.option(
    "--out", "-o", default="./update_packages", show_default=True, help="Output directory"
)
@click.option("--verbose", "-v", is_flag=True)
def package_update(version: str, out: str, verbose: bool) -> None:
    """Create a signed update package (run on online machine)."""
    _setup_logging(verbose)
    from office_agent.update.packager import create_update_package

    result = create_update_package(version=version, out_dir=Path(out))
    click.echo(f"[office-agent] 更新パッケージ作成完了: {result}")


@cli.command("verify-update")
@click.argument("package_path", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True)
def verify_update(package_path: str, verbose: bool) -> None:
    """Verify the SHA-256 signature of an update package."""
    _setup_logging(verbose)
    from office_agent.update.verifier import verify_package

    ok = verify_package(package_path=Path(package_path))
    if ok:
        click.echo("[office-agent] 検証成功: パッケージは正当です")
    else:
        click.echo(
            "[office-agent] 検証失敗: パッケージが改ざんされている可能性があります",
            err=True,
        )
        sys.exit(1)


@cli.command("apply-update")
@click.argument("package_path", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True)
def apply_update(package_path: str, verbose: bool) -> None:
    """Verify and apply a signed update package."""
    _setup_logging(verbose)
    from office_agent.update.applier import apply_package

    result = apply_package(package_path=Path(package_path))
    click.echo(f"[office-agent] 更新適用完了: {result}")


if __name__ == "__main__":
    cli()

"""Configuration management for office-agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Application configuration loaded from environment variables or defaults."""

    # LLM backend selection: "ollama" | "llamacpp" | "mock"
    backend: str = field(default_factory=lambda: os.environ.get("OFFICE_AGENT_BACKEND", "ollama"))

    # Model name passed to the LLM backend
    model: str = field(default_factory=lambda: os.environ.get("OFFICE_AGENT_MODEL", "llama3.2:3b"))

    # Ollama server URL
    ollama_url: str = field(
        default_factory=lambda: os.environ.get("OFFICE_AGENT_OLLAMA_URL", "http://localhost:11434")
    )

    # llama.cpp HTTP server URL
    llamacpp_url: str = field(
        default_factory=lambda: os.environ.get(
            "OFFICE_AGENT_LLAMACPP_URL", "http://localhost:8080"
        )
    )

    # Output directory for generated files
    out_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("OFFICE_AGENT_OUT_DIR", "./out"))
    )

    # Template directory
    template_dir: Path = field(default_factory=lambda: Path("./templates"))

    # Directories allowed for read_local_text_file (sandbox)
    allowed_read_dirs: list[str] = field(
        default_factory=lambda: os.environ.get(
            "OFFICE_AGENT_ALLOWED_READ_DIRS", "./,/tmp"
        ).split(",")
    )

    # LLM request timeout in seconds
    llm_timeout: int = field(
        default_factory=lambda: int(os.environ.get("OFFICE_AGENT_LLM_TIMEOUT", "120"))
    )

    # Max retries for LLM calls
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get("OFFICE_AGENT_MAX_RETRIES", "3"))
    )

    # Ollama の JSON 強制モード（format: "json"）を有効にするか
    ollama_json_format: bool = field(
        default_factory=lambda: os.environ.get(
            "OFFICE_AGENT_OLLAMA_JSON_FORMAT", "true"
        ).lower() != "false"
    )

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.template_dir = Path(self.template_dir)
        # Normalize allowed_read_dirs to resolved absolute paths
        self.allowed_read_dirs = [
            str(Path(d.strip()).resolve()) for d in self.allowed_read_dirs
        ]

    @classmethod
    def from_env(cls) -> Config:
        """Create a Config instance populated from environment variables."""
        return cls()

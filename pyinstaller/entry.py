"""
PyInstaller entry point for office-agent.

This module is the target of the PyInstaller build. It invokes Streamlit
programmatically so the frozen executable runs the GUI without needing
a Python installation or a visible 'streamlit' command on PATH.

The C# launcher sets all OFFICE_AGENT_* and STREAMLIT_* environment
variables before spawning this executable — no .env file is needed.
"""

import os
import sys


def _resolve_gui_path() -> str:
    """Return the absolute path to office_agent/gui.py inside the bundle."""
    # sys._MEIPASS is set by PyInstaller to the temp extraction directory.
    # In development (not frozen) fall back to the repo root.
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "office_agent", "gui.py")


def main() -> None:
    gui_path = _resolve_gui_path()

    if not os.path.isfile(gui_path):
        print(f"[ERROR] GUI entry point not found: {gui_path}", file=sys.stderr)
        sys.exit(1)

    # Override sys.argv so Streamlit's Click-based CLI receives correct args.
    # All server flags are also set via environment variables injected by the
    # C# launcher, but explicit flags here serve as a safety fallback.
    sys.argv = [
        "streamlit",
        "run",
        gui_path,
        "--server.port=8501",
        "--server.address=127.0.0.1",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
    ]

    from streamlit.web import cli as stcli  # noqa: PLC0415

    sys.exit(stcli.main())


if __name__ == "__main__":
    main()

# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for office-agent (Windows x64, --onedir)
#
# Build command (run from repo root on a Windows machine):
#   pyinstaller pyinstaller/office_agent.spec --distpath build/dist --workpath build/work
#
# Output:
#   build/dist/app/OfficeAgentBackend.exe   <- PyInstaller bootloader
#   build/dist/app/_internal/               <- Python runtime + all deps
#
# The C# launcher spawns OfficeAgentBackend.exe with environment variables
# pre-set; users never interact with this binary directly.

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

# ---------------------------------------------------------------------------
# Collect Streamlit — it has many dynamic imports and data files that
# PyInstaller cannot detect statically. collect_all handles this.
# ---------------------------------------------------------------------------
streamlit_datas, streamlit_binaries, streamlit_hiddenimports = collect_all("streamlit")

# ---------------------------------------------------------------------------
# Pydantic v2 uses Rust extensions; collect_all brings them in.
# ---------------------------------------------------------------------------
pydantic_datas, pydantic_binaries, pydantic_hiddenimports = collect_all("pydantic")

# ---------------------------------------------------------------------------
# altair / vega_datasets are pulled in by Streamlit.
# ---------------------------------------------------------------------------
altair_datas, altair_binaries, altair_hiddenimports = collect_all("altair")

# Root of the repository (one level above this spec file).
REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[REPO_ROOT],
    binaries=[
        *streamlit_binaries,
        *pydantic_binaries,
        *altair_binaries,
    ],
    datas=[
        # office-agent package source (schemas, templates, .streamlit config)
        (os.path.join(REPO_ROOT, "office_agent"), "office_agent"),
        (os.path.join(REPO_ROOT, "templates"), "templates"),
        (os.path.join(REPO_ROOT, ".streamlit"), ".streamlit"),
        # Collected framework data files
        *streamlit_datas,
        *pydantic_datas,
        *altair_datas,
    ],
    hiddenimports=[
        # office-agent modules (dynamic imports via factory pattern)
        "office_agent.llm.llamacpp",
        "office_agent.llm.ollama",
        "office_agent.llm.mock",
        "office_agent.tools.docx_tool",
        "office_agent.tools.xlsx_tool",
        "office_agent.tools.pptx_tool",
        "office_agent.tools.vba_tool",
        "office_agent.tools.file_tool",
        "office_agent.agent.core",
        "office_agent.agent.prompt",
        "office_agent.agent.validator",
        "office_agent.update.verifier",
        "office_agent.update.applier",
        # jsonschema validators loaded dynamically
        "jsonschema.validators",
        "jsonschema._format",
        "jsonschema._keywords",
        "jsonschema._legacy_keywords",
        # requests extras
        "requests.packages.urllib3",
        "requests.packages.urllib3.contrib",
        # Collected framework hidden imports
        *streamlit_hiddenimports,
        *pydantic_hiddenimports,
        *altair_hiddenimports,
    ],
    excludes=[
        # Dev/test tools — not needed at runtime
        "pytest",
        "pytest_cov",
        "ruff",
        "mypy",
        "IPython",
        "jupyter",
        "notebook",
        "black",
        "isort",
        # Large scientific packages not used by office-agent
        "scipy",
        "sklearn",
        "matplotlib",
        "PIL",
        "cv2",
        "tensorflow",
        "torch",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # --onedir: binaries go into COLLECT, not the exe
    name="OfficeAgentBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX can trigger AV false positives; leave off
    console=False,             # No console window — launcher manages output
    disable_windowed_traceback=False,
    target_arch="x86_64",
    codesign_identity=None,    # Code signing done separately via sign.ps1
    entitlements_file=None,
    # icon="assets/icon.ico",  # Uncomment when icon asset is available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="app",                # Output directory: build/dist/app/
)

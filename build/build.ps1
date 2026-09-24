# build.ps1
#
# Master build script for OfficeAgent (Windows x64).
#
# Prerequisites (must be installed on the build machine):
#   - Python 3.11+ x64 (with pip)
#   - .NET 8 SDK
#   - PyInstaller  (installed automatically into the venv by this script)
#   - 7-Zip (7z.exe on PATH) — for Phase 1 ZIP assembly
#   - Inno Setup 6 (iscc.exe on PATH) — for Phase 2 installer
#
# The whole package is x64 (win-x64 launcher, cpu-x64 llama.cpp runtime), so the
# Python backend must be built with an x64 interpreter too. On Windows ARM the
# `python` on PATH is usually ARM64; use -PythonExe to pick an x64 one.
#
# Usage:
#   .\build.ps1                         # Phase 1 ZIP build (Standard model)
#   .\build.ps1 -Phase 2                # Phase 2 Inno Setup installer
#   .\build.ps1 -Tier pro               # Pro tier
#   .\build.ps1 -ModelCacheDir D:\models -LlmCacheDir D:\llm-cache
#   .\build.ps1 -PythonExe "py -3.12-64"                  # pick an x64 interpreter
#   .\build.ps1 -PythonExe "C:\Python312\python.exe"      # ... or its full path
#
# Output:
#   Phase 1: artifacts\OfficeAgent-v<ver>-Standard-Windows.zip
#   Phase 2: artifacts\OfficeAgent-Setup-v<ver>-Standard.exe

param(
    [ValidateSet("1","2")]
    [string]$Phase = "1",

    [ValidateSet("standard","pro")]
    [string]$Tier = "standard",

    # Path to directory containing pre-downloaded .gguf model files.
    # File must be named: standard.gguf or pro.gguf
    [string]$ModelCacheDir = "",

    # Path to directory containing pre-downloaded llama-server binaries.
    # Pass to fetch_llm.ps1 as -CacheDir (air-gap mode).
    [string]$LlmCacheDir = "",

    # Skip code signing (development builds).
    [switch]$NoSign,

    # Skip PyInstaller (reuse existing build\dist\app\ output).
    [switch]$SkipPyInstaller,

    # Skip C# launcher build (reuse existing output).
    [switch]$SkipLauncher,

    # Interpreter used to create the PyInstaller build venv.
    # Accepts either a full path to python.exe (spaces are fine) or a command
    # line such as "py -3.12-64". Empty = use `python` from PATH (default).
    [string]$PythonExe = "",

    [string]$Version = "1.0.0"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$BuildDir   = Join-Path $RepoRoot "build"
$DistDir    = Join-Path $BuildDir "dist"
$WorkDir    = Join-Path $BuildDir "work"
$ArtifactsDir = Join-Path $RepoRoot "artifacts"

$VenvDir    = Join-Path $BuildDir "venv"
$Python     = Join-Path $VenvDir "Scripts\python.exe"
$Pip        = Join-Path $VenvDir "Scripts\pip.exe"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host ">>> $msg" -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------
# Interpreter selection helpers
# ---------------------------------------------------------------------------
function Resolve-PythonCommand {
    # Turns the -PythonExe value into a command plus its arguments.
    param([string]$Spec)

    if ($Spec -eq "") {
        return @{ Command = "python"; Arguments = @() }
    }

    # An existing file is used verbatim, so paths containing spaces still work.
    if (Test-Path -LiteralPath $Spec -PathType Leaf) {
        return @{ Command = $Spec; Arguments = @() }
    }

    # Otherwise treat the value as a command line, e.g. "py -3.12-64".
    $parts = @($Spec -split '\s+' | Where-Object { $_ -ne "" })
    if ($parts.Count -eq 0) {
        throw "-PythonExe contains no command: '$Spec'"
    }
    $arguments = @()
    if ($parts.Count -gt 1) { $arguments = @($parts[1..($parts.Count - 1)]) }
    return @{ Command = $parts[0]; Arguments = $arguments }
}

function Invoke-PythonScript {
    # Runs a short Python script from a temp file. Windows PowerShell does not
    # reliably escape double quotes when passing arguments to native commands,
    # so `python -c "<script>"` is not safe for anything but trivial snippets.
    param([string]$Command, [string[]]$Arguments, [string]$Body)

    $scriptFile = Join-Path $env:TEMP ("oa-build-probe-{0}.py" -f (Get-Random))
    try {
        Set-Content -LiteralPath $scriptFile -Value $Body -Encoding UTF8
        & $Command @Arguments $scriptFile
    } finally {
        Remove-Item -LiteralPath $scriptFile -Force -ErrorAction SilentlyContinue
    }
}

# Prints "<version>|<machine>|<pointer bits>" for the interpreter running it.
$InterpreterProbe = @'
import platform
import struct
print(platform.python_version() + "|" + platform.machine() + "|" + str(struct.calcsize("P") * 8))
'@

function Get-InterpreterInfo {
    # Runs the probe and returns @{ Version; Machine; Bits }.
    param([string]$Command, [string[]]$Arguments, [string]$Label)

    try {
        $output = Invoke-PythonScript -Command $Command -Arguments $Arguments -Body $InterpreterProbe
    } catch {
        throw "Could not run the Python interpreter '$Label': $($_.Exception.Message)"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "The Python interpreter '$Label' exited with code $LASTEXITCODE."
    }

    $fields = @(($output | Select-Object -Last 1) -split '\|')
    if ($fields.Count -lt 3) {
        throw "Unexpected output while probing '$Label': $output"
    }
    return @{ Version = $fields[0]; Machine = $fields[1]; Bits = $fields[2] }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor White
Write-Host "  OfficeAgent Build Script" -ForegroundColor White
Write-Host "  Phase: $Phase  |  Tier: $Tier  |  Version: $Version" -ForegroundColor White
Write-Host "============================================" -ForegroundColor White

# ---------------------------------------------------------------------------
# Step 1: Python virtual environment
# ---------------------------------------------------------------------------
Write-Step "1. Python virtual environment"

$resolved       = Resolve-PythonCommand $PythonExe
$PyCmd          = $resolved.Command
$PyArgs         = $resolved.Arguments
$PythonDisplay  = (@($PyCmd) + $PyArgs) -join " "

$hostPython = Get-InterpreterInfo -Command $PyCmd -Arguments $PyArgs -Label $PythonDisplay
Write-Host "  Interpreter: $PythonDisplay"
Write-Host "  Version: $($hostPython.Version)  |  Arch: $($hostPython.Machine) ($($hostPython.Bits)-bit)"

# The launcher and the llama.cpp runtime shipped in this package are x64, and
# pyarrow (pulled in by Streamlit) publishes no Windows ARM64 wheels, so pip
# would try to build it from source. Warn rather than fail: a non-AMD64 build
# may still be intentional.
if ($hostPython.Machine -ne "AMD64") {
    Write-Warning "  Build interpreter architecture is $($hostPython.Machine), not AMD64 (x64)."
    Write-Warning "  The launcher and llama.cpp runtime in this package are x64, and pyarrow has"
    Write-Warning "  no Windows ARM64 wheels. Select an x64 interpreter, for example:"
    Write-Warning "    .\build.ps1 -PythonExe `"py -3.12-64`""
}

if (-not (Test-Path $VenvDir)) {
    Write-Host "  Creating venv..."
    & $PyCmd @PyArgs -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Creating the build venv with '$PythonDisplay' failed." }
} else {
    Write-Host "  Reusing existing venv."
    $venvPython = Get-InterpreterInfo -Command $Python -Arguments @() -Label $Python
    Write-Host "  Venv Python: $($venvPython.Version)  |  Arch: $($venvPython.Machine) ($($venvPython.Bits)-bit)"

    # An existing venv built by a different interpreter would silently win over
    # an explicit -PythonExe, reproducing the very failure it was passed to fix.
    if ($PythonExe -ne "" -and $venvPython.Machine -ne $hostPython.Machine) {
        throw ("The existing build venv does not match -PythonExe.`n" +
               "  Existing venv: $($venvPython.Version) $($venvPython.Machine)`n" +
               "  Requested:     $($hostPython.Version) $($hostPython.Machine)  ($PythonDisplay)`n" +
               "Delete the venv and re-run:`n" +
               "  Remove-Item -Recurse -Force `"$VenvDir`"")
    }
}

Write-Host "  Installing / upgrading dependencies..."
& $Pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip self-upgrade failed." }

& $Pip install --quiet --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed." }

& $Pip install --quiet -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed." }

# The frozen application runs the Streamlit GUI, so the build environment needs
# the GUI dependencies too. Without them PyInstaller bundles no Streamlit and
# the packaged executable fails at start-up with ModuleNotFoundError.
& $Pip install --quiet -r (Join-Path $RepoRoot "requirements-gui.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements-gui.txt failed." }

# Verify the venv actually holds everything the bundle needs, before spending
# minutes in PyInstaller only to fail there.
Write-Host "  Verifying build environment..."

$DependencyProbe = @'
import importlib.util

REQUIRED = [
    ("PyInstaller", "pip install pyinstaller"),
    ("click",       "requirements.txt"),
    ("docx",        "requirements.txt"),
    ("openpyxl",    "requirements.txt"),
    ("pptx",        "requirements.txt"),
    ("jsonschema",  "requirements.txt"),
    ("requests",    "requirements.txt"),
    ("pydantic",    "requirements.txt"),
    ("streamlit",   "requirements-gui.txt"),
    ("altair",      "requirements-gui.txt"),
]

missing = [(name, source) for name, source in REQUIRED if importlib.util.find_spec(name) is None]
if missing:
    print("Missing package(s) in the build venv:")
    for name, source in missing:
        print("  {0}  (from {1})".format(name, source))
    raise SystemExit(1)

print("  All required packages are present.")
'@

Invoke-PythonScript -Command $Python -Arguments @() -Body $DependencyProbe
if ($LASTEXITCODE -ne 0) {
    throw ("The build venv is incomplete — see the missing packages above.`n" +
           "On Windows ARM, pyarrow (a Streamlit dependency) has no wheel and pip tries to`n" +
           "compile it. Build with an x64 interpreter instead:`n" +
           "  Remove-Item -Recurse -Force `"$VenvDir`"`n" +
           "  .\build.ps1 -PythonExe `"py -3.12-64`"")
}

# ---------------------------------------------------------------------------
# Step 2: PyInstaller
# ---------------------------------------------------------------------------
Write-Step "2. PyInstaller bundle"

if ($SkipPyInstaller) {
    Write-Host "  Skipped (-SkipPyInstaller)."
} else {
    $SpecFile = Join-Path $RepoRoot "pyinstaller\office_agent.spec"
    & $Python -m PyInstaller $SpecFile `
        --distpath $DistDir `
        --workpath $WorkDir `
        --noconfirm

    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    Write-Host "  Output: $DistDir\app\" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Step 3: llama-server binaries
# ---------------------------------------------------------------------------
Write-Step "3. llama-server binaries"

$FetchArgs = @{ OutDir = "build\dist\llm" }
if ($LlmCacheDir -ne "") { $FetchArgs["CacheDir"] = $LlmCacheDir }

& (Join-Path $BuildDir "fetch_llm.ps1") @FetchArgs
if ($LASTEXITCODE -ne 0) { throw "fetch_llm.ps1 failed." }

# ---------------------------------------------------------------------------
# Step 4: Model files
# ---------------------------------------------------------------------------
Write-Step "4. Model files"

$ModelsOutDir = Join-Path $DistDir "models"
New-Item -ItemType Directory -Force -Path $ModelsOutDir | Out-Null

$ModelFile = if ($Tier -eq "pro") { "pro.gguf" } else { "standard.gguf" }

if ($ModelCacheDir -ne "") {
    $src = Join-Path $ModelCacheDir $ModelFile
    if (-not (Test-Path $src)) {
        throw "Model file not found in cache: $src"
    }
    Write-Host "  Copying $ModelFile from cache..."
    Copy-Item -Path $src -Destination (Join-Path $ModelsOutDir $ModelFile) -Force
} else {
    Write-Warning "  -ModelCacheDir not specified. Models directory will be empty."
    Write-Warning "  Add the .gguf file manually to: $ModelsOutDir"
}

# ---------------------------------------------------------------------------
# Step 5: C# launcher
# ---------------------------------------------------------------------------
Write-Step "5. C# launcher"

if ($SkipLauncher) {
    Write-Host "  Skipped (-SkipLauncher)."
} else {
    $LauncherProj = Join-Path $RepoRoot "launcher\Phase1\OfficeAgentLauncher.csproj"
    $LauncherOut  = Join-Path $BuildDir "launcher-publish"

    dotnet publish $LauncherProj `
        --configuration Release `
        --runtime win-x64 `
        --self-contained true `
        --output $LauncherOut `
        -p:Version=$Version

    if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed." }

    Copy-Item -Path (Join-Path $LauncherOut "OfficeAgent.exe") `
              -Destination $DistDir -Force
    Write-Host "  Launcher: $DistDir\OfficeAgent.exe" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Step 6: Config and placeholder directories
# ---------------------------------------------------------------------------
Write-Step "6. Config and directories"

$ConfigSrc = Join-Path $RepoRoot "dist\config\settings.ini"
$ConfigDst = Join-Path $DistDir "config"
New-Item -ItemType Directory -Force -Path $ConfigDst | Out-Null

if (Test-Path $ConfigSrc) {
    Write-Host "  Copying settings.ini from $ConfigSrc"
    Copy-Item -Path $ConfigSrc -Destination $ConfigDst -Force
} else {
    Write-Host "  $ConfigSrc not found — generating default settings.ini"
    $DefaultSettingsIni = @'
; OfficeAgent configuration file
; Managed by IT administrators — end users do not need to edit this file.
; Changes take effect on next application start.
;
; Path: <install_dir>\config\settings.ini

[app]
; Application version — do not modify manually.
version = 1.0.0

; Model tier: standard | pro
; standard requires 8 GB RAM, pro requires 16 GB RAM.
tier = standard

[llm]
; Port for the llama-server process (localhost only).
; Change only if 8080 conflicts with another service.
port = 8080

; Context window in tokens.
; standard: 4096, pro: 8192
context_size = 4096

; Number of CPU threads for inference.
; 0 = auto-detect (uses half of logical CPU count as an estimate of physical cores).
; Set explicitly if auto-detection is incorrect for your hardware.
threads = 0

; GPU acceleration: true | false
; Requires a compatible NVIDIA GPU and the CUDA-enabled llama-server binary.
; Leave false for CPU-only environments.
gpu = false

[server]
; Port for the Streamlit web server (localhost only).
; Change only if 8501 conflicts with another service.
port = 8501

[paths]
; Directory where generated Office documents are saved.
; Leave blank to use the current user's Documents\OfficeAgent\ folder.
output_dir =

; Relative paths to model files from the install directory.
; Do not change unless models have been moved.
model_standard = models\standard.gguf
model_pro = models\pro.gguf

[security]
; Number of days to retain audit log files before automatic deletion.
log_retention_days = 90

; Verify SHA256 checksums of critical files on every startup.
; Set to false only if advised by your IT administrator.
integrity_check = true
'@
    Set-Content -Path (Join-Path $ConfigDst "settings.ini") -Value $DefaultSettingsIni -Encoding UTF8
}

# Placeholder output and logs directories (shipped empty in the ZIP).
New-Item -ItemType Directory -Force -Path (Join-Path $DistDir "output") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DistDir "logs")   | Out-Null

# Placeholder license file (no enforcement in Phase 1).
$LicenseDst = Join-Path $DistDir "license.key"
if (-not (Test-Path $LicenseDst)) {
    '{"schema_version":1,"license_type":"evaluation","tier":"standard","valid_until":"2099-12-31","hardware_id":"SITE_LICENSE","signature":"UNSIGNED"}' |
        Set-Content -Path $LicenseDst -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Step 7: Generate checksums
# ---------------------------------------------------------------------------
Write-Step "7. SHA256 checksums"

$ChecksumFile = Join-Path $DistDir "checksums.sha256"
$entries = @()

Get-ChildItem -Path $DistDir -Recurse -File |
    Where-Object { $_.Extension -in ".exe",".gguf",".dll" } |
    ForEach-Object {
        $hash = (Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLowerInvariant()
        $rel  = $_.FullName.Substring($DistDir.Length + 1)
        $entries += "$hash  $rel"
    }

$entries | Set-Content -Path $ChecksumFile -Encoding UTF8
Write-Host "  Checksums written: $ChecksumFile"

# ---------------------------------------------------------------------------
# Step 8: Code signing (Phase 2 and non-dev builds)
# ---------------------------------------------------------------------------
Write-Step "8. Code signing"

if ($NoSign) {
    Write-Host "  Skipped (-NoSign)."
} else {
    $SignScript = Join-Path $BuildDir "sign.ps1"
    if (Test-Path $SignScript) {
        & $SignScript -TargetDir $DistDir
        if ($LASTEXITCODE -ne 0) { throw "Code signing failed." }
    } else {
        Write-Warning "  sign.ps1 not found — skipping code signing."
        Write-Warning "  For production builds, configure sign.ps1 with your EV certificate."
    }
}

# ---------------------------------------------------------------------------
# Step 9: Package
# ---------------------------------------------------------------------------
Write-Step "9. Package"

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

$TierLabel = $Tier.Substring(0,1).ToUpper() + $Tier.Substring(1)
$ArtifactBaseName = "OfficeAgent-v$Version-$TierLabel-Windows"

if ($Phase -eq "1") {
    # Phase 1: ZIP
    $ZipPath = Join-Path $ArtifactsDir "$ArtifactBaseName.zip"

    Write-Host "  Assembling ZIP: $ZipPath"

    # 7-Zip produces faster and smaller output than Compress-Archive for large files.
    if (Get-Command "7z" -ErrorAction SilentlyContinue) {
        $inner = Join-Path $env:TEMP "OfficeAgent-zip-$(Get-Random)"
        New-Item -ItemType Directory -Force -Path $inner | Out-Null
        Copy-Item -Path $DistDir -Destination (Join-Path $inner "OfficeAgent") -Recurse -Force
        & 7z a -tzip -mx=5 $ZipPath (Join-Path $inner "OfficeAgent\*")
        Remove-Item -Recurse -Force $inner
    } else {
        Write-Warning "  7z not found — falling back to Compress-Archive (slower for large files)."
        Compress-Archive -Path "$DistDir\*" -DestinationPath $ZipPath -Force
    }

    Write-Host ""
    Write-Host "Build complete!" -ForegroundColor Green
    Write-Host "  Artifact: $ZipPath" -ForegroundColor Green

} elseif ($Phase -eq "2") {
    # Phase 2: Inno Setup
    $IssScript = Join-Path $RepoRoot "installer\setup.iss"

    if (-not (Get-Command "iscc" -ErrorAction SilentlyContinue)) {
        throw "iscc (Inno Setup Compiler) not found on PATH. Install Inno Setup 6."
    }

    Write-Host "  Running Inno Setup..."
    & iscc $IssScript `
        /DMyAppVersion=$Version `
        /DMyTier=$Tier `
        /DDistDir=$DistDir `
        /DOutputDir=$ArtifactsDir `
        /DOutputBaseName=$ArtifactBaseName

    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }

    Write-Host ""
    Write-Host "Build complete!" -ForegroundColor Green
    Write-Host "  Artifact: $ArtifactsDir\$ArtifactBaseName.exe" -ForegroundColor Green
}

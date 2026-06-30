# build.ps1
#
# Master build script for OfficeAgent (Windows x64).
#
# Prerequisites (must be installed on the build machine):
#   - Python 3.11+ (with pip)
#   - .NET 8 SDK
#   - PyInstaller  (installed automatically into the venv by this script)
#   - 7-Zip (7z.exe on PATH) — for Phase 1 ZIP assembly
#   - Inno Setup 6 (iscc.exe on PATH) — for Phase 2 installer
#
# Usage:
#   .\build.ps1                         # Phase 1 ZIP build (Standard model)
#   .\build.ps1 -Phase 2                # Phase 2 Inno Setup installer
#   .\build.ps1 -Tier pro               # Pro tier
#   .\build.ps1 -ModelCacheDir D:\models -LlmCacheDir D:\llm-cache
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

Write-Host ""
Write-Host "============================================" -ForegroundColor White
Write-Host "  OfficeAgent Build Script" -ForegroundColor White
Write-Host "  Phase: $Phase  |  Tier: $Tier  |  Version: $Version" -ForegroundColor White
Write-Host "============================================" -ForegroundColor White

# ---------------------------------------------------------------------------
# Step 1: Python virtual environment
# ---------------------------------------------------------------------------
Write-Step "1. Python virtual environment"

if (-not (Test-Path $VenvDir)) {
    Write-Host "  Creating venv..."
    python -m venv $VenvDir
} else {
    Write-Host "  Reusing existing venv."
}

Write-Host "  Installing / upgrading dependencies..."
& $Pip install --quiet --upgrade pip
& $Pip install --quiet --upgrade pyinstaller
& $Pip install --quiet -r (Join-Path $RepoRoot "requirements.txt")

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
Copy-Item -Path $ConfigSrc -Destination $ConfigDst -Force

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

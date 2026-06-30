# fetch_llm.ps1
#
# Downloads (or copies from a local cache) the llama-server Windows binaries
# and places them into build\dist\llm\.
#
# Usage:
#   .\fetch_llm.ps1                          # Download from GitHub (internet required)
#   .\fetch_llm.ps1 -CacheDir D:\llm-cache   # Copy from a pre-downloaded vendor cache
#                                            # (use this for air-gap build environments)
#
# The -CacheDir mode is the recommended path for production builds.
# The download mode is provided for development convenience only.

param(
    [string]$CacheDir = "",          # If set, copy from here instead of downloading
    [string]$OutDir   = "build\dist\llm",
    [switch]$SkipVerify              # Skip SHA256 verification (not recommended)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Pinned llama.cpp release and binary names
#
# To upgrade: update the tag and SHA256 hashes below.
# Download the corresponding release from:
#   https://github.com/ggerganov/llama.cpp/releases/tag/<LLAMA_TAG>
# ---------------------------------------------------------------------------
$LLAMA_TAG = "b3576"

$Binaries = @(
    @{
        Variant  = "avx2"
        ZipName  = "llama-$LLAMA_TAG-bin-win-avx2-x64.zip"
        ExeInZip = "llama-server.exe"
        OutName  = "llama-server-avx2.exe"
        Sha256   = "PLACEHOLDER_AVX2_SHA256"   # Replace with actual hash after download
    },
    @{
        Variant  = "avx512"
        ZipName  = "llama-$LLAMA_TAG-bin-win-avx512-x64.zip"
        ExeInZip = "llama-server.exe"
        OutName  = "llama-server-avx512.exe"
        Sha256   = "PLACEHOLDER_AVX512_SHA256"
    },
    @{
        Variant  = "noavx"
        ZipName  = "llama-$LLAMA_TAG-bin-win-noavx-x64.zip"
        ExeInZip = "llama-server.exe"
        OutName  = "llama-server-noavx.exe"
        Sha256   = "PLACEHOLDER_NOAVX_SHA256"
    }
)

$GithubBase = "https://github.com/ggerganov/llama.cpp/releases/download/$LLAMA_TAG"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Verify-Sha256 {
    param([string]$FilePath, [string]$Expected)
    if ($Expected -like "PLACEHOLDER*") {
        Write-Warning "SHA256 hash is a placeholder for $FilePath — skipping verification."
        Write-Warning "Replace PLACEHOLDER values in fetch_llm.ps1 with actual hashes before production use."
        return
    }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $FilePath).Hash.ToUpperInvariant()
    $exp    = $Expected.ToUpperInvariant()
    if ($actual -ne $exp) {
        throw "SHA256 mismatch for $FilePath`n  Expected: $exp`n  Actual:   $actual"
    }
    Write-Host "  SHA256 OK: $FilePath"
}

function Get-BinaryFromCache {
    param([hashtable]$Binary, [string]$CacheDir, [string]$OutDir)
    $src = Join-Path $CacheDir $Binary.OutName
    if (-not (Test-Path $src)) {
        throw "Cache file not found: $src`nExpected pre-downloaded binary at this path."
    }
    $dst = Join-Path $OutDir $Binary.OutName
    Copy-Item -Path $src -Destination $dst -Force
    Write-Host "  Copied: $($Binary.OutName)"
    if (-not $SkipVerify) { Verify-Sha256 $dst $Binary.Sha256 }
}

function Get-BinaryFromGitHub {
    param([hashtable]$Binary, [string]$TempDir, [string]$OutDir)
    $zipUrl  = "$GithubBase/$($Binary.ZipName)"
    $zipPath = Join-Path $TempDir $Binary.ZipName

    Write-Host "  Downloading: $($Binary.ZipName)"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

    Write-Host "  Extracting..."
    $extractDir = Join-Path $TempDir "extract_$($Binary.Variant)"
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    # Find the exe inside the extracted archive (may be in a subdirectory).
    $exeFound = Get-ChildItem -Path $extractDir -Recurse -Filter $Binary.ExeInZip |
                Select-Object -First 1
    if (-not $exeFound) {
        throw "Could not find $($Binary.ExeInZip) inside $($Binary.ZipName)"
    }

    $dst = Join-Path $OutDir $Binary.OutName
    Copy-Item -Path $exeFound.FullName -Destination $dst -Force
    Write-Host "  Extracted to: $dst"
    if (-not $SkipVerify) { Verify-Sha256 $dst $Binary.Sha256 }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== fetch_llm.ps1 — llama.cpp binary setup ===" -ForegroundColor Cyan
Write-Host "Tag: $LLAMA_TAG"
Write-Host "Output: $OutDir"
Write-Host ""

# Resolve OutDir relative to the repo root (one level above build/).
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Split-Path -Parent $scriptDir
$OutDirAbs = Join-Path $repoRoot $OutDir

New-Item -ItemType Directory -Force -Path $OutDirAbs | Out-Null

if ($CacheDir -ne "") {
    # Air-gap mode: copy from vendor cache directory.
    Write-Host "Mode: AIR-GAP (copying from cache: $CacheDir)" -ForegroundColor Yellow
    foreach ($bin in $Binaries) {
        Write-Host "Processing $($bin.Variant)..."
        Get-BinaryFromCache $bin $CacheDir $OutDirAbs
    }
} else {
    # Online mode: download from GitHub (development builds only).
    Write-Host "Mode: ONLINE (downloading from GitHub)" -ForegroundColor Yellow
    Write-Warning "Online download is for development only. Use -CacheDir for production air-gap builds."

    $tempDir = Join-Path $env:TEMP "oa-llm-fetch-$(Get-Random)"
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

    try {
        foreach ($bin in $Binaries) {
            Write-Host "Processing $($bin.Variant)..."
            Get-BinaryFromGitHub $bin $tempDir $OutDirAbs
        }
    } finally {
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "Done. Binaries written to: $OutDirAbs" -ForegroundColor Green

# fetch_llm.ps1
#
# Downloads (or copies from a local cache) the llama-server Windows runtime
# and places it into build\dist\llm\.
#
# The runtime is llama-server.exe PLUS its DLLs. Current llama.cpp Windows
# releases are dynamically linked: llama-server.exe is a ~9 KB front-end and
# all inference code lives in llama.dll / ggml*.dll. Shipping the exe alone
# produces a process that dies at load time with exit code 0xC0000135
# (STATUS_DLL_NOT_FOUND, reported as -1073741515) and prints nothing.
#
# Usage:
#   .\fetch_llm.ps1                          # Download from GitHub (internet required)
#   .\fetch_llm.ps1 -CacheDir D:\llm-cache   # Copy from a pre-downloaded vendor cache
#                                            # (use this for air-gap build environments)
#
# The -CacheDir mode is the recommended path for production builds.
# For that mode, place the untouched release ZIP in the cache directory so the
# runtime cannot be partially copied and so SHA256 verification stays possible.
# The download mode is provided for development convenience only.

param(
    [string]$CacheDir  = "",          # If set, copy from here instead of downloading
    [string]$OutDir    = "build\dist\llm",
    [string]$LlamaTag  = "b9848",     # Override to pin a specific llama.cpp release
    [switch]$SkipVerify               # Skip SHA256 verification (not recommended)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Pinned llama.cpp release and binary names
#
# To upgrade: pass -LlamaTag <tag> or update the $LlamaTag default above.
# Asset naming changed in newer releases — current format: llama-bXXXX-bin-win-cpu-x64.zip
# Browse releases at: https://github.com/ggerganov/llama.cpp/releases
# ---------------------------------------------------------------------------
$LLAMA_TAG = $LlamaTag

$Binaries = @(
    @{
        Variant  = "cpu-x64"
        ZipName  = "llama-$LLAMA_TAG-bin-win-cpu-x64.zip"
        ExeInZip = "llama-server.exe"
        OutName  = "llama-server.exe"
        # SHA256 of the release ZIP — not of the extracted exe. One hash over
        # the archive covers the exe and every runtime DLL together.
        # Replace with the actual hash after downloading (see llm_checksums.txt).
        Sha256   = "PLACEHOLDER_CPU_X64_SHA256"
    }
)

$GithubBase = "https://github.com/ggerganov/llama.cpp/releases/download/$LLAMA_TAG"

# Runtime files copied from the release bin directory alongside llama-server.exe.
# *.dll covers llama.dll, ggml.dll, ggml-base.dll, ggml-cpu.dll, mtmd.dll and
# the ggml-cpu-*.dll CPU backends that ggml.dll loads at run time to pick the
# AVX/AVX2/AVX-512 code path. Other executables, *.pdb, *.lib and headers from
# the archive are deliberately not copied.
$RuntimePatterns = @("*.dll", "*.manifest")

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

function Copy-LlamaRuntime {
    # Copies llama-server.exe and every runtime file sitting next to it.
    param(
        [string]$BinDir,    # Directory that holds llama-server.exe and its DLLs
        [string]$ExeName,   # Source exe file name inside $BinDir
        [string]$OutName,   # Destination exe file name inside $OutDir
        [string]$OutDir
    )

    $exeSrc = Join-Path $BinDir $ExeName
    if (-not (Test-Path $exeSrc)) {
        throw "$ExeName not found in: $BinDir"
    }

    Copy-Item -Path $exeSrc -Destination (Join-Path $OutDir $OutName) -Force
    Write-Host "  Copied: $OutName"

    $dllCount   = 0
    $otherCount = 0
    foreach ($pattern in $RuntimePatterns) {
        $files = @(Get-ChildItem -Path $BinDir -Filter $pattern -File -ErrorAction SilentlyContinue)
        foreach ($f in $files) {
            Copy-Item -Path $f.FullName -Destination (Join-Path $OutDir $f.Name) -Force
            if ($f.Extension -eq ".dll") { $dllCount++ } else { $otherCount++ }
        }
    }

    # Fail fast. Without its DLLs the exe still packages and ships fine, and
    # only fails at the customer site with a silent 0xC0000135 exit, so the
    # build must refuse to continue here.
    if ($dllCount -eq 0) {
        throw "No runtime DLLs found next to $ExeName in: $BinDir`nllama-server.exe cannot start without them (exit code 0xC0000135)."
    }

    Write-Host "  Copied: $dllCount DLL(s), $otherCount other runtime file(s)"
}

function Expand-LlamaRuntimeZip {
    # Verifies a release ZIP, extracts it and copies the runtime out of it.
    param([string]$ZipPath, [hashtable]$Binary, [string]$ExtractDir, [string]$OutDir)

    if (-not $SkipVerify) { Verify-Sha256 $ZipPath $Binary.Sha256 }

    Write-Host "  Extracting..."
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

    # The archive layout has changed across llama.cpp releases (files at the
    # archive root vs. nested under build\bin\), so locate the exe first and
    # treat whatever directory holds it as the runtime bin directory.
    $exeFound = Get-ChildItem -Path $ExtractDir -Recurse -Filter $Binary.ExeInZip -File |
                Select-Object -First 1
    if (-not $exeFound) {
        throw "Could not find $($Binary.ExeInZip) inside $ZipPath"
    }

    Copy-LlamaRuntime -BinDir  $exeFound.DirectoryName `
                      -ExeName $Binary.ExeInZip `
                      -OutName $Binary.OutName `
                      -OutDir  $OutDir
}

function Get-BinaryFromCache {
    param([hashtable]$Binary, [string]$CacheDir, [string]$OutDir)

    # Preferred: the untouched release ZIP placed in the cache by the vendor.
    # Nothing can be missed, and the SHA256 check still applies.
    $zipSrc = Join-Path $CacheDir $Binary.ZipName
    if (Test-Path $zipSrc) {
        Write-Host "  Source: cached release archive $($Binary.ZipName)"
        $extractDir = Join-Path $env:TEMP "oa-llm-cache-$(Get-Random)"
        try {
            Expand-LlamaRuntimeZip -ZipPath    $zipSrc `
                                   -Binary     $Binary `
                                   -ExtractDir $extractDir `
                                   -OutDir     $OutDir
        } finally {
            Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
        }
        return
    }

    # Fallback: a pre-extracted cache directory holding the exe and its DLLs.
    $exeSrc = Join-Path $CacheDir $Binary.OutName
    if (Test-Path $exeSrc) {
        Write-Host "  Source: pre-extracted cache directory"
        Write-Warning "SHA256 verification covers the release ZIP, so it is skipped for a pre-extracted cache."
        Write-Warning "Place $($Binary.ZipName) in $CacheDir to enable verification."
        Copy-LlamaRuntime -BinDir  $CacheDir `
                          -ExeName $Binary.OutName `
                          -OutName $Binary.OutName `
                          -OutDir  $OutDir
        return
    }

    throw "Cache file not found. Expected one of:`n  $zipSrc`n  $exeSrc"
}

function Get-BinaryFromGitHub {
    param([hashtable]$Binary, [string]$TempDir, [string]$OutDir)
    $zipUrl  = "$GithubBase/$($Binary.ZipName)"
    $zipPath = Join-Path $TempDir $Binary.ZipName

    Write-Host "  Downloading: $($Binary.ZipName)"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

    $extractDir = Join-Path $TempDir "extract_$($Binary.Variant)"
    Expand-LlamaRuntimeZip -ZipPath    $zipPath `
                           -Binary     $Binary `
                           -ExtractDir $extractDir `
                           -OutDir     $OutDir
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
Write-Host "Done. Runtime written to: $OutDirAbs" -ForegroundColor Green

# List what was produced so a missing DLL is visible in the build log.
Get-ChildItem -Path $OutDirAbs -File | Sort-Object Name | ForEach-Object {
    Write-Host ("  {0,-34} {1,12:N0} bytes" -f $_.Name, $_.Length)
}

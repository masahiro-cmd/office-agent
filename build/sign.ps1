# sign.ps1
#
# Code signing stub for OfficeAgent executables.
#
# Configure this file with your EV (Extended Validation) code signing
# certificate details before production builds.
#
# Prerequisites:
#   - EV code signing certificate installed in the Windows Certificate Store
#     (certificate provider: DigiCert, Sectigo, etc.)
#   - signtool.exe available (part of Windows SDK)
#
# Usage (called automatically by build.ps1):
#   .\sign.ps1 -TargetDir build\dist
#
# Usage (manual):
#   .\sign.ps1 -TargetDir path\to\dir -CertThumbprint "ABC123..."

param(
    [Parameter(Mandatory)]
    [string]$TargetDir,

    # Certificate thumbprint from Windows Certificate Store.
    # Find with: Get-ChildItem Cert:\CurrentUser\My | Select Thumbprint, Subject
    [string]$CertThumbprint = $env:OA_CERT_THUMBPRINT,

    # Timestamp server URL (use your CA's TSA endpoint).
    [string]$TimestampUrl = "http://timestamp.digicert.com",

    # Digest algorithm.
    [string]$Digest = "sha256"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($CertThumbprint)) {
    Write-Warning "OA_CERT_THUMBPRINT environment variable not set and -CertThumbprint not provided."
    Write-Warning "Skipping code signing. Set the thumbprint to enable signing."
    exit 0
}

# Find signtool.exe
$signTool = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
if (-not $signTool) {
    # Try common Windows SDK locations
    $candidates = @(
        "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe",
        "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $signTool = $c; break }
    }
}
if (-not $signTool) {
    throw "signtool.exe not found. Install Windows SDK."
}

# Find all executables to sign.
$executables = Get-ChildItem -Path $TargetDir -Recurse -Include "*.exe","*.dll" |
               Where-Object { $_.FullName -notlike "*\_internal\*" }  # Skip PyInstaller internals

Write-Host "Signing $($executables.Count) file(s) in $TargetDir..."

foreach ($exe in $executables) {
    Write-Host "  Signing: $($exe.Name)"
    & $signTool sign `
        /sha1 $CertThumbprint `
        /fd $Digest `
        /tr $TimestampUrl `
        /td $Digest `
        /d "OfficeAgent" `
        /du "https://example.com" `
        $exe.FullName

    if ($LASTEXITCODE -ne 0) {
        throw "signtool failed for: $($exe.FullName)"
    }
}

Write-Host "Code signing complete." -ForegroundColor Green

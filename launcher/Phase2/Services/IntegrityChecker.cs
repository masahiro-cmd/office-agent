using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace OfficeAgent.Wpf.Services;

public sealed record IntegrityResult(bool IsValid, string? FailedFile = null);

/// <summary>
/// Verifies SHA256 checksums of critical files against checksums.sha256.
///
/// checksums.sha256 format (one entry per line):
///   &lt;lowercase sha256 hex&gt;  &lt;relative path from install root&gt;
///
/// Only .exe and .gguf files are verified (DLLs inside _internal/ are skipped
/// to avoid excessive startup time; PyInstaller verifies its own archive).
/// </summary>
internal sealed class IntegrityChecker
{
    private readonly string _installRoot;
    private readonly Settings _cfg;

    public IntegrityChecker(string installRoot, Settings cfg)
    {
        _installRoot = installRoot;
        _cfg = cfg;
    }

    public IntegrityResult Verify()
    {
        string checksumFile = Path.Combine(_installRoot, "checksums.sha256");
        if (!File.Exists(checksumFile))
        {
            // No checksum file present — skip verification (dev / Phase 1 builds).
            return new IntegrityResult(IsValid: true);
        }

        var expected = ParseChecksumFile(checksumFile);

        foreach (var (relativePath, expectedHash) in expected)
        {
            // Only verify top-level .exe and .gguf files; skip _internal/ directory.
            if (relativePath.Contains("_internal")) continue;

            string fullPath = Path.Combine(_installRoot, relativePath);
            if (!File.Exists(fullPath))
                return new IntegrityResult(IsValid: false, FailedFile: relativePath + " (見つかりません)");

            string actualHash = ComputeSha256(fullPath);
            if (!string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
                return new IntegrityResult(IsValid: false, FailedFile: relativePath);
        }

        return new IntegrityResult(IsValid: true);
    }

    private static Dictionary<string, string> ParseChecksumFile(string path)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        foreach (string line in File.ReadLines(path, Encoding.UTF8))
        {
            string trimmed = line.Trim();
            if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith('#')) continue;

            // Format: "<hash>  <relative path>"  (two spaces as separator)
            int sep = trimmed.IndexOf("  ", StringComparison.Ordinal);
            if (sep < 0) continue;

            string hash     = trimmed[..sep].Trim();
            string filePath = trimmed[(sep + 2)..].Trim();

            if (!string.IsNullOrEmpty(hash) && !string.IsNullOrEmpty(filePath))
                result[filePath] = hash;
        }

        return result;
    }

    private static string ComputeSha256(string filePath)
    {
        using var stream = File.OpenRead(filePath);
        byte[] hash = SHA256.HashData(stream);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }
}

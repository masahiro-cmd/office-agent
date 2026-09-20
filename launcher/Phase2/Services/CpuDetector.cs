using System;
using System.IO;
using System.Runtime.Intrinsics.X86;

namespace OfficeAgent.Wpf.Services;

/// <summary>
/// Detects CPU SIMD capabilities and returns the appropriate llama-server binary path.
/// </summary>
internal static class CpuDetector
{
    /// <summary>
    /// Returns the absolute path to the best available llama-server binary
    /// for the current CPU. Prefers the unified cpu-x64 binary, which picks
    /// its own AVX code path at run time; falls back to the per-variant
    /// binaries shipped by older packages.
    /// </summary>
    public static string SelectBinary(string installRoot)
    {
        string llmDir = Path.Combine(installRoot, "llm");

        string unifiedPath = Path.Combine(llmDir, "llama-server.exe");
        if (File.Exists(unifiedPath)) return unifiedPath;

        if (Avx512F.IsSupported)
        {
            string path = Path.Combine(llmDir, "llama-server-avx512.exe");
            if (File.Exists(path)) return path;
        }

        if (Avx2.IsSupported)
        {
            string path = Path.Combine(llmDir, "llama-server-avx2.exe");
            if (File.Exists(path)) return path;
        }

        return Path.Combine(llmDir, "llama-server-noavx.exe");
    }

    /// <summary>
    /// Returns a human-readable string describing the detected CPU capability tier.
    /// </summary>
    public static string DescribeCapability()
    {
        if (Avx512F.IsSupported) return "AVX-512";
        if (Avx2.IsSupported)    return "AVX2";
        return "No AVX";
    }
}

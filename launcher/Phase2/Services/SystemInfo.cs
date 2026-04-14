using System;
using System.Runtime.InteropServices;

namespace OfficeAgent.Wpf.Services;

/// <summary>System information helpers (RAM, CPU).</summary>
internal static class SystemInfo
{
    [StructLayout(LayoutKind.Sequential)]
    private struct MEMORYSTATUSEX
    {
        public uint  dwLength;
        public uint  dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;
    }

    [DllImport("kernel32.dll")]
    private static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX lpBuffer);

    /// <summary>Returns total installed physical RAM in GB, or 0 if unavailable.</summary>
    public static long GetTotalRamGb()
    {
        try
        {
            var mem = new MEMORYSTATUSEX
            {
                dwLength = (uint)Marshal.SizeOf<MEMORYSTATUSEX>()
            };
            if (GlobalMemoryStatusEx(ref mem))
                return (long)(mem.ullTotalPhys / (1024UL * 1024 * 1024));
        }
        catch { /* Unavailable in some virtualised or non-Windows environments */ }
        return 0;
    }
}

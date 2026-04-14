// OfficeAgent Phase 1 — Console Launcher
//
// Responsibilities:
//   1. Read config/settings.ini
//   2. Verify model file is present
//   3. Detect CPU capabilities → select correct llama-server binary
//   4. Spawn llama-server.exe and OfficeAgentBackend.exe as hidden subprocesses
//   5. Poll health endpoints until both services are ready
//   6. Open http://127.0.0.1:{port} in the user's default browser
//   7. Supervise both processes; exit when the user closes the console window
//
// Target: .NET 8, win-x64, single-file self-contained publish

using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Runtime.Intrinsics.X86;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace OfficeAgent.Launcher;

internal sealed class ConsoleLauncher
{
    // -----------------------------------------------------------------------
    // Entry point
    // -----------------------------------------------------------------------
    static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        Console.Title = "OfficeAgent";

        // Resolve the install root: the directory that contains OfficeAgent.exe.
        string installRoot = AppContext.BaseDirectory;

        try
        {
            return await RunAsync(installRoot);
        }
        catch (Exception ex)
        {
            ShowError($"予期しないエラーが発生しました:\n{ex.Message}");
            return 1;
        }
    }

    // -----------------------------------------------------------------------
    // Main logic
    // -----------------------------------------------------------------------
    static async Task<int> RunAsync(string installRoot)
    {
        // --- 1. Read settings -----------------------------------------------
        var cfg = Settings.Load(Path.Combine(installRoot, "config", "settings.ini"));

        // --- 2. Verify model file -------------------------------------------
        string modelPath = ResolveModelPath(installRoot, cfg);
        if (!File.Exists(modelPath))
        {
            ShowError(
                $"モデルファイルが見つかりません:\n{modelPath}\n\n" +
                "IT管理者にお問い合わせください。");
            return 1;
        }

        // --- 3. Detect CPU → choose llama-server binary ---------------------
        string llamaExe = SelectLlamaServerBinary(installRoot);

        // --- 4. Verify ports are free ---------------------------------------
        int llamaPort = cfg.LlmPort;
        int streamlitPort = cfg.ServerPort;

        if (!IsPortFree(llamaPort))
        {
            ShowError($"ポート {llamaPort} は既に使用されています。\n" +
                      "別のアプリが同じポートを使っている可能性があります。\n" +
                      "config\\settings.ini の llm.port を変更してください。");
            return 1;
        }
        if (!IsPortFree(streamlitPort))
        {
            ShowError($"ポート {streamlitPort} は既に使用されています。\n" +
                      "config\\settings.ini の server.port を変更してください。");
            return 1;
        }

        // --- 5. Warn if RAM is low ------------------------------------------
        long ramGb = GetTotalRamGb();
        int minRam = cfg.Tier == "pro" ? 16 : 8;
        if (ramGb > 0 && ramGb < minRam)
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine(
                $"[警告] RAM が {ramGb} GB です。{cfg.Tier} モードの推奨は {minRam} GB 以上です。\n" +
                "       パフォーマンスが低下する可能性があります。");
            Console.ResetColor();
        }

        // --- 6. Spawn llama-server ------------------------------------------
        int threadCount = cfg.Threads > 0 ? cfg.Threads : Math.Max(1, Environment.ProcessorCount / 2);
        int contextSize = cfg.ContextSize;

        var llamaArgs = string.Join(" ",
            $"--model \"{modelPath}\"",
            $"--host 127.0.0.1",
            $"--port {llamaPort}",
            $"--ctx-size {contextSize}",
            $"--threads {threadCount}",
            "--no-browser",
            "--log-disable");

        Console.WriteLine("[1/4] LLM ランタイムを起動中...");
        var llamaProcess = StartHiddenProcess(llamaExe, llamaArgs, installRoot);
        if (llamaProcess is null)
        {
            ShowError($"LLM ランタイムの起動に失敗しました:\n{llamaExe}");
            return 1;
        }

        // --- 7. Spawn OfficeAgentBackend ------------------------------------
        string backendExe = Path.Combine(installRoot, "app", "OfficeAgentBackend.exe");
        if (!File.Exists(backendExe))
        {
            llamaProcess.Kill(entireProcessTree: true);
            ShowError($"バックエンドが見つかりません:\n{backendExe}");
            return 1;
        }

        string outputDir = ResolveOutputDir(cfg);
        Directory.CreateDirectory(outputDir);

        var backendEnv = BuildBackendEnvironment(cfg, llamaPort, streamlitPort, outputDir);

        Console.WriteLine("[2/4] バックエンドを起動中...");
        var backendProcess = StartHiddenProcess(backendExe, "", installRoot, backendEnv);
        if (backendProcess is null)
        {
            llamaProcess.Kill(entireProcessTree: true);
            ShowError("バックエンドの起動に失敗しました。");
            return 1;
        }

        // --- 8. Wait for services to be ready -------------------------------
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        using var http = new HttpClient();

        Console.WriteLine("[3/4] サービスの準備を待っています...");

        bool llamaReady = await WaitForHealthAsync(
            http, $"http://127.0.0.1:{llamaPort}/health", cts.Token,
            label: "LLM ランタイム");

        if (!llamaReady)
        {
            KillAll(llamaProcess, backendProcess);
            ShowError("LLM ランタイムが起動しませんでした。\nlogs\\ フォルダのログを確認してください。");
            return 1;
        }

        bool streamlitReady = await WaitForHealthAsync(
            http, $"http://127.0.0.1:{streamlitPort}/healthz", cts.Token,
            label: "UI サーバー");

        if (!streamlitReady)
        {
            KillAll(llamaProcess, backendProcess);
            ShowError("UI サーバーが起動しませんでした。\nlogs\\ フォルダのログを確認してください。");
            return 1;
        }

        // --- 9. Open browser ------------------------------------------------
        string appUrl = $"http://127.0.0.1:{streamlitPort}";
        Console.WriteLine($"[4/4] ブラウザを開いています → {appUrl}");
        OpenBrowser(appUrl);

        // --- 10. Supervise --------------------------------------------------
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine("\nOfficeAgent が起動しました。");
        Console.ResetColor();
        Console.WriteLine("このウィンドウを閉じると OfficeAgent が終止します。\n");

        // Register Ctrl+C handler for graceful shutdown.
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            KillAll(llamaProcess, backendProcess);
        };

        // Block until either child exits unexpectedly.
        await Task.WhenAny(
            WaitForExitAsync(llamaProcess),
            WaitForExitAsync(backendProcess));

        KillAll(llamaProcess, backendProcess);
        return 0;
    }

    // -----------------------------------------------------------------------
    // CPU detection
    // -----------------------------------------------------------------------
    static string SelectLlamaServerBinary(string installRoot)
    {
        string llmDir = Path.Combine(installRoot, "llm");

        // Check AVX-512 first, then AVX2, then fallback.
        if (Avx512F.IsSupported)
        {
            string path = Path.Combine(llmDir, "llama-server-avx512.exe");
            if (File.Exists(path))
            {
                Console.WriteLine("  CPU: AVX-512 検出 → llama-server-avx512.exe を使用");
                return path;
            }
        }

        if (Avx2.IsSupported)
        {
            string path = Path.Combine(llmDir, "llama-server-avx2.exe");
            if (File.Exists(path))
            {
                Console.WriteLine("  CPU: AVX2 検出 → llama-server-avx2.exe を使用");
                return path;
            }
        }

        string noavxPath = Path.Combine(llmDir, "llama-server-noavx.exe");
        Console.WriteLine("  CPU: AVX なし → llama-server-noavx.exe を使用");
        return noavxPath;
    }

    // -----------------------------------------------------------------------
    // Model path resolution
    // -----------------------------------------------------------------------
    static string ResolveModelPath(string installRoot, Settings cfg)
    {
        string relPath = cfg.Tier == "pro" ? cfg.ModelPro : cfg.ModelStandard;

        // If the path in settings.ini is relative, resolve from install root.
        return Path.IsPathRooted(relPath)
            ? relPath
            : Path.GetFullPath(Path.Combine(installRoot, relPath));
    }

    // -----------------------------------------------------------------------
    // Output directory
    // -----------------------------------------------------------------------
    static string ResolveOutputDir(Settings cfg)
    {
        if (!string.IsNullOrWhiteSpace(cfg.OutputDir))
            return cfg.OutputDir;

        // Default: current user's Documents\OfficeAgent\
        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "OfficeAgent");
    }

    // -----------------------------------------------------------------------
    // Environment variables for the Python backend process
    // -----------------------------------------------------------------------
    static Dictionary<string, string> BuildBackendEnvironment(
        Settings cfg, int llamaPort, int streamlitPort, string outputDir)
    {
        return new Dictionary<string, string>
        {
            ["OFFICE_AGENT_BACKEND"]      = "llamacpp",
            ["OFFICE_AGENT_LLAMACPP_URL"] = $"http://127.0.0.1:{llamaPort}",
            ["OFFICE_AGENT_MODEL"]        = cfg.Tier == "pro" ? "pro" : "standard",
            ["OFFICE_AGENT_OUT_DIR"]      = outputDir,
            ["OFFICE_AGENT_LLM_TIMEOUT"]  = "180",
            ["OFFICE_AGENT_MAX_RETRIES"]  = "3",
            ["STREAMLIT_SERVER_PORT"]     = streamlitPort.ToString(),
            ["STREAMLIT_SERVER_ADDRESS"]  = "127.0.0.1",
            ["STREAMLIT_SERVER_HEADLESS"] = "true",
        };
    }

    // -----------------------------------------------------------------------
    // Process helpers
    // -----------------------------------------------------------------------
    static Process? StartHiddenProcess(
        string exePath,
        string arguments,
        string workingDir,
        Dictionary<string, string>? extraEnv = null)
    {
        if (!File.Exists(exePath))
        {
            Console.Error.WriteLine($"[ERROR] 実行ファイルが見つかりません: {exePath}");
            return null;
        }

        var psi = new ProcessStartInfo
        {
            FileName = exePath,
            Arguments = arguments,
            WorkingDirectory = workingDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = false,
            RedirectStandardError = false,
        };

        if (extraEnv is not null)
        {
            foreach (var (key, value) in extraEnv)
                psi.EnvironmentVariables[key] = value;
        }

        try
        {
            return Process.Start(psi);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[ERROR] プロセス起動失敗 ({exePath}): {ex.Message}");
            return null;
        }
    }

    static void KillAll(params Process?[] processes)
    {
        foreach (var p in processes)
        {
            if (p is null || p.HasExited) continue;
            try
            {
                p.Kill(entireProcessTree: true);
                p.WaitForExit(3000);
            }
            catch { /* Best-effort */ }
        }
    }

    static Task WaitForExitAsync(Process p) =>
        Task.Run(() => p.WaitForExit());

    // -----------------------------------------------------------------------
    // Health check polling
    // -----------------------------------------------------------------------
    static async Task<bool> WaitForHealthAsync(
        HttpClient http,
        string url,
        CancellationToken ct,
        string label = "service")
    {
        const int delayMs = 1000;
        int attempts = 0;

        while (!ct.IsCancellationRequested)
        {
            try
            {
                var response = await http.GetAsync(url, ct);
                if (response.IsSuccessStatusCode)
                {
                    Console.WriteLine($"  ✓ {label} 準備完了");
                    return true;
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch
            {
                // Not ready yet — keep polling.
            }

            attempts++;
            if (attempts % 10 == 0)
                Console.WriteLine($"  待機中... ({attempts}s)");

            await Task.Delay(delayMs, ct).ConfigureAwait(false);
        }

        return false;
    }

    // -----------------------------------------------------------------------
    // Browser open
    // -----------------------------------------------------------------------
    static void OpenBrowser(string url)
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true,  // Windows ShellExecute opens the default browser.
            });
        }
        catch (Exception ex)
        {
            Console.WriteLine($"  ブラウザを自動で開けませんでした。手動でアクセスしてください: {url}");
            Console.WriteLine($"  ({ex.Message})");
        }
    }

    // -----------------------------------------------------------------------
    // Port availability check
    // -----------------------------------------------------------------------
    static bool IsPortFree(int port)
    {
        try
        {
            using var listener = new System.Net.Sockets.TcpListener(
                System.Net.IPAddress.Loopback, port);
            listener.Start();
            listener.Stop();
            return true;
        }
        catch
        {
            return false;
        }
    }

    // -----------------------------------------------------------------------
    // RAM detection (Windows WMI-free approach via GlobalMemoryStatusEx)
    // -----------------------------------------------------------------------
    [System.Runtime.InteropServices.StructLayout(
        System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct MEMORYSTATUSEX
    {
        public uint dwLength;
        public uint dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;
    }

    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    private static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX lpBuffer);

    static long GetTotalRamGb()
    {
        try
        {
            var mem = new MEMORYSTATUSEX { dwLength = (uint)System.Runtime.InteropServices.Marshal.SizeOf<MEMORYSTATUSEX>() };
            if (GlobalMemoryStatusEx(ref mem))
                return (long)(mem.ullTotalPhys / (1024UL * 1024 * 1024));
        }
        catch { /* Non-Windows or permission issue */ }
        return 0;
    }

    // -----------------------------------------------------------------------
    // User-visible error dialog
    // -----------------------------------------------------------------------
    static void ShowError(string message)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.Error.WriteLine($"\n[エラー] {message}\n");
        Console.ResetColor();

        // Show a Windows message box so non-technical users see a clear error
        // even if they have the console window minimised.
        try
        {
            System.Windows.Forms.MessageBox.Show(
                message,
                "OfficeAgent — エラー",
                System.Windows.Forms.MessageBoxButtons.OK,
                System.Windows.Forms.MessageBoxIcon.Error);
        }
        catch
        {
            // MessageBox not available (headless/SSH); console output is enough.
        }
    }
}

// ---------------------------------------------------------------------------
// Simple INI settings reader — no external NuGet dependency required.
// ---------------------------------------------------------------------------
internal sealed class Settings
{
    public string Tier         { get; private set; } = "standard";
    public int    LlmPort      { get; private set; } = 8080;
    public int    ContextSize  { get; private set; } = 4096;
    public int    Threads      { get; private set; } = 0;
    public bool   Gpu          { get; private set; } = false;
    public int    ServerPort   { get; private set; } = 8501;
    public string OutputDir    { get; private set; } = "";
    public string ModelStandard { get; private set; } = @"models\standard.gguf";
    public string ModelPro     { get; private set; } = @"models\pro.gguf";
    public int    LogRetentionDays { get; private set; } = 90;
    public bool   IntegrityCheck   { get; private set; } = true;

    public static Settings Load(string path)
    {
        var s = new Settings();
        if (!File.Exists(path))
        {
            Console.WriteLine($"  [INFO] settings.ini が見つかりません。デフォルト設定を使用します: {path}");
            return s;
        }

        string? section = null;
        foreach (string rawLine in File.ReadLines(path))
        {
            string line = rawLine.Trim();
            if (string.IsNullOrEmpty(line) || line.StartsWith(';')) continue;

            if (line.StartsWith('[') && line.EndsWith(']'))
            {
                section = line[1..^1].ToLowerInvariant();
                continue;
            }

            int eq = line.IndexOf('=');
            if (eq < 0) continue;

            string key   = line[..eq].Trim().ToLowerInvariant();
            string value = line[(eq + 1)..].Trim();

            // Strip inline comments.
            int comment = value.IndexOf(';');
            if (comment >= 0) value = value[..comment].Trim();

            switch (section)
            {
                case "app":
                    if (key == "tier") s.Tier = value;
                    break;
                case "llm":
                    if (key == "port"         && int.TryParse(value, out int lp))  s.LlmPort     = lp;
                    if (key == "context_size" && int.TryParse(value, out int cs))  s.ContextSize  = cs;
                    if (key == "threads"      && int.TryParse(value, out int th))  s.Threads      = th;
                    if (key == "gpu")                                               s.Gpu          = value == "true";
                    break;
                case "server":
                    if (key == "port" && int.TryParse(value, out int sp)) s.ServerPort = sp;
                    break;
                case "paths":
                    if (key == "output_dir")     s.OutputDir     = value;
                    if (key == "model_standard") s.ModelStandard = value;
                    if (key == "model_pro")      s.ModelPro      = value;
                    break;
                case "security":
                    if (key == "log_retention_days" && int.TryParse(value, out int lr)) s.LogRetentionDays = lr;
                    if (key == "integrity_check")                                        s.IntegrityCheck   = value != "false";
                    break;
            }
        }

        return s;
    }
}

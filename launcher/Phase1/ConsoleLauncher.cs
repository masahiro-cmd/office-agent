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
//   8. Record launcher events and llama-server stdout/stderr under logs\
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

        Log.Initialize(installRoot);

        try
        {
            int exitCode = await RunAsync(installRoot);
            Log.Info($"ランチャー終了 (exit code {exitCode})");
            return exitCode;
        }
        catch (Exception ex)
        {
            Log.Error($"予期しない例外: {ex}");
            ShowError($"予期しないエラーが発生しました:\n{ex.Message}\n\n詳細ログ: {Log.LauncherLogPath}");
            return 1;
        }
        finally
        {
            Log.Shutdown();
        }
    }

    // -----------------------------------------------------------------------
    // Main logic
    // -----------------------------------------------------------------------
    static async Task<int> RunAsync(string installRoot)
    {
        // --- 1. Read settings -----------------------------------------------
        var cfg = Settings.Load(Path.Combine(installRoot, "config", "settings.ini"));
        Log.Info($"設定: tier={cfg.Tier}, llm.port={cfg.LlmPort}, server.port={cfg.ServerPort}, " +
                 $"context_size={cfg.ContextSize}, threads={cfg.Threads}");

        // --- 2. Verify model file -------------------------------------------
        string modelPath = ResolveModelPath(installRoot, cfg);
        Log.Info($"モデル: {modelPath} (存在={File.Exists(modelPath)})");
        if (!File.Exists(modelPath))
        {
            ShowError(
                $"モデルファイルが見つかりません:\n{modelPath}\n\n" +
                "IT管理者にお問い合わせください。");
            return 1;
        }

        // --- 3. Detect CPU → choose llama-server binary ---------------------
        string llamaExe = SelectLlamaServerBinary(installRoot);
        Log.Info($"llama-server 実行ファイル: {llamaExe} (存在={File.Exists(llamaExe)})");

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
        Log.Info($"RAM: {ramGb} GB (推奨 {minRam} GB 以上), 論理 CPU 数: {Environment.ProcessorCount}");
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

        // --log-disable is intentionally not passed: llama-server's stdout/stderr
        // is captured into logs\llama-server.log so start-up failures are visible.
        var llamaArgs = string.Join(" ",
            $"--model \"{modelPath}\"",
            $"--host 127.0.0.1",
            $"--port {llamaPort}",
            $"--ctx-size {contextSize}",
            $"--threads {threadCount}");

        Process? llamaProcess = null;
        Process? backendProcess = null;

        // Every exit path from here on — success, failure, timeout or exception —
        // must terminate the child processes, so cleanup lives in finally.
        try
        {
            var llamaTail = new OutputTail(capacity: 10);
            LogFile? llamaLog = Log.OpenChildLog("llama-server.log");
            llamaLog?.Write($"==== llama-server 起動 (launcher PID {Environment.ProcessId}) ====");

            Console.WriteLine("[1/4] LLM ランタイムを起動中...");
            llamaProcess = StartHiddenProcess(
                "llama-server", llamaExe, llamaArgs, installRoot,
                onOutputLine: line =>
                {
                    llamaLog?.Write(line);
                    llamaTail.Add(line);
                },
                childLog: llamaLog);
            if (llamaProcess is null)
            {
                ShowError($"LLM ランタイムの起動に失敗しました:\n{llamaExe}\n\n詳細ログ: {Log.LauncherLogPath}");
                return 1;
            }

            // --- 7. Spawn OfficeAgentBackend --------------------------------
            string backendExe = Path.Combine(installRoot, "app", "OfficeAgentBackend.exe");
            if (!File.Exists(backendExe))
            {
                KillAll(llamaProcess);
                ShowError($"バックエンドが見つかりません:\n{backendExe}");
                return 1;
            }

            string outputDir = ResolveOutputDir(cfg);
            Directory.CreateDirectory(outputDir);

            var backendEnv = BuildBackendEnvironment(cfg, llamaPort, streamlitPort, outputDir);

            Console.WriteLine("[2/4] バックエンドを起動中...");
            backendProcess = StartHiddenProcess("backend", backendExe, "", installRoot, backendEnv);
            if (backendProcess is null)
            {
                KillAll(llamaProcess);
                ShowError($"バックエンドの起動に失敗しました。\n\n詳細ログ: {Log.LauncherLogPath}");
                return 1;
            }

            // --- 8. Wait for services to be ready ---------------------------
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
            // A short per-request timeout keeps a hung endpoint from consuming
            // the whole start-up budget in a single request.
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };

            Console.WriteLine("[3/4] サービスの準備を待っています...");

            HealthResult llamaHealth = await WaitForHealthAsync(
                http, $"http://127.0.0.1:{llamaPort}/health", llamaProcess, cts.Token,
                label: "LLM ランタイム");

            if (!llamaHealth.Ready)
            {
                // Terminate before the modal dialog so the ports are released
                // while it is open; then let the output readers drain the last lines.
                KillAll(llamaProcess, backendProcess);
                llamaProcess.WaitForExit(1000);
                ShowError(
                    "LLM ランタイムが起動しませんでした。\n" +
                    $"理由: {llamaHealth.Reason}\n\n" +
                    "--- llama-server の最後の出力 ---\n" +
                    FormatTail(llamaTail) + "\n\n" +
                    $"詳細ログ: {llamaLog?.FilePath ?? Log.LauncherLogPath}");
                return 1;
            }

            HealthResult streamlitHealth = await WaitForHealthAsync(
                http, $"http://127.0.0.1:{streamlitPort}/healthz", backendProcess, cts.Token,
                label: "UI サーバー");

            if (!streamlitHealth.Ready)
            {
                KillAll(llamaProcess, backendProcess);
                ShowError(
                    "UI サーバーが起動しませんでした。\n" +
                    $"理由: {streamlitHealth.Reason}\n\n" +
                    $"詳細ログ: {Log.LauncherLogPath}");
                return 1;
            }

            // --- 9. Open browser --------------------------------------------
            string appUrl = $"http://127.0.0.1:{streamlitPort}";
            Console.WriteLine($"[4/4] ブラウザを開いています → {appUrl}");
            Log.Info($"ブラウザを開きます: {appUrl}");
            OpenBrowser(appUrl);

            // --- 10. Supervise ----------------------------------------------
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("\nOfficeAgent が起動しました。");
            Console.ResetColor();
            Console.WriteLine("このウィンドウを閉じると OfficeAgent が終止します。\n");
            Log.Info("起動完了。子プロセスを監視します。");

            // Register Ctrl+C handler for graceful shutdown.
            Console.CancelKeyPress += (_, e) =>
            {
                e.Cancel = true;
                Log.Info("Ctrl+C を受信しました。終了します。");
                KillAll(llamaProcess, backendProcess);
            };

            // Block until either child exits unexpectedly.
            Task llamaExit = WaitForExitAsync(llamaProcess);
            Task backendExit = WaitForExitAsync(backendProcess);
            Task firstExit = await Task.WhenAny(llamaExit, backendExit);

            string exitedLabel = firstExit == llamaExit ? "llama-server" : "backend";
            Process exited = firstExit == llamaExit ? llamaProcess : backendProcess;
            Log.Warn($"{exitedLabel} が終了したため OfficeAgent を終了します ({DescribeExit(exited)})");
            return 0;
        }
        finally
        {
            KillAll(llamaProcess, backendProcess);
        }
    }

    // -----------------------------------------------------------------------
    // CPU detection
    // -----------------------------------------------------------------------
    static string SelectLlamaServerBinary(string installRoot)
    {
        string llmDir = Path.Combine(installRoot, "llm");

        // Current llama.cpp Windows releases ship a single cpu-x64 binary that
        // selects the AVX code path itself at run time (ggml.dll loads the
        // matching ggml-cpu-*.dll), so prefer it when present.
        string unifiedPath = Path.Combine(llmDir, "llama-server.exe");
        if (File.Exists(unifiedPath))
        {
            string caps = Avx512F.IsSupported ? "AVX-512"
                        : Avx2.IsSupported    ? "AVX2"
                                              : "AVX なし";
            Console.WriteLine($"  CPU: {caps} 検出 → llama-server.exe を使用（実行時に最適化を選択）");
            return unifiedPath;
        }

        // Backward compatibility: packages built before the unified binary
        // shipped one executable per CPU variant.
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
    /// <summary>
    /// Starts a child process without a visible window. When
    /// <paramref name="onOutputLine"/> is given, stdout and stderr are
    /// redirected and every line is passed to it prefixed with [stdout]/[stderr].
    /// Start parameters and the exit code are written to the launcher log and,
    /// when given, to <paramref name="childLog"/>.
    /// </summary>
    static Process? StartHiddenProcess(
        string label,
        string exePath,
        string arguments,
        string workingDir,
        Dictionary<string, string>? extraEnv = null,
        Action<string>? onOutputLine = null,
        LogFile? childLog = null)
    {
        void LogBoth(string message)
        {
            Log.Info($"{label}: {message}");
            childLog?.Write(message);
        }

        LogBoth($"実行パス: {exePath}");
        LogBoth($"引数: {arguments}");
        LogBoth($"WorkingDirectory: {workingDir}");

        if (!File.Exists(exePath))
        {
            Console.Error.WriteLine($"[ERROR] 実行ファイルが見つかりません: {exePath}");
            Log.Error($"{label}: 実行ファイルが見つかりません: {exePath}");
            childLog?.Write($"実行ファイルが見つかりません: {exePath}");
            return null;
        }

        bool capture = onOutputLine is not null;
        var psi = new ProcessStartInfo
        {
            FileName = exePath,
            Arguments = arguments,
            WorkingDirectory = workingDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = capture,
            RedirectStandardError = capture,
        };
        if (capture)
        {
            psi.StandardOutputEncoding = Encoding.UTF8;
            psi.StandardErrorEncoding = Encoding.UTF8;
        }

        if (extraEnv is not null)
        {
            foreach (var (key, value) in extraEnv)
                psi.EnvironmentVariables[key] = value;
        }

        Process? process;
        try
        {
            process = Process.Start(psi);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[ERROR] プロセス起動失敗 ({exePath}): {ex.Message}");
            Log.Error($"{label}: プロセス起動失敗: {ex}");
            childLog?.Write($"プロセス起動失敗: {ex.Message}");
            return null;
        }

        if (process is null)
        {
            Log.Error($"{label}: Process.Start が null を返しました");
            childLog?.Write("Process.Start が null を返しました");
            return null;
        }

        LogBoth($"起動しました (PID {process.Id})");

        process.EnableRaisingEvents = true;
        process.Exited += (_, _) => LogBoth($"プロセス終了 (PID {process.Id}, {DescribeExit(process)})");

        if (onOutputLine is not null)
        {
            process.OutputDataReceived += (_, e) =>
            {
                if (e.Data is not null) onOutputLine($"[stdout] {e.Data}");
            };
            process.ErrorDataReceived += (_, e) =>
            {
                if (e.Data is not null) onOutputLine($"[stderr] {e.Data}");
            };
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
        }

        return process;
    }

    static void KillAll(params Process?[] processes)
    {
        foreach (var p in processes)
        {
            if (p is null) continue;
            try
            {
                if (p.HasExited) continue;
                Log.Info($"PID {p.Id} を終了します");
                p.Kill(entireProcessTree: true);
                if (!p.WaitForExit(3000))
                    Log.Warn($"PID {p.Id} が 3 秒以内に終了しませんでした");
            }
            catch (Exception ex)
            {
                // Best-effort: one failure must not stop the remaining kills.
                Log.Warn($"プロセス終了処理に失敗しました: {ex.Message}");
            }
        }
    }

    /// <summary>Exit code in decimal and hex, with a hint for common Windows crash codes.</summary>
    static string DescribeExit(Process p)
    {
        int code;
        try
        {
            code = p.ExitCode;
        }
        catch (Exception ex)
        {
            return $"終了コード取得失敗: {ex.Message}";
        }

        uint raw = unchecked((uint)code);
        string hint = raw switch
        {
            0xC0000135 => " — DLL が見つかりません (llm フォルダの DLL 不足の可能性)",
            0xC000001D => " — CPU が未対応の命令を実行しました (AVX 非対応 CPU の可能性)",
            0xC0000005 => " — アクセス違反",
            0xC0000409 => " — スタックバッファオーバーラン / 異常終了",
            _ => "",
        };
        return $"終了コード {code} (0x{raw:X8}){hint}";
    }

    /// <summary>Last captured output lines for console / dialog display.</summary>
    static string FormatTail(OutputTail tail)
    {
        const int maxLineLength = 200;
        string[] lines = tail.Snapshot();
        if (lines.Length == 0)
            return "(出力なし)";

        var sb = new StringBuilder();
        foreach (string line in lines)
        {
            sb.AppendLine(line.Length > maxLineLength ? line[..maxLineLength] + "…" : line);
        }
        return sb.ToString().TrimEnd();
    }

    static Task WaitForExitAsync(Process p) =>
        Task.Run(() => p.WaitForExit());

    // -----------------------------------------------------------------------
    // Health check polling
    // -----------------------------------------------------------------------
    readonly record struct HealthResult(bool Ready, string Reason);

    /// <summary>
    /// Polls <paramref name="url"/> until it answers 2xx, the process exits, or
    /// <paramref name="ct"/> expires. Never throws on timeout; the returned
    /// Reason says why the service did not become ready.
    /// </summary>
    static async Task<HealthResult> WaitForHealthAsync(
        HttpClient http,
        string url,
        Process process,
        CancellationToken ct,
        string label = "service")
    {
        const int delayMs = 1000;
        int attempts = 0;
        var elapsed = Stopwatch.StartNew();
        string lastReason = "未確認";
        string? loggedReason = null;

        Log.Info($"{label}: health check 開始 {url} (PID {process.Id})");

        while (true)
        {
            if (process.HasExited)
            {
                string reason = $"プロセスが終了しました ({DescribeExit(process)})";
                Log.Error($"{label}: health check 失敗 — {reason} / 直前の応答: {lastReason}");
                return new HealthResult(false, reason);
            }

            if (ct.IsCancellationRequested)
                break;

            try
            {
                using var response = await http.GetAsync(url, ct);
                if (response.IsSuccessStatusCode)
                {
                    Console.WriteLine($"  ✓ {label} 準備完了");
                    Log.Info($"{label}: 準備完了 ({elapsed.Elapsed.TotalSeconds:F0} 秒)");
                    return new HealthResult(true, "");
                }
                // llama-server answers 503 while the model is still loading.
                lastReason = $"HTTP {(int)response.StatusCode} {response.ReasonPhrase}";
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                break;
            }
            catch (TaskCanceledException)
            {
                lastReason = $"応答なし (リクエストタイムアウト {http.Timeout.TotalSeconds:F0} 秒)";
            }
            catch (HttpRequestException ex)
            {
                lastReason = $"接続失敗: {ex.Message}";
            }
            catch (Exception ex)
            {
                lastReason = $"{ex.GetType().Name}: {ex.Message}";
            }

            // Log only changes so a 120-second wait does not flood the log.
            if (lastReason != loggedReason)
            {
                Log.Info($"{label}: 未準備 ({elapsed.Elapsed.TotalSeconds:F0} 秒経過) — {lastReason}");
                loggedReason = lastReason;
            }

            attempts++;
            if (attempts % 10 == 0)
                Console.WriteLine($"  待機中... ({attempts}s)");

            try
            {
                await Task.Delay(delayMs, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }

        string timeoutReason =
            $"タイムアウト ({elapsed.Elapsed.TotalSeconds:F0} 秒以内に応答しませんでした) / 直前の応答: {lastReason}";
        Log.Error($"{label}: health check 失敗 — {timeoutReason}");
        return new HealthResult(false, timeoutReason);
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
    private const uint MB_OK            = 0x00000000;
    private const uint MB_ICONERROR     = 0x00000010;
    private const uint MB_SETFOREGROUND = 0x00010000;

    [System.Runtime.InteropServices.DllImport(
        "user32.dll",
        CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    static void ShowError(string message)
    {
        Log.Error($"エラー表示: {message.Replace("\n", " | ")}");

        Console.ForegroundColor = ConsoleColor.Red;
        Console.Error.WriteLine($"\n[エラー] {message}\n");
        Console.ResetColor();

        // Show a Windows message box so non-technical users see a clear error
        // even if they have the console window minimised.
        try
        {
            MessageBoxW(IntPtr.Zero, message, "OfficeAgent — エラー",
                        MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
        }
        catch
        {
            // MessageBox not available (headless/SSH); console output is enough.
        }
    }
}

// ---------------------------------------------------------------------------
// File logging — local files only, no external logging.
//
// Logs go to <install root>\logs\. If that folder is not writable (e.g. the
// ZIP was extracted somewhere read-only), %LOCALAPPDATA%\OfficeAgent\logs\ is
// used instead. Logging failures never stop the launcher.
// ---------------------------------------------------------------------------
internal static class Log
{
    private static readonly object Gate = new();
    private static readonly List<LogFile> OpenFiles = new();
    private static LogFile? _launcher;

    /// <summary>Directory holding the log files, or null when none is writable.</summary>
    public static string? LogDir { get; private set; }

    public static string LauncherLogPath =>
        _launcher?.FilePath ?? "(ログファイルを作成できませんでした)";

    public static void Initialize(string installRoot)
    {
        string[] candidates =
        {
            Path.Combine(installRoot, "logs"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "OfficeAgent", "logs"),
        };

        foreach (string dir in candidates)
        {
            try
            {
                Directory.CreateDirectory(dir);
                _launcher = LogFile.Open(Path.Combine(dir, "launcher.log"));
                LogDir = dir;
                break;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[警告] ログフォルダを使用できません: {dir} ({ex.Message})");
            }
        }

        if (_launcher is null)
        {
            Console.Error.WriteLine("[警告] ログファイルを作成できませんでした。ログはコンソールにのみ表示されます。");
            return;
        }

        lock (Gate) OpenFiles.Add(_launcher);
        Console.WriteLine($"  ログ: {LogDir}");

        Info("==== OfficeAgent ランチャー起動 ====");
        Info($"ランチャー: {Environment.ProcessPath} (PID {Environment.ProcessId}, " +
             $"version {typeof(Log).Assembly.GetName().Version})");
        Info($"インストール先: {installRoot}");
        Info($"OS: {Environment.OSVersion}, 64bit プロセス: {Environment.Is64BitProcess}");
    }

    /// <summary>Opens another log file next to launcher.log; null when logging is unavailable.</summary>
    public static LogFile? OpenChildLog(string fileName)
    {
        if (LogDir is null) return null;
        try
        {
            var file = LogFile.Open(Path.Combine(LogDir, fileName));
            lock (Gate) OpenFiles.Add(file);
            Info($"{fileName} に出力を記録します: {file.FilePath}");
            return file;
        }
        catch (Exception ex)
        {
            Warn($"{fileName} を開けませんでした: {ex.Message}");
            return null;
        }
    }

    public static void Info(string message)  => _launcher?.Write($"[INFO] {message}");
    public static void Warn(string message)  => _launcher?.Write($"[WARN] {message}");
    public static void Error(string message) => _launcher?.Write($"[ERROR] {message}");

    public static void Shutdown()
    {
        lock (Gate)
        {
            foreach (var file in OpenFiles) file.Close();
            OpenFiles.Clear();
        }
    }
}

/// <summary>
/// One append-only UTF-8 log file, safe to write from several threads.
/// A file larger than 10 MB at open time is moved to *.prev.log first, so
/// each log stays bounded at roughly two generations.
/// </summary>
internal sealed class LogFile
{
    private const long RotateBytes = 10L * 1024 * 1024;

    private readonly object _gate = new();
    private StreamWriter? _writer;

    public string FilePath { get; }

    private LogFile(string filePath, StreamWriter writer)
    {
        FilePath = filePath;
        _writer = writer;
    }

    public static LogFile Open(string filePath)
    {
        var info = new FileInfo(filePath);
        if (info.Exists && info.Length > RotateBytes)
        {
            try
            {
                File.Move(filePath, Path.ChangeExtension(filePath, ".prev.log"), overwrite: true);
            }
            catch (Exception ex)
            {
                // Another instance may hold the file; keep appending instead.
                Console.Error.WriteLine($"[警告] ログのローテーションに失敗しました: {filePath} ({ex.Message})");
            }
        }

        var stream = new FileStream(
            filePath, FileMode.Append, FileAccess.Write,
            FileShare.ReadWrite | FileShare.Delete);
        // AutoFlush so the last lines survive a crash or a closed console window.
        var writer = new StreamWriter(stream, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false))
        {
            AutoFlush = true,
        };
        return new LogFile(filePath, writer);
    }

    public void Write(string line)
    {
        lock (_gate)
        {
            if (_writer is null) return;  // Already closed; late output is dropped.
            try
            {
                _writer.WriteLine($"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {line}");
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[警告] ログ書き込みに失敗しました ({FilePath}): {ex.Message}");
            }
        }
    }

    public void Close()
    {
        lock (_gate)
        {
            _writer?.Dispose();
            _writer = null;
        }
    }
}

/// <summary>Keeps the last N output lines of a child process for error dialogs.</summary>
internal sealed class OutputTail
{
    private readonly int _capacity;
    private readonly Queue<string> _lines = new();

    public OutputTail(int capacity) => _capacity = capacity;

    public void Add(string line)
    {
        lock (_lines)
        {
            _lines.Enqueue(line);
            while (_lines.Count > _capacity) _lines.Dequeue();
        }
    }

    public string[] Snapshot()
    {
        lock (_lines) return _lines.ToArray();
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

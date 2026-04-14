using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace OfficeAgent.Wpf.Services;

/// <summary>
/// Owns the lifetime of the llama-server and OfficeAgentBackend subprocesses.
/// Dispose() gracefully terminates both.
/// </summary>
internal sealed class ProcessManager : IDisposable
{
    private readonly string _installRoot;
    private readonly Settings _cfg;

    private Process? _llamaProcess;
    private Process? _backendProcess;
    private bool _disposed;

    public ProcessManager(string installRoot, Settings cfg)
    {
        _installRoot = installRoot;
        _cfg = cfg;
    }

    /// <summary>
    /// Starts llama-server and OfficeAgentBackend, polls until both are healthy.
    /// Returns true on success.
    /// </summary>
    public async Task<bool> StartAsync(Action<string>? onProgress = null)
    {
        void Report(string msg) => onProgress?.Invoke(msg);

        // 1. Select and start llama-server
        string llamaExe = CpuDetector.SelectBinary(_installRoot);
        string modelPath = _cfg.Tier == "pro"
            ? Path.Combine(_installRoot, _cfg.ModelPro)
            : Path.Combine(_installRoot, _cfg.ModelStandard);

        int threads = _cfg.Threads > 0 ? _cfg.Threads : Math.Max(1, Environment.ProcessorCount / 2);

        string llamaArgs = string.Join(" ",
            $"--model \"{modelPath}\"",
            $"--host 127.0.0.1",
            $"--port {_cfg.LlmPort}",
            $"--ctx-size {_cfg.ContextSize}",
            $"--threads {threads}",
            "--no-browser",
            "--log-disable");

        Report("LLM ランタイムを起動しています...");
        _llamaProcess = StartHidden(llamaExe, llamaArgs, _installRoot);
        if (_llamaProcess is null) return false;

        // 2. Resolve output dir and start backend
        string outputDir = ResolveOutputDir();
        Directory.CreateDirectory(outputDir);

        string backendExe = Path.Combine(_installRoot, "app", "OfficeAgentBackend.exe");
        var env = BuildEnv(outputDir);

        Report("バックエンドを起動しています...");
        _backendProcess = StartHidden(backendExe, "", _installRoot, env);
        if (_backendProcess is null)
        {
            _llamaProcess.Kill(entireProcessTree: true);
            return false;
        }

        // 3. Wait for health endpoints
        using var http = new HttpClient();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));

        Report("LLM ランタイムの準備を待っています...");
        bool llamaOk = await PollHealthAsync(
            http, $"http://127.0.0.1:{_cfg.LlmPort}/health", cts.Token);
        if (!llamaOk) return false;

        Report("UI サーバーの準備を待っています...");
        bool streamlitOk = await PollHealthAsync(
            http, $"http://127.0.0.1:{_cfg.ServerPort}/healthz", cts.Token);

        return streamlitOk;
    }

    private string ResolveOutputDir()
    {
        if (!string.IsNullOrWhiteSpace(_cfg.OutputDir))
            return _cfg.OutputDir;

        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "OfficeAgent");
    }

    private Dictionary<string, string> BuildEnv(string outputDir) => new()
    {
        ["OFFICE_AGENT_BACKEND"]      = "llamacpp",
        ["OFFICE_AGENT_LLAMACPP_URL"] = $"http://127.0.0.1:{_cfg.LlmPort}",
        ["OFFICE_AGENT_MODEL"]        = _cfg.Tier,
        ["OFFICE_AGENT_OUT_DIR"]      = outputDir,
        ["OFFICE_AGENT_LLM_TIMEOUT"]  = "180",
        ["OFFICE_AGENT_MAX_RETRIES"]  = "3",
        ["STREAMLIT_SERVER_PORT"]     = _cfg.ServerPort.ToString(),
        ["STREAMLIT_SERVER_ADDRESS"]  = "127.0.0.1",
        ["STREAMLIT_SERVER_HEADLESS"] = "true",
    };

    private static Process? StartHidden(
        string exe, string args, string workDir,
        Dictionary<string, string>? extraEnv = null)
    {
        if (!File.Exists(exe)) return null;

        var psi = new ProcessStartInfo
        {
            FileName = exe,
            Arguments = args,
            WorkingDirectory = workDir,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        if (extraEnv is not null)
            foreach (var (k, v) in extraEnv)
                psi.EnvironmentVariables[k] = v;

        try { return Process.Start(psi); }
        catch { return null; }
    }

    private static async Task<bool> PollHealthAsync(
        HttpClient http, string url, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var r = await http.GetAsync(url, ct);
                if (r.IsSuccessStatusCode) return true;
            }
            catch (OperationCanceledException) { break; }
            catch { /* not ready yet */ }

            await Task.Delay(1000, ct).ConfigureAwait(false);
        }
        return false;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        foreach (var p in new[] { _backendProcess, _llamaProcess })
        {
            if (p is null || p.HasExited) continue;
            try { p.Kill(entireProcessTree: true); p.WaitForExit(3000); }
            catch { /* best-effort */ }
        }
    }
}

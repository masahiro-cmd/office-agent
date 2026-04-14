using System;
using System.IO;

namespace OfficeAgent.Wpf.Services;

/// <summary>
/// Reads config/settings.ini and exposes typed properties.
/// Shared by both SplashWindow and ProcessManager.
/// </summary>
internal sealed class Settings
{
    public string Tier             { get; private set; } = "standard";
    public int    LlmPort          { get; private set; } = 8080;
    public int    ContextSize      { get; private set; } = 4096;
    public int    Threads          { get; private set; } = 0;
    public bool   Gpu              { get; private set; } = false;
    public int    ServerPort       { get; private set; } = 8501;
    public string OutputDir        { get; private set; } = "";
    public string ModelStandard    { get; private set; } = @"models\standard.gguf";
    public string ModelPro         { get; private set; } = @"models\pro.gguf";
    public int    LogRetentionDays { get; private set; } = 90;
    public bool   IntegrityCheck   { get; private set; } = true;

    public static Settings Load(string path)
    {
        var s = new Settings();
        if (!File.Exists(path)) return s;

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
            int commentIdx = value.IndexOf(';');
            if (commentIdx >= 0) value = value[..commentIdx].Trim();

            switch (section)
            {
                case "app":
                    if (key == "tier") s.Tier = value;
                    break;
                case "llm":
                    if (key == "port"         && int.TryParse(value, out int lp)) s.LlmPort      = lp;
                    if (key == "context_size" && int.TryParse(value, out int cs)) s.ContextSize   = cs;
                    if (key == "threads"      && int.TryParse(value, out int th)) s.Threads       = th;
                    if (key == "gpu")                                              s.Gpu           = value == "true";
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

using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using OfficeAgent.Wpf.Services;

namespace OfficeAgent.Wpf;

public partial class SplashWindow : Window
{
    public SplashWindow()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        await RunStartupSequenceAsync();
    }

    private async Task RunStartupSequenceAsync()
    {
        string installRoot = AppContext.BaseDirectory;
        var cfg = Settings.Load(Path.Combine(installRoot, "config", "settings.ini"));

        // --- Startup checks -------------------------------------------------
        SetStatus("設定を確認しています...");

        var checker = new IntegrityChecker(installRoot, cfg);
        var licenseValidator = new LicenseValidator(installRoot);

        // Model file check
        SetStatus("モデルファイルを確認しています...");
        await Task.Delay(200); // Allow UI to render

        string modelPath = cfg.Tier == "pro"
            ? Path.Combine(installRoot, cfg.ModelPro)
            : Path.Combine(installRoot, cfg.ModelStandard);

        if (!File.Exists(modelPath))
        {
            ShowFatalError(
                $"モデルファイルが見つかりません:\n{modelPath}\n\n" +
                "IT管理者にお問い合わせください。");
            return;
        }

        // Integrity check (optional, from settings)
        if (cfg.IntegrityCheck)
        {
            SetStatus("ファイル整合性を確認しています...");
            var integrityResult = await Task.Run(() => checker.Verify());
            if (!integrityResult.IsValid)
            {
                ShowFatalError(
                    $"ファイルの整合性チェックに失敗しました:\n{integrityResult.FailedFile}\n\n" +
                    "インストールが破損している可能性があります。IT管理者にお問い合わせください。");
                return;
            }
        }

        // License check
        SetStatus("ライセンスを確認しています...");
        var licenseResult = await Task.Run(() => licenseValidator.Validate(cfg.Tier));

        if (licenseResult != LicenseStatus.Valid)
        {
            string hwId = licenseValidator.GetHardwareId();
            ShowFatalError(
                $"ライセンスが無効です: {licenseResult}\n\n" +
                $"ハードウェア ID: {hwId}\n\n" +
                "IT管理者にこのハードウェア ID をお伝えください。");
            return;
        }

        // RAM warning (non-blocking)
        long ramGb = SystemInfo.GetTotalRamGb();
        int minRam = cfg.Tier == "pro" ? 16 : 8;
        if (ramGb > 0 && ramGb < minRam)
        {
            var warn = MessageBox.Show(
                $"RAM が {ramGb} GB です。{cfg.Tier} モードの推奨は {minRam} GB 以上です。\n" +
                "パフォーマンスが低下する可能性があります。続行しますか？",
                "OfficeAgent — 警告",
                MessageBoxButton.YesNo,
                MessageBoxImage.Warning);

            if (warn == MessageBoxResult.No) { Application.Current.Shutdown(); return; }
        }

        // --- Start services -------------------------------------------------
        SetStatus("LLM ランタイムを起動しています...");

        var processManager = new ProcessManager(installRoot, cfg);
        ((App)Application.Current).ProcessManager = processManager;  // App owns lifetime

        bool started = await processManager.StartAsync(
            onProgress: msg => SetStatus(msg));

        if (!started)
        {
            ShowFatalError(
                "サービスの起動に失敗しました。\n" +
                $"ログを確認してください:\nC:\\ProgramData\\OfficeAgent\\logs\\");
            return;
        }

        // --- Open main window -----------------------------------------------
        SetStatus("完了");
        ProgressBar.IsIndeterminate = false;
        ProgressBar.Value = 100;

        var main = new MainWindow(cfg);
        Application.Current.MainWindow = main;
        main.Show();
        Close();
    }

    private void SetStatus(string message)
    {
        Dispatcher.Invoke(() => StatusText.Text = message);
    }

    private void ShowFatalError(string message)
    {
        Dispatcher.Invoke(() =>
        {
            MessageBox.Show(message, "OfficeAgent — エラー",
                MessageBoxButton.OK, MessageBoxImage.Error);
            Application.Current.Shutdown(1);
        });
    }
}

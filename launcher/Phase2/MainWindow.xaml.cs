using System;
using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Web.WebView2.Core;
using OfficeAgent.Wpf.Services;

namespace OfficeAgent.Wpf;

public partial class MainWindow : Window
{
    private readonly Settings _cfg;
    private readonly string _appUrl;

    public MainWindow(Settings cfg)
    {
        _cfg = cfg;
        _appUrl = $"http://127.0.0.1:{cfg.ServerPort}";

        InitializeComponent();
        TierLabel.Text = cfg.Tier == "pro" ? "Pro" : "Standard";
        Loaded += OnLoaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        // Initialise WebView2 environment — uses the system-installed or
        // bundled WebView2 runtime. User data stored in %AppData%\OfficeAgent.
        var env = await CoreWebView2Environment.CreateAsync(
            browserExecutableFolder: null,
            userDataFolder: System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "OfficeAgent", "WebView2Cache"));

        await WebView.EnsureCoreWebView2Async(env);

        // Security: block all navigation away from localhost.
        WebView.CoreWebView2.NavigationStarting += OnNavigationStarting;
        WebView.CoreWebView2.NavigationCompleted += OnNavigationCompleted;

        // Disable browser context menu and DevTools in production.
        WebView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
        WebView.CoreWebView2.Settings.AreDevToolsEnabled = false;
        WebView.CoreWebView2.Settings.IsStatusBarEnabled = false;

        WebView.Source = new Uri(_appUrl);
    }

    private void OnNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        // Allow only localhost navigation.
        if (!e.Uri.StartsWith("http://127.0.0.1") && !e.Uri.StartsWith("about:"))
        {
            e.Cancel = true;
        }
    }

    private void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        // Hide the loading overlay once Streamlit has loaded.
        Dispatcher.Invoke(() => LoadingOverlay.Visibility = Visibility.Collapsed);
    }

    private void OnWindowClosing(object? sender, CancelEventArgs e)
    {
        ((App)Application.Current).ProcessManager?.Dispose();
    }
}

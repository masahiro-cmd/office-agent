using System.Windows;
using OfficeAgent.Wpf.Services;

namespace OfficeAgent.Wpf;

public partial class App : Application
{
    internal ProcessManager? ProcessManager { get; private set; }

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // Show splash immediately; startup checks run inside it.
        var splash = new SplashWindow();
        splash.Show();
        MainWindow = splash;
    }

    protected override void OnExit(ExitEventArgs e)
    {
        ProcessManager?.Dispose();
        base.OnExit(e);
    }
}

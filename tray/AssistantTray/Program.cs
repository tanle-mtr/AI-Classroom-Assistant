using System.Diagnostics;
using System.Text;
using System.Windows.Forms;

namespace AssistantTray;

/// <summary>托盘入口：单实例 + 常驻。</summary>
internal static class Program
{
    [STAThread]
    private static void Main()
    {
        using var mutex = new Mutex(true, "AI_Classroom_Assistant_Tray", out var createdNew);
        if (!createdNew)
        {
            // 已有一个托盘实例，静默退出（v1 教训：避免多实例自愈打架）
            return;
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new TrayContext());
    }
}

/// <summary>托盘上下文：图标、菜单、进程守护（核心 + 桥）。</summary>
internal class TrayContext : ApplicationContext
{
    private readonly NotifyIcon _tray;
    private readonly ToolStripMenuItem _miAutoStart;
    private readonly string _root = ResolveRoot();
    private Process? _coreProc;
    private Process? _bridgeProc;
    private PanelForm? _panel;
    private readonly System.Threading.Timer _guardTimer;
    private int _corePort = 18760;

    /// <summary>从可执行目录向上查找项目根（兼容 bin/publish 两种布局）。</summary>
    internal static string ResolveRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; i < 8 && dir is not null; i++)
        {
            if (File.Exists(Path.Combine(dir.FullName, "core", "main.py")))
                return dir.FullName;
            dir = dir.Parent;
        }
        return Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
    }

    public TrayContext()
    {
        _tray = new NotifyIcon
        {
            Icon = LoadIcon(),
            Text = "AI 课堂助手",
            Visible = true,
        };

        // 关机拦截：先导出监控/总结，再放行系统关机
        Microsoft.Win32.SystemEvents.SessionEnding += OnSessionEnding;

        var menu = new ContextMenuStrip();
        _miAutoStart = new ToolStripMenuItem("开机自启：开", null, OnToggleAutoStart);
        menu.Items.Add(new ToolStripMenuItem("打开面板", null, OnOpenPanel));
        menu.Items.Add(new ToolStripMenuItem("打开控制台", null, (_, _) => OpenBrowser()));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(_miAutoStart);
        menu.Items.Add(new ToolStripMenuItem("重启核心", null, (_, _) => RestartCore()));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(new ToolStripMenuItem("退出", null, OnExit));
        _tray.ContextMenuStrip = menu;
        _tray.DoubleClick += (_, _) => OnOpenPanel(menu, EventArgs.Empty);

        // 启动守护
        _guardTimer = new System.Threading.Timer(_ => GuardLoop(), null, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(5));
        _ = Task.Run(Bootstrap);
    }

    /// <summary>启动核心与桥（后台，不阻塞 UI）。</summary>
    private async Task Bootstrap()
    {
        // 1) 核心：找正在监听的端口；没有则拉起新核心到 18760
        _corePort = FindCorePort();
        if (_corePort == 0)
        {
            _corePort = 18760;
            _coreProc = StartCore();
            await WaitPortAsync(_corePort, 30);
        }
        // 2) 桥：ClassIsland 启用时拉起
        _bridgeProc = StartBridge();
        // 3) 刷新自启菜单状态
        UpdateAutoStartMenu();
    }

    private void GuardLoop()
    {
        try
        {
            if (_coreProc is { HasExited: true } || (_coreProc is null && !PortInUse(_corePort)))
            {
                _coreProc = StartCore();
            }
            if (_bridgeProc is { HasExited: true })
            {
                _bridgeProc = StartBridge();
            }
        }
        catch { /* 守护失败静默，下轮重试 */ }
    }

    private Process? StartCore()
    {
        try
        {
            var coreMain = Path.Combine(_root, "core", "main.py");
            // 1) 打包版优先（dist/AI课堂助手Core.exe）
            var distExe = Path.Combine(_root, "dist", "AI课堂助手Core.exe");
            if (File.Exists(distExe))
            {
                var psi = new ProcessStartInfo
                {
                    FileName = distExe,
                    Arguments = $"--port {_corePort}",
                    WorkingDirectory = Path.GetDirectoryName(distExe)!,
                    WindowStyle = ProcessWindowStyle.Hidden,
                    CreateNoWindow = true,
                    UseShellExecute = false,
                };
                return Process.Start(psi);
            }
            // 2) 开发环境：Doubao sandbox pythonw
            var sandboxPyw = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Doubao", "User Data", "sandbox_runtime", "bases",
                "c98c5042338ed152c6f10ecd8591889f", "python", "pythonw.exe");
            // 3) 用户机器：系统 pythonw
            var sysPyw = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs", "Python", "Python314", "pythonw.exe");
            foreach (var pyw in new[] { sandboxPyw, sysPyw })
            {
                if (!File.Exists(pyw)) continue;
                var psi = new ProcessStartInfo
                {
                    FileName = pyw,
                    Arguments = $"\"{coreMain}\" --port {_corePort}",
                    WorkingDirectory = Path.Combine(_root, "core"),
                    WindowStyle = ProcessWindowStyle.Hidden,
                    CreateNoWindow = true,
                    UseShellExecute = false,
                };
                return Process.Start(psi);
            }
            return null;
        }
        catch { return null; }
    }

    private Process? StartBridge()
    {
        try
        {
            var bridgeExe = Path.Combine(_root, "bridge", "ClassIslandBridge", "bin",
                "Release", "net8.0-windows", "ClassIslandBridge.exe");
            if (!File.Exists(bridgeExe)) return null;
            var psi = new ProcessStartInfo
            {
                FileName = bridgeExe,
                WorkingDirectory = Path.GetDirectoryName(bridgeExe)!,
                WindowStyle = ProcessWindowStyle.Hidden,
                CreateNoWindow = true,
                UseShellExecute = false,
            };
            return Process.Start(psi);
        }
        catch { return null; }
    }

    private void RestartCore()
    {
        try { _coreProc?.Kill(); } catch { }
        _coreProc = StartCore();
    }

    private void OnOpenPanel(object? sender, EventArgs e)
    {
        if (_panel is { IsDisposed: false })
        {
            _panel.Show();
            _panel.Activate();
            return;
        }
        _panel = new PanelForm(_corePort);
        _panel.Closed += (_, _) => _panel = null;
        _panel.Show();
    }

    private void OpenBrowser()
    {
        try { Process.Start(new ProcessStartInfo($"http://127.0.0.1:{_corePort}/") { UseShellExecute = true }); }
        catch { }
    }

    private void OnToggleAutoStart(object? sender, EventArgs e)
    {
        var startMenuPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Startup), "AI课堂助手.lnk");
        if (File.Exists(startMenuPath))
        {
            try { File.Delete(startMenuPath); } catch { }
        }
        else
        {
            var trayExe = Path.Combine(AppContext.BaseDirectory, "AssistantTray.exe");
            if (File.Exists(trayExe)) CreateShortcut(startMenuPath, trayExe);
        }
        UpdateAutoStartMenu();
    }

    private void UpdateAutoStartMenu()
    {
        var startMenuPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Startup), "AI课堂助手.lnk");
        _miAutoStart.Text = File.Exists(startMenuPath) ? "开机自启：关" : "开机自启：开";
    }

    private void OnExit(object? sender, EventArgs e)
    {
        _guardTimer.Dispose();
        _tray.Visible = false;
        Microsoft.Win32.SystemEvents.SessionEnding -= OnSessionEnding;
        try { _coreProc?.Kill(); } catch { }
        try { _bridgeProc?.Kill(); } catch { }
        Application.Exit();
    }

    /// <summary>系统关机/注销前：调用核心导出接口（最多等待 25 秒），然后放行。</summary>
    private void OnSessionEnding(object sender, Microsoft.Win32.SessionEndingEventArgs e)
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(25) };
            _ = http.PostAsync($"http://127.0.0.1:{_corePort}/api/monitor/export", null).Result;
        }
        catch { /* 核心未运行则不阻塞关机 */ }
        e.Cancel = false;   // 完成导出后放行关机
    }

    private static Icon LoadIcon()
    {
        var ico = Path.Combine(ResolveRoot(), "icons", "app.ico");
        if (File.Exists(ico)) return new Icon(ico);
        return SystemIcons.Application;
    }

    private static void CreateShortcut(string linkPath, string target)
    {
        var workDir = Path.GetDirectoryName(target)!.Replace("'", "''");
        var script = $"$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut('{linkPath.Replace("'", "''")}'); $lnk.TargetPath = '{target.Replace("'", "''")}'; $lnk.WorkingDirectory = '{workDir}'; $lnk.Description = 'AI 课堂助手（开机自启）'; $lnk.Save()";
        try
        {
            Process.Start(new ProcessStartInfo("powershell",
                $"-NoProfile -ExecutionPolicy Bypass -Command \"{script}\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
            });
        }
        catch { }
    }

    /// <summary>找正在监听的端口（核心所在）；无核心运行返回 0。</summary>
    private static int FindCorePort()
    {
        for (var p = 18760; p < 18780; p++)
            if (PortInUse(p)) return p;
        return 0;
    }

    private static bool PortInUse(int port)
    {
        try
        {
            using var tcp = new System.Net.Sockets.TcpClient();
            var task = tcp.ConnectAsync("127.0.0.1", port);
            return task.Wait(300) && tcp.Connected;
        }
        catch { return false; }
    }

    private static async Task WaitPortAsync(int port, int seconds)
    {
        for (var i = 0; i < seconds * 2; i++)
        {
            if (PortInUse(port)) return;
            await Task.Delay(500);
        }
    }
}

using System.Diagnostics;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

namespace AssistantTray;

/// <summary>
/// 系统托盘：开机静默常驻，守护核心/桥进程，右键菜单，关机导出拦截。
/// </summary>
internal static class Program
{
    private static string _root = "";
    private static int _corePort = 18760;
    private static Process? _coreProc;
    private static Process? _bridgeProc;
    private static Form? _panel;
    private static NotifyIcon _tray = null!;
    private static DateTime _lastExport = DateTime.MinValue;

    [STAThread]
    private static void Main()
    {
        using var mutex = new Mutex(true, "AssistantTray.SingleInstance", out var createdNew);
        if (!createdNew) return;
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        _root = FindProjectRoot();
        if (string.IsNullOrEmpty(_root))
        {
            MessageBox.Show("未找到项目目录（AI课堂助手）", "AI 课堂助手",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        _tray = BuildTray();
        _corePort = FindCorePort();
        GuardLoop();          // 后台守护：核心/桥 不在就拉起

        Application.Run();
    }

    private static string FindProjectRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; i < 6; i++)
        {
            if (dir != null && Directory.Exists(Path.Combine(dir.FullName, "core")) &&
                Directory.Exists(Path.Combine(dir.FullName, "data")))
                return dir.FullName;
            dir = dir?.Parent;
        }
        return "";
    }

    private static NotifyIcon BuildTray()
    {
        var icon = LoadIcon();
        var tray = new NotifyIcon
        {
            Icon = icon,
            Text = "AI 课堂助手（监听 ClassIsland）",
            Visible = true,
        };
        var menu = new ContextMenuStrip();
        menu.Items.Add("📊 打开控制台", null, (_, _) => OpenPanel());
        menu.Items.Add("🖥 打开面板", null, (_, _) => OpenPanel("panel.html"));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("🔄 重启核心", null, (_, _) => RestartCore());
        menu.Items.Add("💾 立即导出", null, (_, _) => ExportNow());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("⚙ 开机自启", null, (_, _) => ToggleAutostart());
        menu.Items.Add("❌ 退出", null, (_, _) => ExitApp());
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += (_, _) => OpenPanel();
        return tray;
    }

    private static Icon LoadIcon()
    {
        var ico = Path.Combine(_root, "icons", "app.ico");
        if (File.Exists(ico)) return new Icon(ico);
        return SystemIcons.Application;
    }

    private static void GuardLoop()
    {
        var t = new Thread(() =>
        {
            while (true)
            {
                try
                {
                    if (!PortInUse(_corePort))
                        _coreProc = StartCore();
                    if (_bridgeProc == null || _bridgeProc.HasExited)
                        _bridgeProc = StartBridge();
                }
                catch { /* 守护循环不中断 */ }
                Thread.Sleep(5000);
            }
        });
        t.IsBackground = true;
        t.Start();
    }

    private static int FindCorePort()
    {
        for (var p = 18760; p <= 18779; p++)
        {
            if (PortInUse(p)) return p;
        }
        return 18760;
    }

    private static bool PortInUse(int port)
    {
        using var c = new TcpClient();
        try { c.Connect("127.0.0.1", port); return true; }
        catch { return false; }
    }

    private static Process? StartCore()
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

    private static Process? StartBridge()
    {
        try
        {
            var exe = Path.Combine(_root, "bridge", "ClassIslandBridge", "bin", "Release",
                "net8.0-windows", "ClassIslandBridge.exe");
            if (!File.Exists(exe)) return null;
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                WorkingDirectory = Path.GetDirectoryName(exe)!,
                WindowStyle = ProcessWindowStyle.Hidden,
                CreateNoWindow = true,
                UseShellExecute = false,
            };
            return Process.Start(psi);
        }
        catch { return null; }
    }

    private static void OpenPanel(string page = "")
    {
        try
        {
            var url = $"http://127.0.0.1:{_corePort}/{page}";
            if (_panel is null || _panel.IsDisposed)
            {
                _panel = new PanelForm(url);
                _panel.FormClosed += (_, _) => _panel = null;
                _panel.Show();
            }
            else
            {
                _panel.Activate();
            }
        }
        catch { Process.Start("http://127.0.0.1:" + _corePort + "/"); }
    }

    private static void RestartCore()
    {
        if (_coreProc != null)
        {
            try { _coreProc.Kill(); } catch { }
        }
        foreach (var p in Process.GetProcessesByName("pythonw"))
        {
            try { if (p.MainWindowTitle.Length == 0 && p.PathContains(_root)) p.Kill(); } catch { }
        }
        _coreProc = StartCore();
    }

    private static void ExportNow()
    {
        if ((DateTime.Now - _lastExport).TotalSeconds < 20) return;
        _lastExport = DateTime.Now;
        var t = new Thread(() =>
        {
            try
            {
                using var c = new HttpClient();
                var resp = c.PostAsync($"http://127.0.0.1:{_corePort}/api/monitor/export", null).Result;
                resp.EnsureSuccessStatusCode();
                _tray.ShowBalloonTip(3000, "AI 课堂助手", "导出完成（监控+总结+座位表）", ToolTipIcon.Info);
            }
            catch (Exception ex)
            {
                _tray.ShowBalloonTip(3000, "AI 课堂助手", $"导出失败: {ex.Message}", ToolTipIcon.Error);
            }
        });
        t.IsBackground = true;
        t.Start();
    }

    private static void ToggleAutostart()
    {
        try
        {
            var startup = Environment.GetFolderPath(Environment.SpecialFolder.Startup);
            var lnk = Path.Combine(startup, "AI课堂助手.lnk");
            if (File.Exists(lnk))
            {
                File.Delete(lnk);
                _tray.ShowBalloonTip(2000, "AI 课堂助手", "已关闭开机自启", ToolTipIcon.Info);
            }
            else
            {
                var ws = new COMObject("WScript.Shell");
                var shortcut = ws.CreateShortcut(lnk);
                shortcut.TargetPath = Environment.ProcessPath!;
                shortcut.WorkingDirectory = AppContext.BaseDirectory;
                shortcut.Save();
                _tray.ShowBalloonTip(2000, "AI 课堂助手", "已开启开机自启", ToolTipIcon.Info);
            }
        }
        catch (Exception ex)
        {
            _tray.ShowBalloonTip(2000, "AI 课堂助手", $"自启设置失败: {ex.Message}", ToolTipIcon.Error);
        }
    }

    private static void ExitApp()
    {
        ExportNow();
        _tray.Visible = false;
        _tray.Dispose();
        _panel?.Close();
        Application.Exit();
    }

    private static COMObject COMObject(string progId)
    {
        var t = Type.GetTypeFromProgID(progId)!;
        return new COMObject(Activator.CreateInstance(t)!);
    }
}

internal class COMObject
{
    private readonly object _obj;
    public COMObject(object obj) => _obj = obj;
    public dynamic CreateShortcut(string path) => ((dynamic)_obj).CreateShortcut(path);
}

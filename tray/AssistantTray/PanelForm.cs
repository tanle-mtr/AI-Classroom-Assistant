using Microsoft.Web.WebView2.WinForms;

namespace AssistantTray;

/// <summary>
/// 桌面面板：WebView2 内嵌 Web 控制台/面板页（深蓝主题）。
/// </summary>
internal class PanelForm : Form
{
    public PanelForm(string url)
    {
        Text = "AI 课堂助手";
        Width = 1280;
        Height = 800;
        StartPosition = FormStartPosition.CenterScreen;
        var web = new WebView2
        {
            Dock = DockStyle.Fill,
        };
        Controls.Add(web);
        _ = InitAsync(web, url);
    }

    private static async Task InitAsync(WebView2 web, string url)
    {
        try
        {
            await web.EnsureCoreWebView2Async();
            web.CoreWebView2.Settings.AreDevToolsEnabled = false;
            web.CoreWebView2.Navigate(url);
        }
        catch
        {
            // WebView2 不可用时退回浏览器
            System.Diagnostics.Process.Start(url);
        }
    }
}

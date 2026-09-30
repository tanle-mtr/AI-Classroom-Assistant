using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace ClassIslandBridge;

/// <summary>
/// ClassIsland 官方 IPC 桥：订阅课程事件 → POST 到 AI 课堂助手核心。
/// 反射激活编译好的服务代理（避免直接引用内部类型），单实例 Mutex 防重复。
/// </summary>
internal static class Program
{
    private const string IpcNamespace = "ClassIsland.Shared.IPC";
    private const string ProxyTypeName = "__IPublicLessonsServiceIpcProxy";

    [STAThread]
    private static void Main()
    {
        using var mutex = new Mutex(true, "ClassIslandBridge.SingleInstance", out var createdNew);
        if (!createdNew) return;
        try
        {
            var asm = Assembly.Load(IpcNamespace);
            var proxyType = asm.GetType($"{IpcNamespace}.{ProxyTypeName}")
                            ?? asm.GetTypes().FirstOrDefault(t => t.Name == ProxyTypeName);
            if (proxyType == null)
            {
                Log("IPC 代理类型未找到，请确认 ClassIsland.Shared.IPC 版本");
                return;
            }

            var proxy = Activator.CreateInstance(proxyType);
            var events = proxyType.GetEvents();
            var lessonStarted = events.FirstOrDefault(e => e.Name.Contains("Started"));
            var lessonEnded = events.FirstOrDefault(e => e.Name.Contains("Ended"));
            if (lessonStarted != null)
                AddHandler(proxy, lessonStarted, () => Post("started", null));
            if (lessonEnded != null)
                AddHandler(proxy, lessonEnded, () => Post("ended", null));

            Log("桥已启动，等待 ClassIsland 课程事件…");
            while (true) Thread.Sleep(TimeSpan.FromHours(1));
        }
        catch (Exception ex)
        {
            Log($"桥运行错误: {ex.Message}");
        }
    }

    private static void AddHandler(object target, EventInfo evt, Action action)
    {
        try
        {
            // 事件委托签名不固定：用反射动态构造包装器
            var invoke = evt.EventHandlerType!.GetMethod("Invoke")!;
            var ps = invoke.GetParameters();
            var dm = new DynamicMethod("handler", typeof(void),
                ps.Select(p => p.ParameterType).ToArray());
            var il = dm.GetILGenerator();
            il.Emit(System.Reflection.Emit.OpCodes.Call, typeof(Action).GetMethod("Invoke")!);
            il.Emit(System.Reflection.Emit.OpCodes.Ret);
            var handler = dm.CreateDelegate(evt.EventHandlerType!);
            evt.AddEventHandler(target, handler);
        }
        catch (Exception ex)
        {
            Log($"事件订阅失败: {ex.Message}");
        }
    }

    private static void Post(string eventName, object? lesson)
    {
        try
        {
            var port = FindCorePort();
            if (port <= 0) { Log("核心端口未找到"); return; }
            var payload = JsonSerializer.Serialize(new { @event = eventName, lesson });
            using var client = new TcpClient();
            client.Connect("127.0.0.1", port);
            var body = Encoding.UTF8.GetBytes($"POST /api/events/lesson HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: {payload.Length}\r\nConnection: close\r\n\r\n{payload}");
            client.GetStream().Write(body, 0, body.Length);
            Log($"已推送课程事件: {eventName}");
        }
        catch (Exception ex)
        {
            Log($"推送失败: {ex.Message}");
        }
    }

    private static int FindCorePort()
    {
        try
        {
            var listener = System.Net.Sockets.TcpListener.Create(0);
            listener.Start();
            var port = ((System.Net.IPEndPoint)listener.LocalEndpoint).Port;
            listener.Stop();
            // 探测 18760-18779 哪个在监听（核心端口顺延逻辑）
            for (var p = 18760; p <= 18779; p++)
            {
                using var probe = new TcpClient();
                try { probe.Connect("127.0.0.1", p); return p; }
                catch { /* 尝试下一个 */ }
            }
        }
        catch { /* 忽略 */ }
        return 0;
    }

    private static void Log(string msg)
    {
        try
        {
            var dir = Path.Combine(Environment.CurrentDirectory, "..", "..", "..", "..", "data", "logs");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "bridge.log"),
                $"[{DateTime.Now:HH:mm:ss}] {msg}{Environment.NewLine}", Encoding.UTF8);
        }
        catch { /* 日志失败不影响运行 */ }
    }
}

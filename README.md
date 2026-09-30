# AI 课堂助手（AI Classroom Assistant）

一款 Windows 常驻托盘的 AI 教学辅助工具：监听 **ClassIsland** 官方课程事件，自动感知课堂（麦克风/摄像头/屏幕，共享不独占），下课自动生成课堂总结（Markdown，分课型路由），按课程切片录制监控，座位表识图与换座检测，并可通过 **Cloudflare 隧道 + OpenList** 在其他电脑远程访问导出文件。

> 模型完全由本地 **Ollama** 提供，数据全部保存在本地，无云端上传。

## ✨ 功能特性

| 能力 | 说明 |
|---|---|
| 🎓 ClassIsland 集成 | 官方 `ClassIsland.Shared.IPC` 订阅上课/下课/课间事件，无需改 ClassIsland |
| 🧠 课堂感知 | 麦克风（WASAPI 共享）、摄像头（MediaFoundation 共享）、屏幕活跃度，**不独占设备** |
| 📊 拖堂检测 | 纯视觉判定：屏幕持续活跃 + 摄像头见多数学生未离座（麦克风不参与） |
| 📝 课堂总结 | 下课自动生成 Markdown：老师总结（课堂质量/细讲/缩短建议）+ 学生总结（重难点） |
| 🧭 分课型路由 | 新授课（总结+导学案+思维导图）/ 讲评课（总结+变式练习）/ 考试自习（分贝折线报告） |
| 🎬 课堂监控 | 默认开启，按课程切片录制（视频+音频），14 天滚动保留，关机自动导出 |
| 🪑 座位表 | 图片上传 → 视觉模型解析姓名布局；上课自动检测换座并提示更新，可导出 |
| 🛠 内置 Skills | 纯文本 AI 识图（调视觉模型）、Markdown 编写规范，可热加载自定义 skill |
| 🌐 远程访问 | Cloudflare 隧道（免 VPS）+ OpenList 文件浏览，自动查询公网 IP |
| 📂 课件上传 | 按科目自动分类建文件夹，无口令，老师可直接传课件到本机 |

## 🧩 技术栈（多语言）

| 组件 | 语言/技术 | 职责 |
|---|---|---|
| `core/` | Python + FastAPI | 事件总线、状态机、感知/产出/监控/远程引擎 |
| `bridge/` | C# (dotnet 8) | ClassIsland 官方 IPC 桥（无窗口） |
| `tray/` | C# WinForms | 系统托盘、开机自启、进程守护、关机导出拦截 |
| `webui/` | Vue 3 + Vite | Web 控制台 + 桌面面板 |
| `scripts/` | PowerShell | 启动/停止/自启/关机导出/打包 |

## 🚀 快速开始

### 依赖
- Windows 10/11（x64）
- [ClassIsland](https://github.com/ClassIsland/ClassIsland)（课程事件来源，已开启本机 IPC）
- [Ollama](https://ollama.com/)（本地模型，启动后软件自动探测可用模型并让你选择）
- .NET 8 Runtime（托盘/桥）
- WebView2 Runtime（面板，Windows 11 一般自带）

### 运行
```powershell
scripts\start.ps1
# 或直接运行打包产物：
dist\AI课堂助手Core.exe
tray\AssistantTray\bin\Release\net8.0-windows\publish\AssistantTray.exe
```

首次打开：在 Web 控制台（`http://127.0.0.1:18760`）设置 Ollama 模型、上传座位表、配置 Cloudflare 隧道 token。

### 打包 exe
```powershell
scripts\build_exe.ps1
```

## ⚖️ 许可证

[MIT](LICENSE)
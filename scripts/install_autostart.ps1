# AI 课堂助手 · 开机自启安装脚本
# 用法：powershell -ExecutionPolicy Bypass -File install_autostart.ps1
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$trayExe = Join-Path $root "tray\AssistantTray\bin\Release\net8.0-windows\publish\AssistantTray.exe"
if (-not (Test-Path $trayExe)) { Write-Error "托盘程序不存在，请先编译"; exit 1 }

$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "AI课堂助手.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $trayExe
$s.WorkingDirectory = Split-Path $trayExe
$s.Description = "AI 课堂助手（开机自启）"
$s.Save()
Write-Host "开机自启已安装：$lnk"

# 桌面快捷方式
$desktop = [Environment]::GetFolderPath("Desktop")
$dlnk = Join-Path $desktop "AI课堂助手.lnk"
if (-not (Test-Path $dlnk)) {
    $s2 = $ws.CreateShortcut($dlnk)
    $s2.TargetPath = $trayExe
    $s2.WorkingDirectory = Split-Path $trayExe
    $s2.Description = "AI 课堂助手"
    $s2.Save()
    Write-Host "桌面快捷方式已创建"
}

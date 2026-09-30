# AI 课堂助手 · 启动脚本
# 用法：powershell -ExecutionPolicy Bypass -File start.ps1
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# 核心：pythonw 无窗口启动
$pyw = Join-Path $env:LOCALAPPDATA "Doubao\User Data\sandbox_runtime\bases\c98c5042338ed152c6f10ecd8591889f\python\pythonw.exe"
if (Test-Path $pyw) {
    $coreMain = Join-Path $root "core\main.py"
    if (-not (Get-Process -Name "assistant-core" -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $pyw -ArgumentList "`"$coreMain`"" -WindowStyle Hidden -WorkingDirectory (Join-Path $root "core")
        Write-Host "核心已启动（pythonw 无窗口）"
    }
} else {
    # 打包版
    $coreExe = Join-Path $root "dist\AI课堂助手Core.exe"
    if (Test-Path $coreExe) {
        Start-Process -FilePath $coreExe -WindowStyle Hidden
        Write-Host "核心已启动（打包版）"
    }
}

# 托盘：常驻图标 + 守护
$trayExe = Join-Path $root "tray\AssistantTray\bin\Release\net8.0-windows\publish\AssistantTray.exe"
if (Test-Path $trayExe) {
    Start-Process -FilePath $trayExe -WorkingDirectory (Split-Path $trayExe)
    Write-Host "托盘已启动"
} else {
    Write-Host "未找到托盘程序，请先编译 tray/AssistantTray"
}

Start-Sleep -Seconds 2
Write-Host "控制台：http://127.0.0.1:18760/"

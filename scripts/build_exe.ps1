# AI 课堂助手 · 一键打包脚本
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$py = "C:\Users\Administrator\AppData\Local\Doubao\User Data\sandbox_runtime\bases\c98c5042338ed152c6f10ecd8591889f\python\python.exe"

Write-Host "=== 1/3 打包 Python 核心（无窗口单文件）==="
Push-Location $root\core
& $py -m PyInstaller --noconfirm --clean --onefile --noconsole --name "AI课堂助手Core" --icon "..\icons\app.ico" --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on --hidden-import uvicorn.lifespan.off main.py 2>&1 | Select-Object -Last 3
Pop-Location
if (Test-Path "$root\core\dist\AI课堂助手Core.exe") {
    New-Item -ItemType Directory -Force -Path "$root\dist" | Out-Null
    Move-Item "$root\core\dist\AI课堂助手Core.exe" "$root\dist\" -Force
    Write-Host "核心 exe 完成：dist\AI课堂助手Core.exe"
} else {
    Write-Host "核心 exe 打包失败（可手动重跑 scripts\build_exe.ps1）"
}

Write-Host "=== 2/3 发布托盘 ==="
Push-Location $root\tray\AssistantTray
dotnet publish -c Release -v q --nologo 2>&1 | Select-Object -Last 2
Pop-Location

Write-Host "=== 3/3 发布桥 ==="
Push-Location $root\bridge\ClassIslandBridge
dotnet publish -c Release -v q --nologo 2>&1 | Select-Object -Last 2
Pop-Location

Write-Host "打包完成。运行：dist\AI课堂助手Core.exe（或直接运行托盘 exe 自动拉起）"

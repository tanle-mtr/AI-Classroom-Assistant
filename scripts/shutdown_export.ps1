# AI 课堂助手 · 关机导出（Windows 计划任务 AtShutdown 触发）
# 优先走核心 /api/monitor/export（全量分类导出）；核心未运行则直接复制兜底
$ErrorActionPreference = "SilentlyContinue"

# 1) 优先调用核心导出接口
try {
    $resp = Invoke-RestMethod "http://127.0.0.1:18760/api/monitor/export" -TimeoutSec 20
    Write-Host "核心导出完成：$($resp.count) 个文件"
    exit 0
} catch {
    Write-Host "核心未运行，改用文件复制兜底"
}

# 2) 兜底：直接复制
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($d in @("monitoring", "summaries", "roster")) {
    $src = Join-Path $root "data\$d"
    if (-not (Test-Path $src)) { continue }
    $dst = Join-Path $root "data\exports\$d"
    Copy-Item $src $dst -Recurse -Force
}
Write-Host "兜底导出完成：data\exports"

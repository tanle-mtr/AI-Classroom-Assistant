# AI 课堂助手 · 停止脚本（结束托盘/核心/桥，保留自启设置）
$names = @("AssistantTray", "ClassIslandBridge", "assistant-core", "pythonw", "python")
foreach ($n in $names) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -like "*AI课堂助手*" -or $_.Path -like "*ClassIslandBridge*" } catch { $false }
    } | Stop-Process -Force -ErrorAction SilentlyContinue
}
# 核心端口进程（找不到路径信息时按端口清理）
$conns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -ge 18760 -and $_.LocalPort -le 18779 }
foreach ($c in $conns) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
}
Write-Host "AI 课堂助手已停止"

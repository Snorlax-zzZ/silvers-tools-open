# checkpoint 六件套 — Windows 安装脚本（PowerShell）
#
# 行为：
#   1. 把 prompts/*.md 复制到 ~/.codex/prompts/
#   2. 输出迁移来源的权限参考片段（当前 Codex 桌面环境通常无需手工合并）
#
# 不会自动改任何 Codex 全局配置（避免覆盖现有配置）
#
# 用法：
#   pwsh install/install-windows.ps1
#   或
#   powershell -ExecutionPolicy Bypass -File install\install-windows.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolDir = Split-Path -Parent $ScriptDir
$PromptsSrc = Join-Path $ToolDir "prompts"
$PromptsDst = Join-Path $HOME ".codex\prompts"
$ScriptsSrc = Join-Path $ToolDir "scripts"
$ScriptsDst = Join-Path $HOME ".codex\scripts"
$PermFile = Join-Path $ToolDir "permissions\windows.json"
$CheckpointsDir = Join-Path $HOME ".codex\checkpoints"
$OnlineDir = Join-Path $HOME ".codex\checkpoints-online"
$OnlineRepo = "<CHECKPOINT_REPO_URL>"
$WindowsRuntimeConstraint = @'

<!-- WINDOWS RUNTIME CONSTRAINT (locally injected; do not commit) -->
> **Windows time command (REQUIRED)**: use GNU date from Git Bash:
> `date '+%Y-%m-%dT%H:%M:%S%z'`
> **DO NOT use PowerShell Get-Date or [DateTime]::Now**: cold starts and Defender scanning can cause incompatible output, long delays, or timeouts.
<!-- END WINDOWS RUNTIME CONSTRAINT -->
'@

Write-Host "==> 安装 checkpoint 六件套到 $PromptsDst"

New-Item -ItemType Directory -Path $PromptsDst -Force | Out-Null
New-Item -ItemType Directory -Path $ScriptsDst -Force | Out-Null
New-Item -ItemType Directory -Path $CheckpointsDir -Force | Out-Null

# online 三件套：clone 云端 checkpoint 工作区（已存在则跳过）
# 判据用 <...> 形态而不是占位符字面量：开源导出后用户整包替换占位符时，
# 这行判断不会被一起换掉。真实 Git 地址不会以 "<" 开头。
if ($OnlineRepo -like "<*>") {
    Write-Host "    [skip] 云端仓库地址尚未配置：$OnlineRepo"
    Write-Host "           请先把本包内的 $OnlineRepo 全部替换为你自己的 checkpoint Git 仓库地址，再重跑本脚本。"
    Write-Host "           （只影响 online 三件套；本地三件套不受影响，继续安装）"
} elseif (Test-Path (Join-Path $OnlineDir ".git")) {
    Write-Host "    [skip] 云端工作区已存在：$OnlineDir"
} else {
    Write-Host "==> clone 云端 checkpoint 工作区到 $OnlineDir"
    git clone $OnlineRepo $OnlineDir
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    [ok]   云端工作区就绪"
    } else {
        Write-Host "    [warn] clone 失败（网络 / 仓库访问权限），稍后手动跑：git clone $OnlineRepo $OnlineDir"
    }
}

foreach ($cmd in @("checkpoint.md", "checkpoint-load.md", "task-done.md",
                   "checkpoint-online.md", "checkpoint-load-online.md", "task-done-online.md")) {
    $dst = Join-Path $PromptsDst $cmd
    $src = Join-Path $PromptsSrc $cmd
    Copy-Item $src $dst -Force
    # 每次先以仓库源码覆盖，再追加一次本机约束：重复安装不会累积 marker。
    Add-Content -Path $dst -Value $WindowsRuntimeConstraint -Encoding UTF8
    Write-Host "    [ok]   ${cmd}（已同步最新版本并注入 Windows 取时约束）"
}

Write-Host ""
Write-Host "==> 安装扫描脚本到 $ScriptsDst"
foreach ($sh in @("list-checkpoints.sh")) {
    $src = Join-Path $ScriptsSrc $sh
    $dst = Join-Path $ScriptsDst $sh
    Copy-Item $src $dst -Force
    Write-Host "    [ok]   $sh （Windows 用 git-bash 执行）"
}

Write-Host ""
Write-Host "==> 命令安装完成"
Write-Host ""
Write-Host "==> 权限参考（通常不用手工合并）"
Write-Host ""
Write-Host "下面是从 Claude Code checkpoint 包迁移过来的权限参考。"
Write-Host "当前 Codex 桌面环境通常不需要手工合并；如果你的 Codex 表面支持类似 permissions.allow，再按需参考："
Write-Host ""
Write-Host "----------------------------------------"
Get-Content $PermFile | Write-Host
Write-Host "----------------------------------------"
Write-Host ""
Write-Host "==> 测试"
Write-Host "在 Codex 里跑 /checkpoint 看看能不能用。"

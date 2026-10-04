# checkpoint 三件套 — Windows 安装脚本（PowerShell）
#
# 行为：
#   1. 把 commands/*.md 复制到 ~/.claude/commands/
#   2. 输出权限白名单片段，让用户手动 merge 到 ~/.claude/settings.json
#
# 不会自动改 ~/.claude/settings.json（避免覆盖现有配置）
#
# 用法：
#   pwsh install/install-windows.ps1
#   或
#   powershell -ExecutionPolicy Bypass -File install\install-windows.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolDir = Split-Path -Parent $ScriptDir
$CommandsSrc = Join-Path $ToolDir "commands"
$CommandsDst = Join-Path $HOME ".claude\commands"
$ScriptsSrc = Join-Path $ToolDir "scripts"
$ScriptsDst = Join-Path $HOME ".claude\scripts"
$PermFile = Join-Path $ToolDir "permissions\windows.json"
$CheckpointsDir = Join-Path $HOME ".claude\checkpoints"
$OnlineDir = Join-Path $HOME ".claude\checkpoints-online"
$OnlineRepo = "<CHECKPOINT_REPO_URL>"

Write-Host "==> 安装 checkpoint 三件套到 $CommandsDst"

New-Item -ItemType Directory -Path $CommandsDst -Force | Out-Null
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
    $dst = Join-Path $CommandsDst $cmd
    $src = Join-Path $CommandsSrc $cmd
    if (Test-Path $dst) {
        Write-Host "    [skip] $cmd 已存在（如需覆盖，先手动删除再跑）"
    } else {
        Copy-Item $src $dst
        Write-Host "    [ok]   $cmd"
    }
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
Write-Host "==> 接下来：手动合并权限白名单"
Write-Host ""
Write-Host "把下面这些条目加到 ~/.claude/settings.json 的 permissions.allow 数组里："
Write-Host ""
Write-Host "----------------------------------------"
Get-Content $PermFile | Write-Host
Write-Host "----------------------------------------"
Write-Host ""
Write-Host "完成后，重启 Claude Code 让权限生效。"
Write-Host ""
Write-Host "==> 测试"
Write-Host "在 Claude Code 里跑 /checkpoint 看看能不能用。"

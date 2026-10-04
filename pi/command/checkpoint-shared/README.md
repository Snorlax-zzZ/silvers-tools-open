# pi/command/checkpoint-shared — 公共接力三件套（pi 版）

> 多模型顺序接力同一个任务 + macOS ↔ Windows 跨机器恢复。
> 协议来源：[`shared/command/checkpoint/`](../../../shared/command/checkpoint/)（**唯一权威，不复制正文**）。

## 三条命令

| 命令 | 作用 |
|---|---|
| [`/checkpoint-shared`](commands/checkpoint-shared.md) | 把当前任务状态保存到公共接力区并同步远端 |
| [`/checkpoint-shared-load`](commands/checkpoint-shared-load.md) | 拉取公共接力区，加载一棒并折算当前机器环境 |
| [`/task-done-shared`](commands/task-done-shared.md) | 完成任务，归档公共 checkpoint 并同步远端 |

与本地 checkpoint 三件套**完全并行**：不同命令、不同目录、互不干扰。

## 固定运行时资源

- 远端：`<CHECKPOINT_REPO_URL>`
- 公共工作区：`~/.silvers/checkpoint-shared/`
- 活动：`shared/<project_key>/<checkpoint_id>.md`；已完成：`shared/done/<project_key>/<checkpoint_id>.md`
- 只允许操作 `shared/`；`cc/`、`codex/`、`zcode/` 等目录不在授权范围
- `client_name` 硬编码为 **`pi`**

## 与 cc / grok 版的关键差异：运行时判断而不是安装时裁剪

cc / grok 版要求"安装时把当前平台块内嵌进本机命令，删掉不匹配的块"。pi 版**直接引用本仓库文件，不产生本机副本**，所以：

- 平台差异必须在**运行时判断**（`uname -s` / `$OSTYPE` / 是否存在 Git Bash）
- 三条模板同时带 mac 与 windows 约束，执行时只应用匹配的那一组
- 这是 pi"能引用不复制"带来的必然适配，不是偷懒

## 安装

1. 装扫描脚本到 pi 的稳定脚本目录：

```bash
mkdir -p ~/.pi/agent/scripts
cp <SILVERS_TOOLS>/shared/command/checkpoint/scripts/list-shared-checkpoints.sh ~/.pi/agent/scripts/
chmod +x ~/.pi/agent/scripts/list-shared-checkpoints.sh
bash -n ~/.pi/agent/scripts/list-shared-checkpoints.sh
```

2. clone 公共工作区（**不复用任何客户端的 `checkpoints-online`**）：

```bash
git clone <CHECKPOINT_REPO_URL> "$HOME/.silvers/checkpoint-shared"
```

3. 把本目录 `commands/` 加进 `settings.prompts`，替换模板里的 `<SILVERS_TOOLS>`，`/reload`。

windows：脚本在 **Git Bash** 下跑；禁止 PowerShell `Get-Date` / `[DateTime]::Now`。

## 安装验收

- 三条命令能在 pi 原生入口发现
- 均指向 `~/.silvers/checkpoint-shared/`，无旧 `checkpoints-online` 路径
- scan 脚本在临时 `$HOME` fixture 里能列 `shared/` 活动项并排除 `shared/done/`
- 平台约束已进入命令执行逻辑（不是只写在 README）
- 冒烟**不得向真实远端 push fixture**

完整协议与状态流以 [`shared/command/checkpoint/design.md`](../../../shared/command/checkpoint/design.md) 为准。

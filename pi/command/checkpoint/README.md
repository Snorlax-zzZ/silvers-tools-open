# pi/command/checkpoint — 本地 checkpoint 三件套（pi 版）

> 长任务跨会话续命，省 token。`/checkpoint` + `/checkpoint-load` + `/task-done`。
> 从 [`cc/command/checkpoint/`](../../../cc/command/checkpoint/) 适配：协议照旧，存储根和运行时换到 pi。

## 用途

长任务跑到 200k+ token 时，`/compact` 不省 token（那一刀消耗 ≈ 全部历史 + 摘要）。真正省 token 的姿势是：**主动归档成精简文档 → 开新会话 → `/checkpoint-load` 续命**。原理见 cc 版 [`design.md`](../../../cc/command/checkpoint/README.md)。

## 三条命令

| 命令 | 作用 | 参数 |
|---|---|---|
| [`/checkpoint`](commands/checkpoint.md) | 把当前会话状态归档成 3-5k token 的精简文档 | `[已有路径]` |
| [`/checkpoint-load`](commands/checkpoint-load.md) | 新会话里加载一份 checkpoint 继续 | `[路径]` |
| [`/task-done`](commands/task-done.md) | 任务完成，归档到 `done/` 子目录 | `[路径]` |

存储：`~/.pi/agent/checkpoints/<项目目录名>/YYYYMMDD-HHMMSS-<中文slug>.md`（**不跟 cc 抢 `~/.claude/checkpoints/`**）。

## 与 cc 版的差异

| 维度 | cc 版 | pi 版 |
|---|---|---|
| 存储根 | `~/.claude/checkpoints/` | `~/.pi/agent/checkpoints/` |
| 扫描脚本 | `~/.claude/scripts/list-checkpoints.sh` | `~/.pi/agent/scripts/list-checkpoints.sh` |
| 参数 | `$ARGUMENTS` | `$@` |
| 权限 | settings allowlist | pi 无权限弹窗 |
| 协议正文 | cc 目录原文 | **引用 cc 原文，不复制** |

frontmatter 字段、slug 规则、真实取时、正文结构、done/ 归档规则**全部保留**。

## 安装（mac / windows 同一步）

1. 装扫描脚本：

```bash
mkdir -p ~/.pi/agent/scripts
sed 's|\.claude/checkpoints|.pi/agent/checkpoints|g' "<SILVERS_TOOLS>/cc/command/checkpoint/scripts/list-checkpoints.sh" > ~/.pi/agent/scripts/list-checkpoints.sh
chmod +x ~/.pi/agent/scripts/list-checkpoints.sh
```

扫描器的存储根在安装副本中改为 `~/.pi/agent/checkpoints/`；只换安装目录不换脚本里的根目录，会误读 cc 存档。源码仍复用同一份扫描实现。本套件只使用其本地扫描模式。

2. 把本目录的 `commands/` 加进 `~/.pi/agent/settings.json` 的 `prompts` 数组（填写本机绝对路径）。

3. 把三条命令模板里的 `<SILVERS_TOOLS>` 替换为本机仓库路径（必须填写工具仓库的真实绝对路径）。

4. `/reload`，验证 `/checkpoint` 能被发现。

windows 追加：脚本在 Git Bash 下跑；`~` 用 `$HOME` 或绝对路径。

## 何时装 / 不装

| 场景 | 建议 |
|---|---|
| 经常跑 100k+ token 长任务 | ✅ 装 |
| 基本短任务 | ❌ 不装也行 |

## 验证

1. `/reload` 后 `/checkpoint` `/checkpoint-load` `/task-done` 在命令补全里可见
2. `~/.pi/agent/scripts/list-checkpoints.sh --help` 正常
3. 用临时目录跑一次 `/checkpoint`，确认文件落在 `~/.pi/agent/checkpoints/` 而不是 `~/.claude/checkpoints/`

# Grok 本地 checkpoint 三件套

协议来自 `cc/command/checkpoint/`，存储改到 `~/.grok/checkpoints/`。

| 命令 | 作用 |
|---|---|
| `/checkpoint` | 归档当前会话到 `~/.grok/checkpoints/<项目slug>/` |
| `/checkpoint-load` | 读档续命 |
| `/task-done` | 把当前 checkpoint 移到 `done/` |

本目录 `commands/` 已是 Grok 适配文件，安装到 `~/.grok/commands/`。不要从 `~/.claude/commands/` 复制。

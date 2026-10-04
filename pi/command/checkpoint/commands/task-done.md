---
description: 任务完成，把当前 checkpoint 归档到 done/ 子目录（pi 版）
argument-hint: "[checkpoint 路径]"
---
任务完成，把 checkpoint 归档到 `done/`，可追溯。

## 权威协议（执行前必须完整读取）

1. `<SILVERS_TOOLS>/cc/command/checkpoint/README.md` —— 唯一权威
2. `<SILVERS_TOOLS>/cc/command/checkpoint/commands/task-done.md` —— 执行步骤原文

`<SILVERS_TOOLS>` 必须填写工具仓库的真实绝对路径，安装时替换。文件缺失时停止并提示。

## pi 侧替换（逐条覆盖 cc 原文）

| 维度 | cc 原文 | pi 执行 |
|---|---|---|
| 自称 | 你（cc） | pi |
| 存储根 | `~/.claude/checkpoints/` | `~/.pi/agent/checkpoints/` |
| 参数 | `$ARGUMENTS` | `$@` |
| 工具名 | Read / Bash | `read` / `bash` |
| 权限 | settings allowlist | pi 无权限弹窗 |

## 执行要点

1. 确定要归档的 checkpoint（`$@` 优先；否则用本对话记住的路径；都没有就先列候选让用户选）
2. 按协议把文件从 `~/.pi/agent/checkpoints/<项目目录名>/` 移到 `done/` 子目录
3. 更新 frontmatter `status: done` 并刷新 `updated_at`（新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`）
4. 移动后确认原路径不再有该文件，汇报归档后路径

## 强制约束

- 只归档本项目的 checkpoint，不碰其他项目
- 不删除 `done/` 里的历史归档
- 找不到目标文件时停止并列出候选，不得猜

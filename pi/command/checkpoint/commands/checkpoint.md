---
description: 把当前会话状态归档成精简 checkpoint 文档，供新会话接力（pi 版）
argument-hint: "[已有 checkpoint 路径]"
---
把当前会话状态归档成精简 checkpoint 文档，供后续会话接力。

## 权威协议（执行前必须完整读取）

本命令是 pi 对 cc checkpoint 协议的**薄适配**，协议正文不复制。先读：

1. `<SILVERS_TOOLS>/cc/command/checkpoint/README.md` —— 协议与原理，**唯一权威**
2. `<SILVERS_TOOLS>/cc/command/checkpoint/commands/checkpoint.md` —— 执行步骤原文

`<SILVERS_TOOLS>` = 本仓库本机 clone 路径，安装时替换；必须填写工具仓库的真实绝对路径。文件不存在时停止并提示先 clone / 填对路径。

## pi 侧替换（逐条覆盖 cc 原文）

| 维度 | cc 原文 | pi 执行 |
|---|---|---|
| 自称 | 你（cc） | pi |
| 存储根 | `~/.claude/checkpoints/` | `~/.pi/agent/checkpoints/` |
| 参数 | `$ARGUMENTS` | `$@`（本命令的可选路径参数） |
| 工具名 | Read / Write / Edit / Bash | `read` / `write` / `edit` / `bash` |
| 权限 | settings allowlist | pi 无权限弹窗，直接执行；遇真实拒绝才停 |
| 扫描脚本 | `~/.claude/scripts/list-checkpoints.sh` | `~/.pi/agent/scripts/list-checkpoints.sh` |

除上述替换外，**frontmatter 字段、文件名 slug 规则、真实取时、正文结构、done/ 归档规则全部保留**，不得简化或省略。

## 强制约束

- 写入前必须新执行一次 `date '+%Y-%m-%dT%H:%M:%S%z'`；`updated_at` 用这次的值，**禁止复用对话里的任何旧时间戳**
- 目标文件必须落在 `~/.pi/agent/checkpoints/<项目目录名>/`，`<项目目录名>` = 当前工作目录绝对路径把 `/` 换成 `-`
- 首次创建后文件名固定；更新只改内容，不改文件名
- 不写 token / 密码 / Cookie / 私钥 / 完整 `.env`；敏感值替换成 `<REDACTED>`
- 不复制完整聊天记录 / 完整 diff / 大段源码
- 写入用原子替换（先写临时文件再覆盖），失败保留原文件

## 参数

`$@` = 可选。传入时视为已有 checkpoint 路径，做覆盖更新；为空则按协议新建。

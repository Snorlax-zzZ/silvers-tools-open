---
description: 保存或更新当前任务的共享 checkpoint，同步到公共接力区远端（pi 版）
argument-hint: "[shared checkpoint 路径]"
---
把当前任务状态整理成共享 checkpoint，写入公共接力区并同步远端，供另一个模型 / 客户端 / 机器继续。

## 权威协议（执行前必须完整读取）

1. `<SILVERS_TOOLS>/shared/command/checkpoint/design.md`
2. `<SILVERS_TOOLS>/shared/command/checkpoint/commands/checkpoint-shared.md`

`<SILVERS_TOOLS>` = 本仓库本机 clone 路径，安装时替换；必须填写工具仓库的真实绝对路径。缺失时停止并提示。

**本命令只做 pi 侧替换，不得改动**：公共路径、远端、schema、revision 规则、7k token 上限、九个必备章节、安全规则、`git pull --ff-only` 行为。

## pi 侧替换

| 维度 | 模板原文 | pi 执行 |
|---|---|---|
| 自称 | 你（当前客户端） | pi |
| `<client_name>` | 安装时硬编码 | **`pi`**（运行时不得写 `unknown`） |
| 参数 | 客户端原生参数 | `$@` = 可选 shared checkpoint 路径 |
| 工具名 | Read / Write / Bash | `read` / `write` / `edit` / `bash` |
| 权限 | 客户端权限机制 | pi 无权限弹窗，直接执行；遇真实拒绝才停 |
| 扫描脚本 | `<installed-script-path>` | `~/.pi/agent/scripts/list-shared-checkpoints.sh` |

## 运行时块（pi 按引用安装，故在运行时判断平台）

```markdown
<!-- CHECKPOINT-SHARED RUNTIME -->
执行前先判断当前平台：
- macOS / Linux：Bash/Zsh 语义；取时间新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`；
  扫描脚本按 BSD/GNU `stat` 实际能力处理，不假设 `stat -c`。
- Windows：必须 Git Bash；禁止 PowerShell `Get-Date` / `[DateTime]::Now`。
公共工作区固定 `$HOME/.silvers/checkpoint-shared`，只允许操作 `shared/`。
UTF-8 + LF；中文 slug 不得按字节 `head -c` 截断。
client_name 固定 `pi`。
同步固定 `git pull --ff-only`，禁止 merge / rebase / force push。
<!-- END CHECKPOINT-SHARED RUNTIME -->
```

## 强制约束（摘要，全文以权威协议为准）

- 写入前新执行 `date`，禁止复用对话里的旧时间戳
- 无 expected revision 时禁止覆盖已有文件
- revision 必须等于 expected revision + 1
- 正文九个必备章节齐全；超 7k token 先压缩过程叙述，不压接棒入口/风险/验证证据
- 无 token / 密码 / Cookie / 私钥 / 完整 `.env` / 完整 diff / 大段源码
- 只 stage 目标文件，禁止无边界 `git add -A`
- push 失败保留本地提交并明确汇报"**尚未交棒成功**"
- 成功后记住完整路径 + revision，供后续更新或 `/task-done-shared`

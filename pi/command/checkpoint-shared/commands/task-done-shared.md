---
description: 完成共享任务，把公共 checkpoint 归档到 done/ 并同步远端（pi 版）
argument-hint: "[shared checkpoint 路径]"
---
任务完成，把公共接力区的 checkpoint 归档到 `shared/done/<project_key>/` 并同步远端。

## 权威协议（执行前必须完整读取）

1. `<SILVERS_TOOLS>/shared/command/checkpoint/design.md`
2. `<SILVERS_TOOLS>/shared/command/checkpoint/commands/task-done-shared.md`

`<SILVERS_TOOLS>` 必须填写工具仓库的真实绝对路径，安装时替换。缺失时停止并提示。

**不得改动**：公共路径、远端、schema、revision 规则、安全规则、fast-forward-only 同步。

## pi 侧替换

| 维度 | 模板原文 | pi 执行 |
|---|---|---|
| 自称 | 你（当前客户端） | pi |
| `<client_name>` | 安装时硬编码 | `pi` |
| 参数 | 客户端原生参数 | `$@` = 可选 shared checkpoint 路径 |
| 工具名 | Read / Write / Bash | `read` / `write` / `edit` / `bash` |
| 权限 | 客户端权限机制 | pi 无权限弹窗 |
| 扫描脚本 | `<installed-script-path>` | `~/.pi/agent/scripts/list-shared-checkpoints.sh` |

## 执行要点

1. 确认目标 checkpoint 处于 `in-progress`（`$@` 优先；否则用本对话记住的路径；都没有先列候选让用户选）
2. 先同步：工作区干净 + `git pull --ff-only`
3. 按协议移动到 `shared/done/<project_key>/`，更新 frontmatter（`status: done`、新 revision、`updated_at` 用新执行的 `date`）
4. 只 stage 目标文件，commit + push；push 失败保留本地提交并汇报"**尚未归档成功**"
5. 汇报归档后路径、revision、同步状态

## 运行时块

```markdown
<!-- CHECKPOINT-SHARED RUNTIME -->
平台在运行时判断：macOS/Linux 用 Bash/Zsh；Windows 必须 Git Bash。
取时间新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`。
公共工作区固定 `$HOME/.silvers/checkpoint-shared`，只允许操作 `shared/`。
client_name 固定 `pi`；同步固定 `git pull --ff-only`。
<!-- END CHECKPOINT-SHARED RUNTIME -->
```

## 强制约束

- 只归档本项目的 checkpoint，不碰其他项目、不碰 `cc/` 等目录
- 不删除 `done/` 历史归档
- 找不到目标文件时停止并列出候选，不得猜
- 归档不等于任务自动完成；缺阶段完成证据时按协议拒绝归档

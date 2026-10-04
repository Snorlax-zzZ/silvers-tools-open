---
description: 在新会话里加载一份 checkpoint 继续工作（pi 版）
argument-hint: "[checkpoint 路径]"
---
加载一份 checkpoint，恢复到"接着做"的状态。

## 权威协议（执行前必须完整读取）

1. `<SILVERS_TOOLS>/cc/command/checkpoint/README.md` —— 唯一权威
2. `<SILVERS_TOOLS>/cc/command/checkpoint/commands/checkpoint-load.md` —— 执行步骤原文

`<SILVERS_TOOLS>` 必须填写工具仓库的真实绝对路径，安装时替换。文件缺失时停止并提示。

## pi 侧替换（逐条覆盖 cc 原文）

| 维度 | cc 原文 | pi 执行 |
|---|---|---|
| 自称 | 你（cc） | pi |
| 存储根 | `~/.claude/checkpoints/` | `~/.pi/agent/checkpoints/` |
| 参数 | `$ARGUMENTS` | `$@` |
| 工具名 | Read / Bash | `read` / `bash` |
| 扫描脚本 | `~/.claude/scripts/list-checkpoints.sh` | `~/.pi/agent/scripts/list-checkpoints.sh` |
| 权限 | settings allowlist | pi 无权限弹窗 |

## 执行要点

1. `$@` 为空时，按权威协议计算当前项目目录名，运行 `bash ~/.pi/agent/scripts/list-checkpoints.sh --here <当前项目目录名>`；必须显式传 `--here` 才会限制在该项目，不带参数会扫描全部项目
2. 多个候选：列编号 + title + updated_at，只让用户回编号，**不要自己挑**
3. 选定后完整读取，输出：一句话状态、第一步、完成标准、剩余任务、风险
4. 在本次对话中记住该文件路径，供后续 `/checkpoint` 更新和 `/task-done` 归档
5. 加载**不等于开工**：等用户确认后再动项目文件

## 强制约束

- 只读，不修改 checkpoint 文件
- 加载后如实汇报"从哪个文件恢复、停在哪一步"，不得凭标题猜进度
- 跨机器加载时，机器相关绝对路径 / 命令要折算成本机；不能折算的标"待用户确认"

---
description: 拉取公共接力区，加载一棒 shared checkpoint 并折算当前机器环境（pi 版）
argument-hint: "[shared checkpoint 路径]"
---
加载公共接力区的一棒，把另一台机器 / 另一个模型留下的状态折算到当前环境。

## 权威协议（执行前必须完整读取）

1. `<SILVERS_TOOLS>/shared/command/checkpoint/design.md`
2. `<SILVERS_TOOLS>/shared/command/checkpoint/commands/checkpoint-shared-load.md`

`<SILVERS_TOOLS>` 必须填写工具仓库的真实绝对路径，安装时替换。缺失时停止并提示。

**不得改动**：公共路径、远端、schema、revision 规则、安全规则、fast-forward-only 同步。

## pi 侧替换

| 维度 | 模板原文 | pi 执行 |
|---|---|---|
| 自称 | 你（当前客户端） | pi |
| 扫描脚本 | `<installed-script-path>` | `~/.pi/agent/scripts/list-shared-checkpoints.sh` |
| 参数 | 客户端原生参数 | `$@` = 可选 shared checkpoint 路径 |
| 工具名 | Read / Bash | `read` / `bash` |
| 权限 | 客户端权限机制 | pi 无权限弹窗 |

## 执行要点

1. 先确保公共工作区可安全同步：工作区有未知改动 / 未推送提交时停止，禁止自动 stash / reset / 覆盖；load 不得 push。提示回到原 save/done 会话补推，或由用户手工恢复后重试
2. `git pull --ff-only`；分叉或失败即停止，禁止 merge / rebase / force push
3. `$@` 为空时用 `~/.pi/agent/scripts/list-shared-checkpoints.sh` 列候选（排除 `shared/done/`）；多个只让用户回编号
4. 完整读取后输出：一句话状态、第一步（含可执行命令 / 预期 / 完成标准 / 失败分支）、剩余任务、风险、跨机折算项
5. 记住完整路径 + expected revision，供后续 `/checkpoint-shared` 更新和 `/task-done-shared` 归档
6. 加载**不等于开工**：等用户确认再动项目文件

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

- 只读加载，不修改 checkpoint
- 机器相关绝对路径 / 命令必须折算到本机；不能折算的标"待用户确认"
- 如实汇报从哪个文件恢复、停在哪一步，不凭标题猜

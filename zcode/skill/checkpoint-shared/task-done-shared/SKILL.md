---
name: task-done-shared
description: Use when the user explicitly asks to "task done shared"/"共享任务完成"/"共享收工". shared 三件套之收棒：把共享接力任务标记 done、git mv 到 shared/done/ 归档区并 push 同步。存棒走 checkpoint-shared，接棒走 checkpoint-shared-load。本地版走 task-done，云端版走 task-done-online。不要主动触发，只有用户明确要求时才执行。
---

# Task-Done-Shared（公共接力 · 收棒）

把当前共享接力任务标记完成，保存最终收口信息，移动到公共归档区并同步远端。存棒走 checkpoint-shared，接棒走 checkpoint-shared-load。

## 固定资源

- 公共工作区：`~/.silvers/checkpoint-shared/`
- 活动位置：`shared/<project_key>/<文件名>`；归档位置：`shared/done/<project_key>/<文件名>`
- 只允许操作该目标 checkpoint；禁止改动远端其他目录
- 用户主动调用即视为确认本次可追溯归档和限定 push，不再插 y/n；这不授权删除文件或操作当前项目 Git

## 运行时约束

<!-- CHECKPOINT-SHARED RUNTIME -->
- macOS / Linux：Bash/Zsh 语义；时间必须新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`。Windows（`MINGW*`/`MSYS*`/`CYGWIN*`）：必须 Git Bash，禁 PowerShell `Get-Date` / `[DateTime]::Now`。
- 文件 UTF-8、LF；`client_name` 硬编码 `zcode`（model 无法可靠得知才写 `unknown`）。
- 同步固定 `git pull --ff-only`，禁 merge / rebase / force push；只 stage 目标 checkpoint，禁 `git add -A`。
<!-- END CHECKPOINT-SHARED RUNTIME -->

> 协议 SSOT：本工具仓库的 `shared/command/checkpoint/design.md`，冲突以其为准。

## 收棒步骤（task-done-shared）

### 1. 就绪检查 + 定位目标

1. 工作区就绪检查（同接棒：clone/remote 校验、dirty 停止、未推送先补推、`pull --ff-only`）
2. 按优先级定位：用户显式传入活动 checkpoint 路径 > 数字编号（按接棒同一列表规则定位）> 本次对话记得的路径 + expected revision > 都没有 → 停止，要求先接棒（checkpoint-shared-load）
3. 只接受 `shared/<project_key>/` 下 `in-progress` 文件；必须持有 expected revision N，pull 后远端仍为 N 才能归档并写 N+1；不一致停止并重新接棒

### 2. 采集本次真实身份与时间

新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`；client 固定 `zcode`；采集当前 model/machine/os/shell/path style。

### 3. 写最终状态

保持 `checkpoint_id`、`project_key`、`project_remote`、`created_at` 不变，更新：

```yaml
status: done
revision: <N+1>
updated_at: <本次真实时间>
last_client: zcode
last_model: <当前模型或 unknown>
last_machine: <hostname>
last_os: <darwin | linux | win32>
last_shell: <当前 shell>
path_style: <posix | windows>
last_project_root: <当前项目根>
done_at: <本次真实时间>
done_client: zcode
done_model: <当前模型或 unknown>
done_machine: <hostname>
```

正文同步收口：当前进度改为已完成边界；已完成工作补最后一轮验证命令和实际结果；接棒入口改成"任务已完成，无需继续接棒"（保留历史关键决策、陷阱和证据）；非阻塞事项移到 P2 / long-term 并说明不影响完成；仍 ≤ 7k token、无敏感（敏感参数 `<REDACTED>` + 取得位置）。先写临时文件，校验后原子替换。

### 4. 移动、提交和推送（禁 rm、先删后写、复制后删除）

```bash
mkdir -p ~/.silvers/checkpoint-shared/shared/done/<project_key>
git -C ~/.silvers/checkpoint-shared mv -- \
  "shared/<project_key>/<文件名>" \
  "shared/done/<project_key>/<文件名>"
git -C ~/.silvers/checkpoint-shared add -- "shared/done/<project_key>/<文件名>"
git -C ~/.silvers/checkpoint-shared commit -m "done(shared/<project_key>): r<revision> <title> @zcode/<model>"
git -C ~/.silvers/checkpoint-shared push
```

push 失败保留本地提交并明确报告"**归档尚未同步成功**"，下次 shared 命令先补推；禁止把本地移动误报为远端归档成功。

### 5. 清理上下文并汇报

只有 push 成功后才忘掉当前路径和 expected revision：

```text
✅ 共享任务已归档并同步
原位置：shared/<project_key>/<文件名>
归档到：shared/done/<project_key>/<文件名>
revision：<N+1>
收尾者：zcode/<model> @ <machine>
```

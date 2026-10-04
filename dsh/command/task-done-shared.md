---
name: task-done-shared
description: 共享接力任务收尾，写最终状态后 git mv 到公共归档区并 push 远端
user-invocable: true
---

<!--
用途：/task-done-shared —— Checkpoint Shared 三件套的「归档」一棒：标记 done、补最终收口信息、git mv 到 shared/done/ 并 push。
用法：/task-done-shared            归档本会话正在维护的那份共享 checkpoint
      /task-done-shared <数字>     按 /checkpoint-shared-load 同一列表规则定位第 N 项
      /task-done-shared <路径>     公共工作区内的活动 checkpoint 路径
位置建议：<CHECKPOINT_TOOLS>/dsh/command/task-done-shared.md（DSH 扫 customSkillDirs 的平面 skill 文件）
来源：shared/command/checkpoint/commands/task-done-shared.md 语义模板的 DSH 原生版；配套 checkpoint-shared.md / checkpoint-shared-load.md；完整协议以 shared/command/checkpoint/design.md 为准。
-->

# /task-done-shared — 归档共享 checkpoint

DSH执行，对用户称用户。

> **只归档、不删除**：归档后仍可追溯（历史版本由 Git 提供），反悔了反向 `git mv` 回来即可。**不授权删除文件，也不授权操作当前项目的 Git**。

## 0. 本机运行时约束（按当前 OS 取对应分支，强制）

<!-- CHECKPOINT-SHARED RUNTIME：按当前 OS 取对应分支；共同项无条件生效 -->
- **共同**：公共工作区固定为 `$HOME/.silvers/checkpoint-shared`；Markdown、脚本和文件名统一 UTF-8、LF；`client_name` 硬编码为 `dsh`（`last_client` 一律填 `dsh`，运行时禁止写 `unknown`，model 取不到时才允许 `unknown`）。
- **macOS / Linux**：shell 用 Bash/Zsh 语义；取时必须新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`；扫描脚本兼容 BSD `stat`，不假设 GNU `stat -c`。
- **Windows**：取时必须走 Git Bash 的 GNU `date`（`date '+%Y-%m-%dT%H:%M:%S%z'`），**禁用** PowerShell `Get-Date` / `[DateTime]::Now`（cold start + Defender 实时扫描会拖到超时甚至挂死）；路径用 `$HOME/` 由 Git Bash 展开。
<!-- END CHECKPOINT-SHARED RUNTIME -->

**强制**：本段缺失就停下来，提示重新按 `shared/command/checkpoint/install/` 下当前 OS 对应的手册（`macos.md` / `windows.md`） 安装；然后按下面的流程同步。

## 固定资源与边界

- 远端：`<CHECKPOINT_REPO_URL>`
- 公共工作区：`~/.silvers/checkpoint-shared/`
- 活动位置：`~/.silvers/checkpoint-shared/shared/<project_key>/<文件名>`
- 归档位置：`~/.silvers/checkpoint-shared/shared/done/<project_key>/<文件名>`
- **仅限该目标 checkpoint**：禁止改动远端其它目录（`cc/`、`codex/`、`zcode/` 等都不在授权范围）。
- **参数**：`/task-done-shared` 之后的文字就是用户消息原文——可选数字编号，或公共工作区内的活动 checkpoint 路径；两种形式**都不能绕过 expected revision 校验**。项目根取 **cwd**。
- **授权**：用户主动喊 `/task-done-shared` 即视为确认本次可追溯归档和**限定** push，**不再插入 y/n**；这不授权删除文件，也不授权操作当前项目的 Git。
- 禁止修改 `~/.ssh/config`、`~/.gitconfig`；禁止擅自更换用户配置的远端地址或 URL scheme。认证 / 网络不通就停下来报告用户，不要自行绕过。

## 执行步骤

### 1. 确认工作区可安全同步

- 用 `git -C "$HOME/.silvers/checkpoint-shared" remote -v` 核实 origin 是固定仓库。
- 检查未知 dirty 文件和未推送提交；**有异常先停止或补推**，**禁止** stash / reset。
- 同步策略**固定**为 `git pull --ff-only`：

  ```bash
  git -C "$HOME/.silvers/checkpoint-shared" pull --ff-only
  ```

不能 fast-forward 时**停止**，**禁止** merge、rebase 或 force push。

### 2. 定位目标和 expected revision（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | 用户消息里传了公共工作区内的活动 checkpoint 路径 | 用这个 |
| 2 | 用户消息里传了数字 N | 按 `/checkpoint-shared-load` 同一列表规则（全局、有效时间倒序、最多 12 个）定位第 N 项 |
| 3 | 本次对话记得当前 shared checkpoint 路径和 expected revision | 用这个 |
| 4 | 以上都没有 | **停止**，要求先 `/checkpoint-shared-load` |

- **只接受** `shared/<project_key>/` 下、状态为 `in-progress` 的文件。
- 必须持有 **expected revision N**；pull 之后远端仍为 N 才能归档，并把 revision 更新为 **N+1**。
- revision 不一致时**停止**并重新 load；没有 expected revision 时**不得覆盖已有文件**。

### 3. 采集本次真实身份与时间

新执行一次：

```bash
date '+%Y-%m-%dT%H:%M:%S%z'
```

- `client` 用本机硬编码的 `dsh`，运行时**不得**写 `unknown`。
- 采集当前 model / machine / os / shell / path style；model 无法可靠得知时写 `unknown`，**不能猜测**。

### 4. 写最终状态

保持 `checkpoint_id`、`project_key`、`project_remote` 和 `created_at` **不变**，更新：

```yaml
status: done
revision: <N+1>
updated_at: <本次真实时间>
last_client: dsh
last_model: <当前模型或 unknown>
last_machine: <当前 hostname>
last_os: <darwin | linux | win32>
last_shell: <当前 shell>
path_style: <posix | windows>
last_project_root: <当前项目根>
done_at: <本次真实时间>
done_client: dsh
done_model: <当前模型或 unknown>
done_machine: <当前 hostname>
```

归档前同步正文的最终状态：

- 当前进度改为**已完成边界**。
- 已完成工作补上最后一轮验证命令和实际结果。
- 接棒入口改成「**任务已完成，无需继续接棒**」，但保留历史关键决策、陷阱和证据。
- 尚未处理的非阻塞事项移到 P2 / long-term，明确它们不影响本任务完成。
- 正文**仍不得超过 7k token**，不得包含秘密；敏感参数写 `<REDACTED>`。

**先写临时文件，校验后原子替换活动文件**；失败时保留原文件。

### 5. 移动、提交和推送

确保目标目录存在，然后使用 `git mv`——**禁止** `rm`、先删后写或复制后删除：

```bash
mkdir -p "$HOME/.silvers/checkpoint-shared/shared/done/<project_key>"
git -C "$HOME/.silvers/checkpoint-shared" mv -- \
  "shared/<project_key>/<文件名>" \
  "shared/done/<project_key>/<文件名>"
git -C "$HOME/.silvers/checkpoint-shared" add -- "shared/done/<project_key>/<文件名>"
git -C "$HOME/.silvers/checkpoint-shared" commit -m "done(shared/<project_key>): r<revision> <title> @dsh/<model>"
git -C "$HOME/.silvers/checkpoint-shared" push
```

- **只 stage 该 checkpoint**，不使用无边界的 `git add -A`。
- push 失败时保留本地提交并明确报告「**归档尚未同步成功**」；下次 shared 命令**必须先补推**。
- **禁止把本地移动误报为远端归档成功**——只有 push 成功才算归档成立。

### 6. 清理上下文并汇报

**只有 push 成功后**，才忘掉当前 shared checkpoint 路径和 expected revision：

```text
✅ 共享任务已归档并同步
原位置：shared/<project_key>/<文件名>
归档到：shared/done/<project_key>/<文件名>
revision：<N+1>
收尾者：dsh/<model> @ <machine>
```

## 沙箱提示（DSH 特有）

`~/.silvers/checkpoint-shared/` 在**工作区之外**：`workspace-write` 档下 `git mv` 与 `git push` 都会被沙箱拒绝。遇到拒绝就按沙箱升权流程申请一次更宽档位（`read-only` → `workspace-write` → `danger-full-access` 是封闭阶梯），或让用户用 `/permission` 切到含 full-access 的预设。**不要**为了绕开沙箱把归档目录改到工作区里。详见同目录 `README.md` 的权限章节。

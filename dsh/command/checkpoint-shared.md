---
name: checkpoint-shared
description: 把当前任务状态整理成共享 checkpoint 写入公共接力区并 push 远端，供别的模型 / 客户端 / 机器接棒
user-invocable: true
---

<!--
用途：/checkpoint-shared —— Checkpoint Shared 三件套的「保存」一棒：把任务状态写成共享 checkpoint，落到公共 clone 的 shared/<project_key>/，commit 后 push 到远端。
用法：/checkpoint-shared            新建一份（revision 1），或更新本会话已 load / 已保存的那份（revision N → N+1）
      /checkpoint-shared <路径>     显式指定要更新的活动 checkpoint（仍必须通过 expected revision 校验）
位置建议：<CHECKPOINT_TOOLS>/dsh/command/checkpoint-shared.md（DSH 扫 customSkillDirs 的平面 skill 文件，别拷到 ~/.dsh/skills）
来源：shared/command/checkpoint/commands/checkpoint-shared.md 语义模板的 DSH 原生版；完整协议（存储布局 / Schema v1 / revision / 九章节正文 / 跨机折算 / Git 失败语义 / 安全）以 shared/command/checkpoint/design.md 为准，本文件不复述设计原理。
-->

# /checkpoint-shared — 保存共享 checkpoint 并同步远端

DSH执行，对用户称用户。

> **跟本地 checkpoint 是两套，平行不干扰**：`/checkpoint`、`/checkpoint-online` 系列和它们的目录 / clone **一律不动、不迁移、不复用**；本命令只碰 `~/.silvers/checkpoint-shared/` 下的 `shared/`。
> **本命令的定位**：多模型顺序接力（A 保存 → B 加载继续 → 最后一棒归档），支持换客户端、换模型、换机器；**不支持**多个模型并发改同一个任务。

## 0. 本机运行时约束（按当前 OS 取对应分支，强制）

<!-- CHECKPOINT-SHARED RUNTIME：按当前 OS 取对应分支；共同项无条件生效 -->
- **共同**：公共工作区固定为 `$HOME/.silvers/checkpoint-shared`；Markdown、脚本和文件名统一 UTF-8、LF；`client_name` 硬编码为 `dsh`（`last_client` 一律填 `dsh`，运行时禁止写 `unknown`，model 取不到时才允许 `unknown`）。
- **macOS / Linux**：shell 用 Bash/Zsh 语义；取时必须新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`；扫描脚本兼容 BSD `stat`，不假设 GNU `stat -c`。
- **Windows**：取时必须走 Git Bash 的 GNU `date`（`date '+%Y-%m-%dT%H:%M:%S%z'`），**禁用** PowerShell `Get-Date` / `[DateTime]::Now`（cold start + Defender 实时扫描会拖到超时甚至挂死）；路径用 `$HOME/` 由 Git Bash 展开。
<!-- END CHECKPOINT-SHARED RUNTIME -->

**强制**：本段缺失就停下来，提示重新按 `shared/command/checkpoint/install/` 下当前 OS 对应的手册（`macos.md` / `windows.md`） 安装，不要凭记忆继续往下跑。

## 固定资源与授权边界

- 远端：`<CHECKPOINT_REPO_URL>`
- 公共工作区：`~/.silvers/checkpoint-shared/`
- 活动目录：`~/.silvers/checkpoint-shared/shared/<project_key>/`
- 归档目录：`~/.silvers/checkpoint-shared/shared/done/<project_key>/`
- **仅限 `shared/`**：远端其它顶层目录（`cc/`、`codex/`、`zcode/` 等）**不在授权范围**——禁止读、禁止写、禁止 commit。
- **参数**：`/checkpoint-shared` 之后的文字就是用户消息原文，当**可选的活动 checkpoint 路径**用（DSH 没有 `$ARGUMENTS` 这种东西）；为空走步骤 3 的默认判定。项目根一律取 **cwd**。
- **授权范围**：用户主动喊 `/checkpoint-shared`，即授权本次在这个公共工作区内做**限定**的 clone、pull、add、commit、push；**不授权**改当前项目的 Git 历史，也**不授权**普通项目 push。
- 禁止修改 `~/.ssh/config`、`~/.gitconfig`；禁止擅自更换用户配置的远端地址或 URL scheme。认证 / 网络不通就停下来报告用户，不要自行绕过。

## 执行步骤

### 1. 确保公共工作区可安全同步

1. `~/.silvers/checkpoint-shared/.git` 不存在 → clone 固定远端到该目录：

   ```bash
   git clone <CHECKPOINT_REPO_URL> "$HOME/.silvers/checkpoint-shared"
   ```

2. 已存在 → 用 `git -C "$HOME/.silvers/checkpoint-shared" remote -v` 确认 origin 就是固定仓库；不是就停下来报告，**禁止**改 remote。
3. 检查工作区（`bash` 跑 `git -C "$HOME/.silvers/checkpoint-shared" status --short --branch`）：
   - 有未知 tracked/untracked 修改：**停止**，列出文件；**禁止**自动 stash、reset 或覆盖。
   - 有未推送的本地提交：先尝试补 push；补推失败就**停止**，本轮**不能**创建新 revision。
4. 干净且没有未推送提交后，执行 fast-forward-only 同步：

   ```bash
   git -C "$HOME/.silvers/checkpoint-shared" pull --ff-only
   ```

同步策略**固定**为 `git pull --ff-only`：pull 失败或出现分叉就停止，**禁止** merge、rebase 或 force push。

### 2. 计算项目身份

- **Git 项目**：读 `origin`，把 SSH SCP、`ssh://`、HTTPS 三种 URL 统一规范化为 `host/owner/repo`——移除 scheme、SSH user、查询参数、fragment、首尾斜杠和 `.git`，host 转小写；GitHub 的 owner/repo 也转小写。`project_key` 取规范化结果最后一段。
- **非 Git 项目**：`project_key` 取当前目录 basename，`project_remote: none`。
- 规范化示例：`git@github.com:Owner/Repo.git`、`ssh://git@github.com/Owner/Repo.git`、`https://github.com/Owner/Repo.git` **都得到** `github.com/owner/repo`。
- 如果 `shared/<project_key>/` 已有 checkpoint，比较当前项目与 checkpoint 里的规范化 `project_remote`：两侧都不是 `none` 且值相等时才可自动继续；两侧都不是 `none` 且值不相等时，视为**项目碰撞并停止**。任一侧为 `none` 时身份无法自动核实，选择、加载或更新前**必须取得用户显式确认**。

### 3. 决定创建还是更新（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | 用户消息里显式传了 shared checkpoint 路径 | 只接受公共工作区 `shared/<project_key>/` 下、状态为 `in-progress` 的文件 |
| 2 | 本次对话记得 `/checkpoint-shared-load` 加载的完整路径和 expected revision | 更新该文件 |
| 3 | 都没有 | 新建 `YYYYMMDD-HHMMSS-<8–15 个中文字 slug>.md`，初始 revision 为 1 |

- 没有 expected revision 时**禁止覆盖已有文件**。
- 当前项目若已存在看起来属于同一任务的活动 checkpoint，先列出让用户选 load / update 还是新建任务，**不能靠标题猜测后覆盖**。
- 更新已有文件时：pull 之后**再次读取**远端 revision，它必须等于本次对话记住的 expected revision N；否则**停止**并要求重新 `/checkpoint-shared-load`。校验通过后只能写 revision **N+1**。
- slug 从任务标题提炼 8–15 个中文字，去标点空格；首次创建时定死，后续更新不改文件名（列表展示用 frontmatter 的 `title`，不用 slug）。

### 4. 采集真实时间、客户端和环境

写入前**必须新执行一次**：

```bash
date '+%Y-%m-%dT%H:%M:%S%z'
```

**禁止**复用对话上下文、旧 frontmatter 或另一台机器留下的时间戳。

采集项：

- `last_client`：本机硬编码的 `dsh`，运行时**不得**写 `unknown`。
- `last_model`：当前模型；无法可靠得知就写 `unknown`，**禁止猜测**。
- `last_machine`：`hostname`。
- `last_os`：`Darwin → darwin`、Linux → `linux`、`MINGW*` / `MSYS*` / `CYGWIN*` → `win32`。
- `last_shell`：当前实际 shell。
- `path_style`：只能是 `posix` 或 `windows`。
- `last_project_root`：当前项目真实绝对路径，仅作环境记录。

首次创建时 `created_at` 等于本次时间；更新时**保持原 `created_at` 不变**，`updated_at` 每次刷新。

### 5. 生成 frontmatter（扁平，字段必须齐全）

```yaml
---
schema_version: 1
checkpoint_id: <与稳定文件名主体一致>
project_key: <项目标识>
project_remote: <规范化远端或 none>
title: "<一句话任务标题>"
status: in-progress
revision: <1 或 N+1>
created_at: <首次创建时间，后续不变>
updated_at: <本次真实时间>
last_client: dsh
last_model: <当前模型或 unknown>
last_machine: <hostname>
last_os: <darwin | linux | win32>
last_shell: <当前 shell>
path_style: <posix | windows>
last_project_root: <当前项目绝对路径>
---
```

未知 `schema_version` 只能只读展示，**禁止覆盖**。

### 6. 生成正文（九个必备章节）

正文建议 4–6k token，**硬上限 7k token**。简单任务可以更短；超限时的压缩优先级是 **过程叙述 > 可选附录 > 九个必备章节**，不能压缩接棒入口、风险和验证证据。

```markdown
# <任务标题>

## 1. 接棒入口

### 一句话状态
<完成到什么边界，当前卡点是什么>

### 接棒后的第一步
- **目的**：<这一步解决什么>
- **工作目录**：<当前机器应进入哪里；项目内路径优先相对路径>
- **前置条件**：<分支、依赖、服务、凭据来源、测试数据>
- **必读文件**：<相对路径 + 关键行/章节 + 阅读目的>
- **修改入口**：<预计从哪些文件/模块开始>
- **执行命令**：<可复制的完整命令，敏感值用占位符>
- **预期结果**：<正常输出或行为>
- **完成标准**：<看到什么才算完成>
- **失败分支**：<常见失败的判定方式 + 下一条诊断命令>

### 后续步骤
1. <动作；实施位置；验证方法；完成条件>
2. <动作；实施位置；验证方法；完成条件>

### 不要重复的工作
- <已完成或已排除路径 + 证据>

### 接棒前仍需用户确认
- <真正需要拍板的事项；没有写“无”>

## 2. 任务目标与范围
<最终交付、包含项、不做项>

## 3. 当前进度与工作区状态
<已完成/进行中/未开始；分支、未提交文件、远端状态>

## 4. 已完成工作及验证证据
<改了什么、在哪里、运行过什么、结果是什么>

## 5. 关键决策
<决策、理由、来源、放弃的备选>

## 6. 认知陷阱与已排除路径
<误区、真相、证据；本轮真没踩过就写“无（任务直线推进）”。
 **不要为了凑段编**——编出来的假陷阱会让接棒方绕开一条根本不存在的坑，比留白更糟。>

## 7. 剩余任务
### P0
### P1
### P2
### long-term
<每项写依赖、实施位置和完成条件>

## 8. 环境与跨机折算
<存档机环境；机器相关绝对路径/命令；凭据重新取得位置>

## 9. 引用
<只列相对文件、设计文档、提交和报告位置，不复制正文>

<!-- 以下附录均为可选，不计入正文九个必备章节。
     没有实质内容时不生成标题，也不写“无”。 -->

## 可选附录：关键发现
<跟本轮改动无关、但下一棒不知道就会踩的代码库既存事实。
 与第 4 节的分界：第 4 节写“本轮改了什么、跑了什么、结果如何”（改动证据），
 本节写“某文件 line N 有隐式默认分支 / 上游 schema 字段类型严格”（既存事实）。
 同一件事不要两节各写一遍。>

## 可选附录：AI verify 边际效用提醒
<仅在已完成多轮 AI 审查、继续审的边际收益明显降低时才写。
 写清：已做几轮 / 报告位置 / 不要再审的理由 / 建议改走什么路径（如真实流量、联调驱动）。>
```

- **接棒入口必须放第一节**，让全新模型只读 checkpoint 与其中的必读文件，就能在五分钟内开始第一条有效操作。
- 两个**可选附录**（关键发现 / AI verify 边际效用提醒）**可写可不写，缺失不构成校验失败**；没有实质内容时**不生成标题，也不写“无”**。一旦出现，仍受 7k token 上限、安全脱敏和“禁止复制大段源码 / 完整 diff”约束。
- **跨机可移植性**：项目内文件始终用相对 `last_project_root` 的相对路径；机器相关绝对路径和命令**集中在第 8 节**，不能散落在其他章节；不确定的路径或命令标成「待用户确认」，**禁止编造**。

### 7. 写入前强制校验

- 路径位于 `shared/<project_key>/`，**不在** `shared/done/`。
- frontmatter 必填字段齐全，`schema_version: 1`，`status: in-progress`。
- `checkpoint_id` 与稳定文件名一致。
- 新建 revision 为 1；更新 revision 恰好为 expected revision + 1。
- `created_at` 更新时未改变，`updated_at` 来自本次真实取时。
- 正文**九个必备章节**齐全，尤其「接棒后的第一步」包含可执行命令、预期结果、完成标准和失败分支。
- 两个**可选附录**缺失不构成校验失败；一旦出现，仍受 7k token 上限、脱敏和「禁止复制大段源码 / 完整 diff」约束。
- 估算正文没有超过 7k token。
- 没有 token、密码、Cookie、私钥、完整 `.env` 或账号凭据。敏感参数统一替换成 `<REDACTED>`，并说明从哪里重新取得。
- 没有完整聊天记录、完整 diff 或大段源码；引用已有 artifact 只写路径、提交或文档位置。

**任一校验失败都拒绝保存**，并列出缺项。

### 8. 原子写入、提交和推送

1. **原子替换**：先把完整内容写到目标同目录的临时文件，校验通过后再原子替换目标文件；失败时**保留原 checkpoint**。不要先破坏旧文件再生成新内容。
2. 用 `write` 落临时文件、`read` 复核内容，再用 `bash` 做原子替换。
3. **只 stage 目标 checkpoint**，不使用无边界的 `git add -A`：

   ```bash
   git -C "$HOME/.silvers/checkpoint-shared" add -- "shared/<project_key>/<文件名>"
   git -C "$HOME/.silvers/checkpoint-shared" commit -m "checkpoint(shared/<project_key>): r<revision> <title> @dsh/<model>"
   git -C "$HOME/.silvers/checkpoint-shared" push
   ```

- push 被拒绝时**只允许**再次 fetch / `pull --ff-only` 后重试一次；如果不能 fast-forward，**停止**。
- 网络中断时保留本地提交，明确汇报「**尚未交棒成功**」；下次 shared 命令**必须先补推**，不能创建另一个 revision。
- **只有 push 成功才算交棒成立**。

### 9. 记住并汇报

push 成功后在本次对话里记住**完整路径和 revision**，供后续更新或 `/task-done-shared` 使用：

```text
✅ 共享 checkpoint 已保存并同步
路径：shared/<project_key>/<文件名>
revision：<N>
写入者：dsh/<model> @ <machine>
接棒状态：远端已就绪
```

## 沙箱提示（DSH 特有）

`~/.silvers/checkpoint-shared/` 在**工作区之外**：`workspace-write` 档下写文件、跑 `git commit` / `git push` 都会被沙箱拒绝。遇到拒绝就按沙箱升权流程申请一次更宽档位（`read-only` → `workspace-write` → `danger-full-access` 是封闭阶梯，只能往更宽的方向走），或让用户用 `/permission` 切到含 full-access 的预设。**不要**为了绕开沙箱把公共工作区挪进当前项目——那会把接力文件混进项目 git。详见同目录 `README.md` 的权限章节。

---
name: checkpoint-shared
description: Use when the user explicitly asks to "checkpoint shared"/"共享 checkpoint"/"共享存档"/"公共接力"/"存一棒". shared 三件套之存棒：保存/更新公共接力区的共享 checkpoint 并 push 同步远端，供另一个模型/客户端/机器接棒。接棒走 checkpoint-shared-load，收棒走 task-done-shared。不要主动触发，只有用户明确要求时才执行。
---

# Checkpoint-Shared（公共接力 · 存棒）

给多个模型 / 客户端 / 机器**顺序接力同一个任务**用：一棒保存 → 另一棒接棒（checkpoint-shared-load）→ 最后一棒收棒（task-done-shared）。与本地 checkpoint、checkpoint-online 完全并行，只复用同一个 git 远端。本 skill 只管**存棒**。

## 固定资源与授权边界

- 远端：`<CHECKPOINT_REPO_URL>`
- 公共工作区：`~/.silvers/checkpoint-shared/`（所有客户端共用同一个 clone）
- 活动目录：`~/.silvers/checkpoint-shared/shared/<project_key>/<checkpoint_id>.md`
- 归档目录：`~/.silvers/checkpoint-shared/shared/done/<project_key>/<checkpoint_id>.md`
- **只允许操作 `shared/`**；禁止读取或改动远端其他顶层目录（`cc/`、`zcode/`、`codex/` 等）
- 用户主动调用即授权本次在公共工作区内执行限定的 clone / pull / add / commit / push；不授权修改当前项目的 Git 历史，也不授权普通项目 push

## 运行时约束

<!-- CHECKPOINT-SHARED RUNTIME -->
执行前先判断当前平台：
- macOS / Linux：Bash/Zsh 语义；当前时间必须新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`，禁止复用对话、旧 frontmatter 或另一台机器的时间戳。
- Windows（`uname -s` 返回 `MINGW*` / `MSYS*` / `CYGWIN*`）：必须 Git Bash；禁止 PowerShell `Get-Date` / `[DateTime]::Now`。
- 扫描脚本必须兼容 BSD / GNU `stat` 实际能力，不假设 GNU `stat -c`。
- 公共工作区固定 `$HOME/.silvers/checkpoint-shared`。
- 文件统一 UTF-8、LF；中文 slug 不得用 `head -c` 按字节截断。
- `client_name` 固定硬编码 **`zcode`**，运行时禁止写 `unknown`；`last_model` 无法可靠得知时才写 `unknown`，禁止猜测。
- 同步固定 `git pull --ff-only`；禁止 merge / rebase / force push。
<!-- END CHECKPOINT-SHARED RUNTIME -->

> 协议唯一事实来源（SSOT）：本工具仓库的 `shared/command/checkpoint/design.md`。本 skill 与其冲突时以 design.md 为准。

## 通用预备步骤（存棒/接棒/收棒共用，详见各技能）

### A. 工作区就绪检查

1. `~/.silvers/checkpoint-shared/.git` 不存在 → `git clone <CHECKPOINT_REPO_URL> ~/.silvers/checkpoint-shared`
2. 已存在 → 确认 remote 指向固定仓库（不是则停止报告，禁止改 remote）
3. 有未知 dirty 修改 → **停止**，列出文件；禁止自动 stash、reset 或覆盖。有未推送本地提交 → 先尝试补 push，补推失败则停止，本轮不能创建新 revision
4. 干净且无未推送提交后：`git -C ~/.silvers/checkpoint-shared pull --ff-only`；失败或分叉 → 停止

### B. 计算项目身份

- Git 项目：读 `origin`，把 SSH SCP、`ssh://`、HTTPS 三种 URL 统一规范化为 `host/owner/repo`——移除 scheme、SSH user、查询参数、fragment、首尾斜杠和 `.git`；host 转小写，GitHub 的 owner/repo 也转小写。`project_key` 取规范化结果最后一段。例：`git@github.com:example/my-project.git` → `github.com/example/my-project`，key = `my-project`
- 非 Git 项目：`project_key` = 当前目录 basename，`project_remote: none`
- **碰撞规则**：两侧 `project_remote` 都不是 `none` 且相等 → 可自动继续；都不是 `none` 且不等 → 项目碰撞，停止；任一侧为 `none` → 必须用户显式确认

## 存棒步骤（checkpoint-shared）

### 1. 决定创建还是更新

优先级：

1. 用户显式传入 shared checkpoint 路径 → 只接受公共工作区 `shared/<project_key>/` 下、状态 `in-progress` 的文件
2. 本次对话记得 checkpoint-shared-load 记下的完整路径 + expected revision → 更新该文件（pull 后远端 revision 必须仍等于 N，否则停止并要求重新接棒；校验通过写 N+1）
3. 都没有 → 新建 `YYYYMMDD-HHMMSS-<8–15 个中文字 slug>.md`，revision = 1

**没有 expected revision 时禁止覆盖已有文件**。当前项目存在疑似同一任务的活动 checkpoint 时，先列出并让用户选接棒更新还是新建，不能靠标题猜测后覆盖。

### 2. 采集真实时间、客户端和环境

写入前必须新执行一次 `date '+%Y-%m-%dT%H:%M:%S%z'`，禁止复用任何旧时间戳。采集：

- `last_client`: **`zcode`**（安装时硬编码，运行时不得写 `unknown`）
- `last_model`: 当前模型；无法可靠得知写 `unknown`，禁止猜测
- `last_machine`: `hostname`
- `last_os`: `Darwin → darwin`、Linux → `linux`、`MINGW*/MSYS*/CYGWIN* → win32`
- `last_shell`: 当前实际 shell；`path_style`: `posix` 或 `windows`
- `last_project_root`: 当前项目真实绝对路径（仅环境记录）

首次创建时 `created_at` = 本次时间；更新时 `created_at` 不变，`updated_at` 每次刷新。

### 3. 生成 frontmatter（schema v1，扁平，字段齐全）

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
last_client: zcode
last_model: <当前模型或 unknown>
last_machine: <hostname>
last_os: <darwin | linux | win32>
last_shell: <当前 shell>
path_style: <posix | windows>
last_project_root: <当前项目绝对路径>
---
```

### 4. 生成正文（建议 4–6k token，硬上限 7k）

九个必备章节（第一章接棒入口强制放最前）：

1. **接棒入口**：一句话状态（完成到什么边界、当前卡点）；**接棒后的第一步**——目的 / 工作目录 / 前置条件（分支、依赖、服务、凭据来源、测试数据）/ 必读文件（相对路径 + 关键行 + 阅读目的）/ 修改入口 / 可复制的完整命令（敏感值用占位符）/ 预期结果 / 完成标准 / 失败分支及下一条诊断命令；后续步骤（2–6 步，每步写动作、实施位置、验证方式、完成条件）；不要重复的工作（已完成 / 已排除路径 + 证据）；接棒前仍需用户确认（没有写"无"）
2. 任务目标与范围（最终交付、包含项、不做项）
3. 当前进度与工作区状态（分支、未提交文件、远端状态）
4. 已完成工作及验证证据（改了什么、跑了什么、结果是什么）
5. 关键决策（决策、理由、来源、放弃的备选）
6. 认知陷阱与已排除路径（真没踩过就写"无（任务直线推进）"，**不要为了凑段编**）
7. 剩余任务（P0 / P1 / P2 / long-term，每项写依赖、实施位置、完成条件）
8. 环境与跨机折算（存档机环境；机器相关绝对路径和命令**只放本节**；凭据重新取得位置）
9. 引用（只列相对文件、设计文档、提交和报告位置，不复制正文）

可选附录（不计入必备章节；没有实质内容时**不生成标题也不写"无"**）：关键发现（与本轮改动无关但下一棒不知道就会踩的既存事实）；AI verify 边际效用提醒（多轮审查后边际收益明显降低时才写）。

超限压缩优先级：**过程叙述 > 可选附录 > 九个必备章节**；不能压缩接棒入口、风险和验证证据。项目内路径用相对路径；机器相关绝对路径只放第 8 节。

### 5. 写入前强制校验（任一失败拒绝保存并列出缺项）

- 路径位于 `shared/<project_key>/`，不在 `shared/done/`
- frontmatter 必填字段齐全，`schema_version: 1`，`status: in-progress`
- `checkpoint_id` 与稳定文件名一致；新建 revision=1，更新恰好 = expected+1
- `created_at` 未改变，`updated_at` 来自本次真实取时
- 九个必备章节齐全，"接棒后的第一步"含可执行命令、预期结果、完成标准、失败分支
- 估算正文 ≤ 7k token
- 无 token、密码、Cookie、私钥、完整 `.env`、账号凭据（敏感参数 `<REDACTED>` + 写明重新取得位置）；无完整聊天记录、完整 diff 或大段源码

### 6. 原子写入、提交和推送

先把完整内容写到目标同目录临时文件，校验通过后**原子替换**目标文件；失败时保留原 checkpoint，禁止先破坏旧文件再生成。

只 stage 目标 checkpoint（禁无边界的 `git add -A`）：

```bash
git -C ~/.silvers/checkpoint-shared add -- "shared/<project_key>/<文件名>"
git -C ~/.silvers/checkpoint-shared commit -m "checkpoint(shared/<project_key>): r<revision> <title> @zcode/<model>"
git -C ~/.silvers/checkpoint-shared push
```

push 被拒 → 只允许再次 fetch / `pull --ff-only` 后重试，不能 fast-forward 则停止。网络中断 → 保留本地提交，明确汇报"**尚未交棒成功**"，下次 shared 命令必须先补推，不能另建 revision。

push 成功后记住完整路径和 revision，汇报：

```text
✅ 共享 checkpoint 已保存并同步
路径：shared/<project_key>/<文件名>
revision：<N>
写入者：zcode/<model> @ <machine>
接棒状态：远端已就绪
```

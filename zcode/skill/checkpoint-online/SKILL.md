---
name: checkpoint-online
description: Use when the user explicitly asks to "checkpoint online"/"online 存档"/"同步到云端"/"云端 checkpoint"/"云端归档". online 三件套之存档：把当前会话状态存到云端（github 仓库 zcode 命名空间）并自动 commit + push，frontmatter 带环境块供跨机折算。云端加载走 checkpoint-load-online，云端完成走 task-done-online。不要主动触发，只有用户明确要求时才执行。
---

# Checkpoint-Online（云端存档）

本地 checkpoint 的云端版。存档落到 github 仓库的 zcode clone 工作区，写完自动 commit + push。frontmatter 多记环境块（机器/系统/shell/project_key），跨机器 load 时自动折算路径与命令。本 skill 只管**云端存档**；云端加载走 checkpoint-load-online，云端完成走 task-done-online。

## 云端工作区（ZCode 专属）

- **仓库**：`<CHECKPOINT_REPO_URL>`
- **本地工作区**：`~/.zcode/checkpoints-online/`（ZCode 专属 clone，与 cc 的 `~/.claude/checkpoints-online/` 分开）
- **命名空间**：存档落在 `~/.zcode/checkpoints-online/zcode/<project_key>/`（用 `zcode/` 子目录和 cc 的 `cc/` 区分）

## 存档步骤（checkpoint-online）

### 0. 确保工作区就绪（每次都做）
- 工作区不存在 → `git clone <CHECKPOINT_REPO_URL> ~/.zcode/checkpoints-online`
- 工作区已存在 → `git -C ~/.zcode/checkpoints-online pull --ff-only`（拿别的机器最新，避免 push 冲突）
- pull 失败/冲突 → 告诉用户「云端拉取异常」，中止，不强行覆盖

### 1. 计算 project_key（跨机稳定标识）
- git 仓库 → `git remote get-url origin` 仓库名去 `.git`（例 `my-project.git`→`my-project`）
- 非 git → `pwd` 的 basename
- 存档目录：`~/.zcode/checkpoints-online/zcode/<project_key>/`，不存在 `mkdir -p`

### 2. 决定写哪个文件
1. 用户传了路径 → 覆盖更新
2. 本次对话记得"当前 online checkpoint 路径" → 覆盖更新
3. 都没有 → 新建 `zcode/<project_key>/YYYYMMDD-HHMMSS-<slug>.md`

**路径边界校验（强制）**：写入前展开 `~`，消解 `.` / `..`，解析现有文件及父目录的符号链接。目标必须位于 `~/.zcode/checkpoints-online/zcode/<当前 project_key>/` 的活动目录；`project_key` 必须是非空单个目录名，不能为 `.` / `..`，不能包含 `/` 或 `\`。越界或来自其它客户端的文件只可只读参考，禁止读取后原地覆盖、stage 或提交。

提交使用 `commit --only -- <目标路径>`，保留其它文件的暂存状态，不把它们夹带进本次提交。

### 3. 采集环境元数据
- **machine**：`hostname`
- **os**：`uname -s`（Darwin→darwin，Linux→linux，MINGW→win32）
- **shell**：当前 shell（bash/zsh/pwsh）
- **project_root**：`pwd` 绝对路径（仅记录，load 时不照搬）
- **时间**：`date '+%Y-%m-%dT%H:%M:%S%z'`（强制每次新跑，禁止复用上下文旧时间戳）

### 4. 写入文档

**Frontmatter**（环境块是 online 核心增量）：
```yaml
---
project_key: <跨机稳定标识>
machine: <hostname>
os: <darwin | linux | win32>
shell: <bash | zsh | pwsh>
project_root: <存档机绝对路径，仅记录>
created_at: <首次创建填，后续不变>
updated_at: <每次刷新为当前 ISO8601>
title: "<一句话任务标题 10-25 字>"
status: in-progress
---
```

**正文**：沿用本地 checkpoint 结构，额外加「环境上下文」段：
```markdown
## 🖥️ 环境上下文（online 专用，跨机还原依据）
- **存档机**：<machine>（os: <os>，shell: <shell>）
- **项目根**：<project_root> ← 当前机器用 pwd 重新确定，勿照搬
- **机器相关路径/命令**：
  - 启动命令：`<完整命令>`
  - 运行时路径：`<python/node/venv 等>`
```

**可移植性铁律**：
- ✅ 项目内文件路径写相对路径（`src/xxx.py`）
- ✅ 机器相关绝对路径/命令集中写进「环境上下文」段
- ❌ 正文段落里不写死存档机绝对路径

### 5. 同步到 github
```bash
git -C ~/.zcode/checkpoints-online add "zcode/<project_key>/<文件名>"
git -C ~/.zcode/checkpoints-online commit --only -m "checkpoint(zcode/<project_key>): <title> @<machine>" -- "zcode/<project_key>/<文件名>"
git -C ~/.zcode/checkpoints-online push
```
- 首次推送报 no upstream → `push -u origin HEAD`
- push 失败 → `pull --ff-only` 后重试；仍失败告诉用户「已本地保存，云端同步失败」，不丢数据

### 6. 记住路径 + 汇报
```
✅ 已保存并同步到云端：`zcode/<project_key>/<文件名>`（约 X.X k token）
   存档机：<machine>（<os>）｜push：成功/失败(原因)
```

## 写作铁律 + 体积约束

同本地 checkpoint：只记结论不记过程，死路也记，不粘贴文件/diff。目标 3-5k token，超 5k 砍。

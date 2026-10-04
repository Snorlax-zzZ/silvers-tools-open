---
description: 任务完成后归档云端 checkpoint 并同步
argument-hint: 可选：数字序号或 online checkpoint 路径
---

标记云端任务完成，把 checkpoint 归档到云端 `done/` 子目录并同步 github（可追溯）。

> **背景**：`/task-done` 的云端版。配套：`/checkpoint-online`（保存）、`/checkpoint-load-online`（加载）。

## 云端工作区

- **本地工作区**：`~/.codex/checkpoints-online/`（你的云端 checkpoint 仓库的 clone，多客户端共用）
- **Codex 顶层命名空间**：`codex/`（活动目录 `codex/<project_key>/`，归档目录 `codex/done/<project_key>/`）
- 工作区内 git 操作已在 permissions 白名单豁免确认。

## 执行步骤

### 0. 确保工作区就绪 + 拉最新

- 工作区不存在 → clone（见 `/checkpoint-online`）
- 已存在 → `git -C ~/.codex/checkpoints-online pull --ff-only`

### 1. 找到要归档的 checkpoint（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | `$ARGUMENTS` 是文件路径（含 `/`） | 用这个 |
| 2 | `$ARGUMENTS` 是纯数字 N | 按 `/checkpoint-load-online` 列表规则（全局所有项目，`updated_at` 倒序）取第 N 个 |
| 3 | 你（Codex）在本次对话里记得"当前维护的 online checkpoint 路径" | 用这个 |
| 4 | 以上都没有 | 报错让用户显式指定路径，或先 `/checkpoint-load-online` 恢复上下文 |

**路径边界校验（强制）**：无论候选路径来自 `$ARGUMENTS`、数字序号还是对话记忆，归档前都要展开 `~`、解析绝对路径、消解 `.` / `..` 和符号链接。规范化后的源文件必须位于 `~/.codex/checkpoints-online/codex/<project_key>/` 的活动目录中，目标必须位于 `~/.codex/checkpoints-online/codex/done/<project_key>/`；任何越界、其他客户端路径、已在 `done/` 的路径或源/目标 project_key 不一致都要报错并中止，**绝不读取、移动、stage 或提交**。

### 2. 显示文件信息（不阻塞）

读 frontmatter 拿 `title`、`machine`，归档前打印一行：

  `准备归档云端：<title>（codex/<project_key>/<文件名>，存档机 <machine>）`

直接进第 3 步，**不要插入 y/n 对话** —— 用户主动喊 `/task-done-online` 即视为确认。

### 3. 归档操作

用户主动触发本 prompt 即视为确认，随后：

1. **更新 frontmatter**：
   - `status: in-progress` → `status: done`
   - 加 `done_at: <当前 ISO8601 时间>`（取时用 GNU date `date '+%Y-%m-%dT%H:%M:%S%z'`）
   - 加 `done_machine: <当前机器 hostname>`（记录是哪台机收的尾，跨机可追溯）
2. **移动文件**：
   - 目标：`~/.codex/checkpoints-online/codex/done/<project_key>/<原文件名>`
   - `mkdir -p` 确保 `codex/done/<project_key>/` 存在
   - `git -C ~/.codex/checkpoints-online mv codex/<project_key>/<文件名> codex/done/<project_key>/<文件名>`（用 `git mv`，保留历史）

### 4. 同步到 github（无感）

```bash
git -C ~/.codex/checkpoints-online commit --only -m "done(codex/<project_key>): <title> @<done_machine>" -- "codex/<project_key>/<文件名>" "codex/done/<project_key>/<文件名>"
git -C ~/.codex/checkpoints-online push
```

前一步 `git mv` 已暂存本次重命名，不得再用 `git add -A`。`git commit --only -- <源路径> <目标路径>` 用来保证 cc、zcode、shared 或仓库根目录中已有的 staged / unstaged 改动都不会进入本次 commit。

push 失败：`pull --ff-only` 后重试一次；仍失败告诉用户「已本地归档，云端同步失败(原因)，稍后重试」，不丢数据。

### 5. 清理 Codex 上下文

**忘掉"当前维护的 online checkpoint 路径"**——任务已结束，后续 `/checkpoint-online` 走"新建"分支。

### 6. 汇报用户

```
✅ 云端任务已归档并同步：
  原位置：codex/<project_key>/<文件名>
  归档到：codex/done/<project_key>/<文件名>
  push：成功/失败(原因)

继续干别的，还是收工？
```

## 参数

- `$ARGUMENTS` 可选：文件路径 / 数字编号
- 不传：默认归档"当前维护的 online checkpoint"（Codex 上下文里记着的）

## 注意

- **绝不**走"直接 `rm` 删除"分支，只支持归档（移到 done/），保留可追溯性。
- 用户主动喊 `/task-done-online` 即视为确认，禁止插入 y/n 对话；归档到 done/ 可追溯（git mv 反向恢复即可），按"快进快出"处理。

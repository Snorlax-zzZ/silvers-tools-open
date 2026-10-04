标记云端任务完成，把 checkpoint 归档到云端 `done/` 子目录并同步 github（可追溯）。

> **背景**：`/task-done` 的云端版。配套：`/checkpoint-online`（保存）、`/checkpoint-load-online`（加载）。

## 云端工作区

- **本地工作区**：`~/.claude/checkpoints-online/`（你的云端 checkpoint 仓库的 clone，多客户端共用）
- **cc 顶层命名空间**：`cc/`（in-progress 在 `cc/<project_key>/`，归档后落到 `cc/done/<project_key>/`，与其他客户端隔离）
- 工作区内 git 操作已在 permissions 白名单豁免确认。

## 执行步骤

### 0. 确保工作区就绪 + 拉最新

- 工作区不存在 → clone（见 `/checkpoint-online`）
- 已存在 → `git -C ~/.claude/checkpoints-online pull --ff-only`

### 1. 找到要归档的 checkpoint（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | `$ARGUMENTS` 是文件路径（含 `/`） | 用这个 |
| 2 | `$ARGUMENTS` 是纯数字 N | 按 `/checkpoint-load-online` 列表规则（全局所有项目，`updated_at` 倒序）取第 N 个 |
| 3 | 你（cc）在本次对话里记得"当前维护的 online checkpoint 路径" | 用这个 |
| 4 | 以上都没有 | 报错让用户显式指定路径，或先 `/checkpoint-load-online` 恢复上下文 |

**路径边界校验（强制）**：读取、修改和移动前解析 `~`、`.` / `..` 与符号链接。源文件必须位于 `~/.claude/checkpoints-online/cc/<project_key>/` 的活动目录，目标必须位于 `cc/done/<同一 project_key>/`；拒绝越界、其它客户端目录、已归档文件和已存在的目标。`git mv` 后仅以源、目标两个路径执行 `commit --only`，不得使用 `git add -A` 或夹带其它暂存项。

### 2. 显示文件信息（不阻塞）

读 frontmatter 拿 `title`、`machine`，归档前打印一行：

  `准备归档云端：<title>（cc/<project_key>/<文件名>，存档机 <machine>）`

直接进第 3 步，**不要插入 y/n 对话** —— 用户主动喊 `/task-done-online` 即视为确认。

### 3. 归档操作

用户确认后：

1. **更新 frontmatter**：
   - `status: in-progress` → `status: done`
   - 加 `done_at: <当前 ISO8601 时间>`（取时用 GNU date `date '+%Y-%m-%dT%H:%M:%S%z'`）
   - 加 `done_machine: <当前机器 hostname>`（记录是哪台机收的尾，跨机可追溯）
2. **移动文件**：
   - 目标：`~/.claude/checkpoints-online/cc/done/<project_key>/<原文件名>`（done 子目录嵌在 `cc/` 命名空间内）
   - `mkdir -p` 确保 `cc/done/<project_key>/` 存在
   - `git -C ~/.claude/checkpoints-online mv -- "cc/<project_key>/<文件名>" "cc/done/<project_key>/<文件名>"`（用 `git mv`，保留历史）

### 4. 同步到 github（无感）

```bash
git -C ~/.claude/checkpoints-online commit --only -m "done(cc/<project_key>): <title> @<done_machine>" -- "cc/<project_key>/<文件名>" "cc/done/<project_key>/<文件名>"
git -C ~/.claude/checkpoints-online push
```

push 失败：`pull --ff-only` 后重试一次；仍失败告诉用户「已本地归档，云端同步失败(原因)，稍后重试」，不丢数据。

### 5. 清理 cc 上下文

**忘掉"当前维护的 online checkpoint 路径"**——任务已结束，后续 `/checkpoint-online` 走"新建"分支。

### 6. 汇报用户

```
✅ 云端任务已归档并同步：
  原位置：cc/<project_key>/<文件名>
  归档到：cc/done/<project_key>/<文件名>
  push：成功/失败(原因)

继续干别的，还是收工？
```

## 参数

- `$ARGUMENTS` 可选：文件路径 / 数字编号
- 不传：默认归档"当前维护的 online checkpoint"（cc 上下文里记着的）

## 注意

- **绝不**走"直接 `rm` 删除"分支，只支持归档（移到 done/），保留可追溯性。
- 用户主动喊 `/task-done-online` 即视为确认，禁止插入 y/n 对话；归档到 done/ 可追溯（git mv 反向恢复即可），按"快进快出"处理。

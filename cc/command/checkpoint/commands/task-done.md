标记任务完成，把 checkpoint 归档到 `done/` 子目录（可追溯）。

> 配套命令：`/checkpoint`（保存）、`/checkpoint-load`（加载）。完整说明见本工具包的 README。

## 执行步骤

### 1. 找到要归档的 checkpoint（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | `$ARGUMENTS` 是文件路径（含 `/`） | 用这个 |
| 2 | `$ARGUMENTS` 是纯数字 N | 按 `/checkpoint-load` 的列表规则（全局所有项目，`updated_at` 倒序）取第 N 个 |
| 3 | 你（cc）在本次对话里记得"当前维护的 checkpoint 文件路径" | 用这个 |
| 4 | 以上都没有 | 报错让用户显式指定路径，或先 `/checkpoint-load` 把上下文恢复后再 `/task-done` |

### 2. 显示文件信息（不阻塞）

读 frontmatter 拿到 `title`，归档前打印一行：

  `准备归档：<title>（<完整路径>）`

直接进第 3 步，**不要插入 y/n 对话** —— 用户主动喊 `/task-done` 即视为确认。

### 3. 归档操作

用户确认后：

1. **更新 frontmatter**：
   - 把 `status: in-progress` 改为 `status: done`
   - 添加 `done_at: <当前 ISO8601 时间>` 字段
2. **移动文件**：
   - 目标路径：`~/.claude/checkpoints/done/<项目目录名>/<原文件名>`
   - 用 `mkdir -p` 确保 done 子目录存在
   - 用 `mv` 移动（不要先 `cp` 再 `rm`，原子性更好）

### 4. 清理 cc 上下文

**你（cc）忘掉"当前维护的 checkpoint 文件路径"** — 任务已结束，后续 `/checkpoint` 应当走"新建"分支。

### 5. 汇报用户

```
✅ 任务已归档：
  原位置：<原路径>
  归档到：~/.claude/checkpoints/done/<项目目录名>/<文件名>

继续干别的，还是这就收工？
```

## 参数

- `$ARGUMENTS` 可选：文件路径 / 数字编号
- 不传：默认归档"当前维护的 checkpoint"（cc 上下文里记着的那个）

## 注意

- **绝不要**走"直接 `rm` 删除"分支。设计上只支持归档（移到 done/），保留可追溯性。
- 用户主动喊 `/task-done` 即视为确认，禁止插入 y/n 对话；归档到 done/ 可追溯（反向 mv 恢复即可），按"快进快出"处理。

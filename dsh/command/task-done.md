---
name: task-done
description: 任务完成时把 checkpoint 归档到 done 子目录，保留可追溯性
user-invocable: true
---

<!--
用途：/task-done —— 任务收尾，把 checkpoint 从进行中归档到 done/，不再被 /checkpoint-load 列出。
用法：/task-done             归档本会话正在维护的那份
      /task-done <数字>      归档列表第 N 个
      /task-done <路径>      归档指定文件
位置建议：<CHECKPOINT_TOOLS>/dsh/command/task-done.md（DSH 扫 customSkillDirs 的平面 skill 文件）
来源：cc/command/checkpoint/commands/task-done.md 的 DSH 版；配套 checkpoint.md / checkpoint-load.md；设计原理见 <CHECKPOINT_TOOLS>/cc/command/checkpoint/README.md
-->

# /task-done — 归档完成的 checkpoint

DSH执行，对用户称用户。

> 设计上**只支持归档、不支持删除**——归档到 `~/.dsh/checkpoints/done/` 后仍可追溯，反悔了反向 `mv` 回来即可。状态机只有两态：`in-progress` / `done`（告吹的任务也走归档，没有 abandoned 状态）。

## 参数

从用户消息里取参数（`/task-done` 之后的文字）：文件路径 / 数字编号 / 空（默认归档「当前维护的 checkpoint」）。项目根取当前 cwd。

## 执行步骤

### 1. 找到要归档的 checkpoint（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | 用户消息里传了路径（含 `/`） | 用这个 |
| 2 | 用户消息里传了纯数字 N | 按 `/checkpoint-load` 的列表规则（全局所有项目、排序依据倒序）取第 N 个 |
| 3 | 你（DSH）在本次对话里记得「当前维护的 checkpoint 文件路径」 | 用这个 |
| 4 | 以上都没有 | 报错让用户显式指定路径，或先 `/checkpoint-load` 把上下文恢复后再 `/task-done` |

### 2. 显示文件信息（不阻塞）

用 `read` 拿 frontmatter 里的 `title`，归档前打印一行：

```
准备归档：<title>（<完整路径>）
```

直接进第 3 步，**不要插入 y/n 对话**——用户主动喊 `/task-done` 即视为确认。

### 3. 归档操作

1. **更新 frontmatter**：
   - `status: in-progress` → `status: done`
   - 加 `done_at: <当前 ISO8601 时间>`（**先跑一次** `date '+%Y-%m-%dT%H:%M:%S%z'` 取真值，禁止复用对话里的旧时间戳）
2. **移动文件**：
   - 目标路径：`~/.dsh/checkpoints/done/<项目目录名>/<原文件名>`（`<项目目录名>` = cwd 绝对路径把 `/` 换成 `-`）
   - 用 `bash` 跑 `mkdir -p` 确保 done 子目录存在
   - 用 `mv` 移动（**不要**先 `cp` 再 `rm`，`mv` 原子性更好）

### 4. 清理上下文

**忘掉「当前维护的 checkpoint 文件路径」**——任务已结束，后续 `/checkpoint` 应当走「新建」分支。

### 5. 汇报用户

```
✅ 任务已归档：
  原位置：<原路径>
  归档到：~/.dsh/checkpoints/done/<项目目录名>/<文件名>

继续干别的，还是这就收工？
```

## 注意

- **绝不要**走「直接 `rm` 删除」分支，只支持归档。
- 用户主动喊 `/task-done` 即视为确认，**禁止插入 y/n 对话**；归档可追溯，按「快进快出」处理。

## 沙箱提示（DSH 特有）

`~/.dsh/checkpoints/` 在**工作区之外**：`workspace-write` 档下 `mv` 会被沙箱拒绝。遇到拒绝就按沙箱升权流程申请一次更宽档位（`read-only` → `workspace-write` → `danger-full-access` 是封闭阶梯），或让用户用 `/permission` 切到含 full-access 的预设。**不要**为了绕开沙箱把归档目录改到工作区里。详见同目录 `README.md` 的权限章节。

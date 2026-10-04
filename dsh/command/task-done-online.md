---
name: task-done-online
description: 云端任务收尾，把 checkpoint 归档到 dsh/done 并同步 git，保留可追溯性
user-invocable: true
---

<!--
用途：/task-done-online —— /task-done 的云端版：归档到云端 done/ 子目录并 push。
用法：/task-done-online             归档本会话正在维护的那份
      /task-done-online <数字>      归档列表第 N 个
      /task-done-online <路径>      归档指定文件
位置建议：<CHECKPOINT_TOOLS>/dsh/command/task-done-online.md（DSH 扫 customSkillDirs 的平面 skill 文件）
来源：cc/command/checkpoint/commands/task-done-online.md 的 DSH 版；配套 checkpoint-online.md / checkpoint-load-online.md
-->

# /task-done-online — 云端归档并同步

DSH执行，对用户称用户。

> 云端工作区 `~/.dsh/checkpoints-online/`（`<CHECKPOINT_STORE>` 仓库的 clone）。进行中在 `dsh/<project_key>/`，归档后落到 `dsh/done/<project_key>/`，与 cc 的 `cc/` 命名空间互不干扰。

## 参数

从用户消息里取参数（`/task-done-online` 之后的文字）：文件路径 / 数字编号 / 空（默认归档「当前维护的 online checkpoint」）。项目根取当前 cwd。

## 执行步骤

### 0. 确保工作区就绪 + 拉最新

- 工作区不存在 → clone（同 `/checkpoint-online` 步骤 0）
- 已存在 → `git -C ~/.dsh/checkpoints-online pull --ff-only`；失败 / 冲突 → 告诉用户并中止

### 1. 找到要归档的 checkpoint（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | 用户消息里传了路径（含 `/`） | 用这个 |
| 2 | 用户消息里传了纯数字 N | 按 `/checkpoint-load-online` 的列表规则（全局所有项目、排序依据倒序）取第 N 个 |
| 3 | 你（DSH）在本次对话里记得「当前维护的 online checkpoint 路径」 | 用这个 |
| 4 | 以上都没有 | 报错让用户显式指定路径，或先 `/checkpoint-load-online` 恢复上下文 |

**路径边界校验（强制）**：读取、修改和移动前解析 `~`、`.` / `..` 与符号链接。源文件必须位于 `~/.dsh/checkpoints-online/dsh/<project_key>/` 的活动目录，目标必须位于 `dsh/done/<同一 project_key>/`；拒绝越界、其它客户端目录、已归档文件和已存在的目标。`git mv` 后仅以源、目标两个路径执行 `commit --only`，不得使用 `git add -A` 或夹带其它暂存项。

### 2. 显示文件信息（不阻塞）

用 `read` 拿 frontmatter 里的 `title`、`machine`，归档前打印一行：

```
准备归档云端：<title>（dsh/<project_key>/<文件名>，存档机 <machine>）
```

直接进第 3 步，**不要插入 y/n 对话**——用户主动喊 `/task-done-online` 即视为确认。

### 3. 归档操作

1. **更新 frontmatter**：
   - `status: in-progress` → `status: done`
   - 加 `done_at: <当前 ISO8601 时间>`（**先跑一次** `date '+%Y-%m-%dT%H:%M:%S%z'` 取真值，禁止复用对话里的旧时间戳）
   - 加 `done_machine: <当前机器 hostname>`（记录是哪台机收的尾，跨机可追溯）
2. **移动文件**：
   - 目标：`~/.dsh/checkpoints-online/dsh/done/<project_key>/<原文件名>`（done 子目录嵌在 `dsh/` 命名空间内）
   - `mkdir -p` 确保 `dsh/done/<project_key>/` 存在
   - 用 `git -C ~/.dsh/checkpoints-online mv -- "dsh/<project_key>/<文件名>" "dsh/done/<project_key>/<文件名>"`（用 `git mv` 保留历史）

### 4. 同步到云端

```bash
git -C ~/.dsh/checkpoints-online commit --only -m "done(dsh/<project_key>): <title> @<done_machine>" -- "dsh/<project_key>/<文件名>" "dsh/done/<project_key>/<文件名>"
git -C ~/.dsh/checkpoints-online push
```

- **首次推送报 `no upstream branch`** → 改用 `git -C ~/.dsh/checkpoints-online push -u origin HEAD`
- push 失败 → 先 `pull --ff-only` 再重试一次；仍失败就告诉用户「已本地归档，云端同步失败（原因），稍后重试即可」，不丢数据

### 5. 清理上下文

**忘掉「当前维护的 online checkpoint 路径」**——任务已结束，后续 `/checkpoint-online` 走「新建」分支。

### 6. 汇报用户

```
✅ 云端任务已归档并同步：
  原位置：dsh/<project_key>/<文件名>
  归档到：dsh/done/<project_key>/<文件名>
  push：成功/失败(原因)

继续干别的，还是收工？
```

## 注意

- **绝不**走「直接 `rm` 删除」分支，只支持归档（移到 done/），保留可追溯性。
- 用户主动喊 `/task-done-online` 即视为确认，**禁止插入 y/n 对话**；归档可追溯（`git mv` 反向恢复即可），按「快进快出」处理。

## 沙箱提示（DSH 特有）

`~/.dsh/checkpoints-online/` 在**工作区之外**：`workspace-write` 档下写文件与 `git mv` / `push` 都会被沙箱拒绝。遇到拒绝就按沙箱升权流程申请一次更宽档位（`read-only` → `workspace-write` → `danger-full-access`），或让用户用 `/permission` 切到含 full-access 的预设。详见同目录 `README.md` 的权限章节。

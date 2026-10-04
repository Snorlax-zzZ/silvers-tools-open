将当前会话状态归档成精简 checkpoint，供后续 Grok 会话接力。

> 长任务不要靠 `/compact` 省 token。归档 → 新会话 → `/checkpoint-load`。

## 路径

- 项目目录名：工作目录绝对路径把 `/` 和 `\` 换成 `-`
- 根目录：`~/.grok/checkpoints/<项目目录名>/`，没有就建
- 不要写到 `~/.claude/checkpoints/`（那是 cc 的）

## 写哪个文件

1. 用户给了路径参数 → 用它
2. 本次对话已有当前 checkpoint 路径 → 覆盖
3. 否则新建 `YYYYMMDD-HHMMSS-<slug>.md`

slug：8-15 个中文字，去标点。首次定名后不改文件名。

## 写入

先用 `run_terminal_command` 跑 `date '+%Y-%m-%dT%H:%M:%S%z'`，`updated_at` 必须用这次输出。禁止复用对话里的旧时间戳。

Frontmatter：`project_root` / `created_at` / `updated_at` / `title` / `status: in-progress`

正文至少有：任务目标、当前进度、已踩过的认知陷阱、关键决策、Follow-up（P0/P1）。没陷阱写「无」。自称Grok。

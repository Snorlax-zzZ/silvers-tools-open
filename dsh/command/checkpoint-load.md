---
name: checkpoint-load
description: 列出并加载一份 checkpoint，在新会话里接着之前的工作继续干
user-invocable: true
---

<!--
用途：/checkpoint-load —— 新会话（或上下文被压缩后）把归档的 checkpoint 读回来续命。
用法：/checkpoint-load             列所有项目的进行中 checkpoint（当前项目 ⭐ 高亮）
      /checkpoint-load --here      只列当前项目
      /checkpoint-load <数字>      加载列表第 N 个
      /checkpoint-load <路径>      直接读这个文件
位置建议：<CHECKPOINT_TOOLS>/dsh/command/checkpoint-load.md（DSH 扫 customSkillDirs 的平面 skill 文件）
来源：cc/command/checkpoint/commands/checkpoint-load.md 的 DSH 版；配套 checkpoint.md / task-done.md；设计原理见 <CHECKPOINT_TOOLS>/cc/command/checkpoint/README.md
-->

# /checkpoint-load — 加载 checkpoint 继续干

DSH执行，对用户称用户。

> 配套：`/checkpoint`（保存）、`/task-done`（完成归档）。存档根目录 `~/.dsh/checkpoints/`。

## 参数

从用户消息里取参数（`/checkpoint-load` 之后的文字）：

| 用户消息里的参数 | 行为 |
|---|---|
| 文件路径（含 `/`） | 直接读这个路径 |
| 纯数字 N | 加载「列表第 N 个」 |
| `--here` | 只列**当前项目**（基于 cwd）的 checkpoint |
| 空 | 列**所有项目**的进行中 checkpoint（默认行为，当前项目 ⭐ 高亮） |

## 执行步骤

### 1. 扫描列表

**强制调脚本**（别自己写 `for ... do head/grep/stat ... done` 这类复合 shell——多文件读取 + 跨平台 stat 自己拼容易漏文件、算错时间，输出格式也不稳）：

| 模式 | 命令 |
|---|---|
| 默认（全项目） | `bash ~/.dsh/scripts/list-checkpoints.sh` |
| `--here` 模式 | `bash ~/.dsh/scripts/list-checkpoints.sh --here <当前项目目录名>` |

`<当前项目目录名>` = `pwd` 输出把所有 `/` 替换成 `-`（开头也带 `-`）。例如 `/Users/<USER>/Documents/foo` → `-Users-<USER>-Documents-foo`。

脚本已经做好这些事，你只负责解析：

- 已过滤 `status: in-progress`，已排除 `done/` 子目录
- 已读出 `created_at` / `updated_at` / `title` / `mtime`
- 已跨平台处理 stat（mac = BSD，Linux / git-bash = GNU）
- 一个都没命中时安静退出，不报错

**输出格式**（每行一个，`|` 分隔，你直接 split）：

```
FILE|<绝对路径>|PROJ|<项目目录名>|CREATED|<iso>|UPDATED|<iso>|MTIME|<iso>|TITLE|<标题>
```

`TITLE` 可能带前后引号（frontmatter 里 `title: "..."` 原样输出），显示时剥掉。

**时间来源**：脚本已从 frontmatter 出真值，**禁止从文件名前缀**（`20260520-103045-...`）推断时间——文件名只是创建时刻的 slug，反复更新后会和真实 `updated_at` 严重偏离。

**双时间校验（强制）**：每行同时有 `UPDATED`（frontmatter 写入值）和 `MTIME`（文件系统真值），你自己算偏差：

- 偏差 ≤ 5 min：用 `UPDATED` 排序
- 偏差 > 5 min：**用 `max(UPDATED, MTIME)` 当排序依据**，该行前加 ⚠️ 并注明「frontmatter 漂移 X 分钟」
- 动机：写 `updated_at` 时可能复用了对话里的旧时间戳，文件系统 mtime 是兜底真值

**排序**：按上一步算出的排序依据倒序（最近修改在前）。

**显示**：最多 8 个，**两个时间都显示**——「更新 X 前」放主位（排序依据），「创建 X 前」放副位（看出存档跨度）；首次保存时两边一致，合并成 `[更新/创建 X 前]`：

```
找到 N 个进行中 checkpoint：
  1. [更新 5 分钟前 · 创建 4 天前]   [chat-app]        调试 chat-app 0.3.1 sandbox 启动问题
                                                       (20260520-103045-调试sandbox启动.md)
  2. [更新 2 小时前 · 创建 2 小时前] [notify-console]  写通知中心 REST 接口文档
                                                       (20260520-091200-通知中心REST文档.md)
  3. [更新 昨天 · 创建 3 天前]       [personal-blog]   博客发布流程梳理
                                                       (20260519-203018-博客发布流程.md)

⭐ 当前项目（`<当前项目目录名>`）的 checkpoint 已用 ⭐ 标出

输入数字加载，或直接回车跳过：
```

- **项目名**取子目录名最后一段（`-Users-<USER>-Documents-chat-app` → 显示 `chat-app`）
- 当前项目对应的行前加 `⭐`
- 一个都没有 → 告诉用户「全局没有进行中的 checkpoint，要不要先做点啥再回来？」

### 2. 读取选中的 checkpoint

- 用 `read` 工具读全文（这一步的 token 消耗就是 checkpoint 的体积，正常 3-5k）
- **不要**额外读 frontmatter 之外的元数据文件

### 3. 记住文件路径

**在对话上下文里记住「当前维护的 checkpoint 文件路径是 `<完整路径>`」**。同一会话内后续的 `/checkpoint`（覆盖更新）和 `/task-done`（归档）默认对这个文件操作。

### 4. 复述用户对齐

读完后按下面的格式跟用户对齐（**不复读全文，只提炼核心**）：

```
✅ 已加载 `<完整路径>`（约 X.X k token）

**任务**：<title>
**当前进度**：<1-2 句>
**下一步**：<具体动作>

需要我直接开干，还是先讨论一下？
```

等用户确认后再动手。

## 沙箱提示（DSH 特有）

`~/.dsh/checkpoints/` 与 `~/.dsh/scripts/` 都在**工作区之外**，`workspace-write` 档下扫描脚本会读不到 / 起不来。遇到沙箱拒绝就按升权流程申请一次更宽档位（`read-only` → `workspace-write` → `danger-full-access`），或让用户用 `/permission` 切到含 full-access 的预设。详见同目录 `README.md` 的权限章节。

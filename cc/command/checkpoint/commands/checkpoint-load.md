在新会话里加载一份 checkpoint，继续之前会话的工作。

> 配套命令：`/checkpoint`（保存）、`/task-done`（完成归档）。完整说明见本工具包的 README。

## 执行步骤

### 1. 决定加载哪个文件

| 输入 | 行为 |
|---|---|
| `$ARGUMENTS` 是文件路径（含 `/`） | 直接读这个路径 |
| `$ARGUMENTS` 是纯数字 N | 加载"列表第 N 个" |
| `$ARGUMENTS` 是 `--here` | 只列**当前项目**（基于 `pwd`）的 checkpoint |
| `$ARGUMENTS` 为空 | 列**所有项目**的进行中 checkpoint（默认行为） |

### 2. 扫描列表

**强制调脚本**（不要自己写 `for ... do head/grep/stat ... done`，那是 Bash 复合命令，会触发权限确认弹窗，allowlist 救不了）：

| 模式 | 命令 |
|---|---|
| 默认（全项目） | `bash ~/.claude/scripts/list-checkpoints.sh` |
| `--here` 模式 | `bash ~/.claude/scripts/list-checkpoints.sh --here <当前项目目录名>` |

`<当前项目目录名>` = `pwd` 输出把所有 `/` 替换为 `-`（开头也带 `-`）。例如 `/Users/<USERNAME>/Documents/foo` → `-Users-<USERNAME>-Documents-foo`。

脚本已经做好这些事，cc 只负责解析：

- 已过滤 `status: in-progress`，已排除 `done/` 子目录
- 已读出 `created_at` / `updated_at` / `title` / `mtime`
- 已跨平台处理 stat（mac=BSD，Linux/git-bash=GNU）

**输出格式**（每行一个，`|` 分隔，cc 直接 split）：

```
FILE|<绝对路径>|PROJ|<项目目录名>|CREATED|<iso>|UPDATED|<iso>|MTIME|<iso>|TITLE|<标题>
```

`TITLE` 字段可能带前后引号（frontmatter 里 `title: "..."` 原样输出），cc 显示时剥掉即可。

**时间来源**：脚本已经从 frontmatter 出真值，禁止从文件名前缀（`20260520-103045-...`）推断时间——文件名只是创建时刻 slug，持续更新后会和真实 `updated_at` 严重偏离。

**双时间校验（强制）**：每行同时拿到 `UPDATED`（frontmatter 写入值）和 `MTIME`（文件系统真值），cc 自己算偏差：

- 偏差 ≤ 5 min：用 `UPDATED` 排序
- 偏差 > 5 min：**用 `max(UPDATED, MTIME)` 当排序依据**，列表行前加 ⚠️ 并注明「frontmatter 漂移 X 分钟」
- 动机：`/checkpoint` 写 updated_at 时 cc 可能复用对话上下文里旧时间戳，mtime 是文件系统真值，做兜底

**排序**：按上一步算出的排序依据倒序（最近修改在前）

**显示**：最多 8 个，**两个时间都要显示**——「更新 X 前」放主位（排序依据），「创建 X 前」放副位（看出存档跨度）；同一时刻（首次保存）则两边一致，可显示为 `[更新/创建 X 前]` 合并：

```
找到 N 个进行中 checkpoint：
  1. [更新 5 分钟前 · 创建 4 天前]   [chat-app]            调试 chat-app 0.3.1 sandbox 启动问题
                                                          (20260520-103045-调试sandbox启动.md)
  2. [更新 2 小时前 · 创建 2 小时前] [notify-console]      写通知中心 REST 接口文档
                                                          (20260520-091200-通知中心REST文档.md)
  3. [更新 昨天 · 创建 3 天前]       [personal-blog]       博客发布流程梳理
                                                          (20260519-203018-博客发布流程.md)
  ...

⭐ 当前项目 (`<当前项目目录名>`) 的 checkpoint 已用 ⭐ 标出

输入数字加载，或直接 Enter 跳过：
```

- **项目名**取自子目录名最后一段（如 `-Users-<your-username>-Documents-chat-app` → 显示 `chat-app`）
- 列表中**当前项目**对应的 checkpoint 行前加 `⭐` 高亮
- 如果一个都没有，告诉用户「全局没有进行中的 checkpoint，要不要先做点啥再回来？」

### 3. 读取选中的 checkpoint

- 用 Read 工具读全文（这步 token 消耗就是 checkpoint 的体积，正常 3-5k）
- **不要**额外读 frontmatter 之外的元数据文件

### 4. 记住文件路径

**在你的对话上下文里记住"当前维护的 checkpoint 文件路径是 `<完整路径>`"**。后续同一会话内的 `/checkpoint`（覆盖更新）和 `/task-done`（归档）都默认对这个文件操作。

### 5. 复述用户对齐

读完后用以下格式跟用户对齐（**不复读全文，只提炼核心**）：

```
✅ 已加载 `<完整路径>`（约 X.X k token）

**任务**：<title>
**当前进度**：<1-2 句>
**下一步**：<具体动作>

需要我直接开干，还是先讨论一下？
```

等用户确认后再开始执行。

## 参数

- 无参数：列所有项目
- `--here`：只列当前项目
- 数字：列表里选第 N 个
- 文件路径：直接读

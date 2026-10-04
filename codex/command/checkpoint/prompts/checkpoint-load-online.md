---
description: 加载云端 checkpoint 继续任务
argument-hint: 可选：--here / 数字序号 / online checkpoint 路径
---

在新会话 / 另一台机器里加载一份云端 checkpoint，自动折算跨机器路径与命令后继续工作。

> **背景**：`/checkpoint-load` 的云端版。先从 github 拉最新，再列表 / 加载。如果这份 checkpoint 是**别的机器**存的，Codex 读懂 frontmatter 环境块后，把正文里的机器相关路径 / 命令**折算成当前机器的等价形式**再复述。配套：`/checkpoint-online`（保存）、`/task-done-online`（完成归档）。

## 云端工作区

- **本地工作区**：`~/.codex/checkpoints-online/`（你的云端 checkpoint 仓库的 clone，多客户端共用）
- **Codex 顶层命名空间**：`codex/`（只扫描这个子目录，不读取 cc、zcode、shared）
- 工作区内 git 操作已在 permissions 白名单豁免确认。

## 执行步骤

### 0. 确保工作区就绪 + 拉最新（每次都做）

- 工作区不存在 → `git clone <CHECKPOINT_REPO_URL> ~/.codex/checkpoints-online`
- 工作区已存在 → `git -C ~/.codex/checkpoints-online pull --ff-only`（**关键**：load 前必须 pull，才能看到别的机器刚推上来的 checkpoint）
- pull 失败 / 冲突：告诉用户并中止，别强行覆盖。

### 1. 决定加载哪个文件

| 输入 `$ARGUMENTS` | 行为 |
|---|---|
| 文件路径（含 `/`） | 直接读这个路径 |
| 纯数字 N | 加载"列表第 N 个" |
| `--here` | 只列**当前项目**（基于步骤 2 算出的当前 project_key）的 checkpoint |
| 空 | 列**所有项目**的进行中 checkpoint（默认） |

**路径边界校验（强制）**：无论候选文件来自显式参数、数字序号还是扫描列表，读取前都要展开 `~`、解析绝对路径、消解 `.` / `..` 和符号链接。规范化后的绝对路径必须位于 `~/.codex/checkpoints-online/codex/` 内；指向 cc、zcode、shared、仓库根目录或工作区外的路径一律报错并中止，**绝不读取**。显式路径不因用户传入而豁免此边界。

### 2. 算当前机器的 project_key

- 当前目录是 git 仓库 → `git remote get-url origin` 仓库名去 `.git`
- 非 git → `pwd` 的 basename
- 必须是单个目录名：不得为空，不得是 `.` / `..`，不得含 `/`、`\` 或路径穿越片段；不满足时中止
- 用于 `--here` 过滤 + 列表里 ⭐ 高亮当前项目。

### 3. 扫描列表

**强制调脚本**（不要自己写 `for ... do head/grep/stat ... done`，那是 Bash 复合命令，会触发权限确认弹窗，allowlist 救不了）：

| 模式 | 命令 |
|---|---|
| 默认（全项目） | `bash ~/.codex/scripts/list-checkpoints.sh --online` |
| `--here` 模式 | `bash ~/.codex/scripts/list-checkpoints.sh --online --here <当前 project_key>` |

`<当前 project_key>` = 步骤 2 算出的那个值。脚本 `--online` 模式下根目录锁定到
`~/.codex/checkpoints-online/codex/`；`--here` 只在该命名空间匹配目标项目。

脚本已经做好：

- 过滤 `status: in-progress`，排除 `done/`
- 读 `created_at` / `updated_at` / `title` / `machine` / `mtime`
- 跨平台 stat（mac=BSD，Linux/git-bash=GNU）

**输出格式**（每行一个，`|` 分隔）：

```
FILE|<绝对路径>|PROJ|<父目录名>|CREATED|<iso>|UPDATED|<iso>|MTIME|<iso>|MACHINE|<存档机>|TITLE|<标题>
```

`MACHINE` 字段就是 frontmatter 里的 `machine`（存档机），online 版**必显示**（跨机场景要让用户知道是哪台机存的）。`TITLE` 可能带前后引号，剥掉即可。

**时间来源**：脚本已经从 frontmatter 出真值，禁止从文件名前缀（`20260601-103045-...`）推断时间——文件名只是创建时刻 slug，跨机器接力反复更新后会和真实 `updated_at` 严重偏离。

**MTIME 字段语义（online 专属，关键）**：

- `MTIME` 使用 `git log -1 --pretty=format:'%cI' -- <file>` 的最后提交时间，即跨机稳定的 **git commit time**。
- 未提交的新文件才回退文件系统 mtime。
- **禁止用 fs mtime** 作为已提交 online checkpoint 的真值；`git pull` 会刷新落地时间，造成所有文件看起来刚更新。

**双时间校验（强制）**：每行同时拿到 `UPDATED` 与 Git commit time `MTIME`，Codex 自己算偏差：

- 偏差 ≤ 5 min：用 `UPDATED` 排序
- 偏差 > 5 min：**用 `max(UPDATED, MTIME)` 当排序依据**，列表行前加 ⚠️ 并注明「frontmatter 漂移 X 分钟」
- 动机：`updated_at` 可能因上下文复用而漂移；git commit time 是提交当刻真值。

**排序**：按上一步算出的排序依据倒序

**显示**：最多 8 个，**两个时间都要显示**（「更新 X 前」放主位、「创建 X 前」放副位），并**比本地版多一列「存档机」**：

```
☁️  找到 N 个云端进行中 checkpoint：
  1. [更新 5 分钟前 · 创建 4 天前]   [my-project]  〔laptop-main〕  调试 sandbox 启动问题
                                                       (20260601-103045-调试sandbox启动.md)
  2. [更新 2 小时前 · 创建 2 小时前] [chat-app]       〔mac-mini〕     ⭐ 写通知中心 REST 文档
                                                       (20260601-091200-通知中心REST文档.md)
  ...

⭐ = 当前项目(<当前project_key>)｜〔xxx〕= 存档机（与当前机不同则 load 时自动折算路径）

输入数字加载，或直接 Enter 跳过：
```

- 一个都没有 → 「云端没有进行中的 checkpoint。要先 `/checkpoint-online` 存一个吗？」

### 4. 读取选中的 checkpoint

- Read 全文（token 消耗 ≈ checkpoint 体积，正常 3-5k）。

### 5. 跨机器折算（online 核心）

读 frontmatter 环境块，比较**存档机**（`machine` / `os` / `shell`）和**当前机器**：

- **同一台机器**（machine 相同）：直接用，无需折算。
- **不同机器**：Codex 负责把以下内容翻译成当前机器的等价形式——
  - **project_root**：忽略 frontmatter 里记的，用当前 `pwd` 重新确定当前机器上这个项目的根（同一个 `project_key` 在当前机的实际位置）
  - **「环境上下文」段里的绝对路径 / 命令**：按当前机的 os / shell 折算。例：
    - 路径分隔符 `\` ↔ `/`、盘符 `F:\proj` ↔ `/Users/x/proj`
    - 运行时路径（JDK / Python / node / venv）换成当前机的实际位置（不确定的就**标记为待确认**，让用户补，别瞎编）
    - 平台命令换形式（如 PowerShell ↔ bash 取时、文件操作）
  - **正文里的相对路径**：相对 project_root，直接拼当前机的 project_root 即可，无需翻译。
- 折算时**有把握的直接转，没把握的明确标「待用户确认」**，绝不臆造一个看似合理实则错误的路径。

### 6. 记住文件路径

**在对话上下文里记住"当前维护的 online checkpoint 路径是 `<完整路径>`"**。后续同会话 `/checkpoint-online`（覆盖）和 `/task-done-online`（归档）默认对它操作。

### 7. 复述用户对齐

```
✅ 已加载云端 `codex/<project_key>/<文件名>`（约 X.X k token）
   存档机：<machine>(<os>) → 当前机：<当前machine>(<当前os>)〔已折算 / 同机无需折算〕

**任务**：<title>
**当前进度**：<1-2 句>
**下一步**：<具体动作（已折算成当前机命令/路径）>
〔若有待确认的路径〕**待你确认**：<列出折算不确定的路径/命令>

需要我直接开干，还是先对一下？
```

等用户确认后再执行。

## 参数

- 空：列所有项目云端 checkpoint
- `--here`：只列当前项目
- 数字 N：选列表第 N 个
- 文件路径：直接读

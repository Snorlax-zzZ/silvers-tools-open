---
name: checkpoint-load-online
description: 从云端工作区加载 checkpoint，并把别的机器的路径与命令折算成当前机后继续干
user-invocable: true
---

<!--
用途：/checkpoint-load-online —— /checkpoint-load 的云端版：先 pull 最新，再列表/加载；跨机存档自动折算路径与命令。
用法：/checkpoint-load-online             列所有项目的云端进行中 checkpoint
      /checkpoint-load-online --here      只列当前项目（按 project_key）
      /checkpoint-load-online <数字>      加载列表第 N 个
      /checkpoint-load-online <路径>      直接读这个文件
位置建议：<CHECKPOINT_TOOLS>/dsh/command/checkpoint-load-online.md（DSH 扫 customSkillDirs 的平面 skill 文件）
来源：cc/command/checkpoint/commands/checkpoint-load-online.md 的 DSH 版；配套 checkpoint-online.md / task-done-online.md；跨机折算原理见 <CHECKPOINT_TOOLS>/cc/command/checkpoint/README.md 的云端三件套章节
-->

# /checkpoint-load-online — 加载云端 checkpoint 并折算

DSH执行，对用户称用户。

> 云端工作区 `~/.dsh/checkpoints-online/` 是 `<CHECKPOINT_STORE>` 仓库的 clone，多客户端共用；**DSH 只扫自己的 `dsh/` 命名空间**，与 cc 的 `cc/` 隔离。

## 参数

从用户消息里取参数（`/checkpoint-load-online` 之后的文字）：

| 参数 | 行为 |
|---|---|
| 文件路径（含 `/`） | 直接读这个路径 |
| 纯数字 N | 加载「列表第 N 个」 |
| `--here` | 只列**当前项目**（按下面算出的当前 project_key）的 checkpoint |
| 空 | 列**所有项目**的进行中 checkpoint（默认） |

## 执行步骤

### 0. 确保工作区就绪 + 拉最新（每次都做）

- 工作区不存在 → `git clone <CHECKPOINT_REPO_URL> ~/.dsh/checkpoints-online`
- 工作区已存在 → `git -C ~/.dsh/checkpoints-online pull --ff-only`（**关键**：load 前必须 pull，才看得到别的机器刚推上来的 checkpoint）
- pull 失败 / 冲突 → 告诉用户并中止，别强行覆盖

### 1. 算当前机器的 project_key

- 当前目录是 git 仓库 → `git remote get-url origin` 的仓库名去掉 `.git` 后缀
- 非 git → `pwd` 的 basename
- 用途：`--here` 过滤 + 列表里 ⭐ 高亮当前项目

**路径边界校验（强制）**：选中文件后、读取前展开 `~`，消解 `.` / `..` 并解析符号链接；规范化路径必须位于 `~/.dsh/checkpoints-online/dsh/`，其它客户端目录或工作区外路径一律停止，不读取。

### 2. 扫描列表

**强制调脚本**（别自己写 `for ... do head/grep/stat ... done` 复合 shell——多文件读取 + 跨平台 stat + git log 取值自己拼容易漏文件、算错时间，输出格式也不稳）：

| 模式 | 命令 |
|---|---|
| 默认（全项目） | `bash ~/.dsh/scripts/list-checkpoints.sh --online` |
| `--here` 模式 | `bash ~/.dsh/scripts/list-checkpoints.sh --online --here <当前 project_key>` |

`--online` 模式下脚本的扫描根**已锁定到 `~/.dsh/checkpoints-online/dsh/`**（DSH 命名空间），不会扫到 `cc/` 等别的客户端目录。`--here` 用 `*/$project_key/*.md` 形式的路径通配，能命中 `dsh/<project_key>/*.md`（单层）和将来可能的多层结构。

脚本已经做好这些事：

- 已过滤 `status: in-progress`，已排除 `done/` 子目录
- 已读出 `created_at` / `updated_at` / `title` / `machine` / mtime
- 已跨平台处理 stat（mac = BSD，Linux / git-bash = GNU）

**输出格式**（每行一个，`|` 分隔）：

```
FILE|<绝对路径>|PROJ|<父目录名>|CREATED|<iso>|UPDATED|<iso>|MTIME|<iso>|MACHINE|<存档机>|TITLE|<标题>
```

`MACHINE` 就是 frontmatter 里的 `machine`（存档机），online 版**必显示**（跨机场景要让用户知道是哪台机存的）。`TITLE` 可能带前后引号，剥掉。

**时间来源**：脚本已从 frontmatter 出真值，**禁止从文件名前缀**（`20260601-103045-...`）推断时间——文件名只是创建时刻的 slug，跨机反复更新后会和真实 `updated_at` 严重偏离。

**MTIME 字段语义（online 专属，关键）**：

- `--online` 模式下脚本输出的 `MTIME` **不是文件系统 mtime**，而是 `git log -1 --pretty=format:'%cI' -- <file>`（这份 checkpoint 最后一次被 commit 的时间）
- 原因：`git pull` 落地时 fs mtime 会被刷新成 pull 时刻，跟「谁最后动过这份 checkpoint」完全无关；git commit time 跨机一致，才是真值
- 还没 commit 的全新文件 → 脚本 fallback 到 fs mtime（这种情况两者等价）
- 历史教训：曾把 fs mtime 当成「跨机场景下谁最新动过」的近似，结果列表里所有 checkpoint 都显示「几分钟前更新」（其实是几分钟前 pull 的），信噪比全丢

**双时间校验（强制）**：每行同时有 `UPDATED`（frontmatter 写入值）和 `MTIME`（git commit time），你自己算偏差：

- 偏差 ≤ 5 min：用 `UPDATED` 排序（正常情况——保存时按规矩跑 `date` 写 `updated_at`，紧接着 commit）
- 偏差 > 5 min：**用 `max(UPDATED, MTIME)` 当排序依据**，该行前加 ⚠️ 并注明「frontmatter 漂移 X 分钟」
- **禁止用 fs mtime 兜底**——online 场景下 fs mtime 是 pull 落地时间，纯噪声

**排序**：按上一步算出的排序依据倒序。

**显示**：最多 8 个，**两个时间都显示**（「更新 X 前」主位、「创建 X 前」副位），并**比本地版多一列「存档机」**：

```
☁️  找到 N 个云端进行中 checkpoint：
  1. [更新 5 分钟前 · 创建 4 天前]   [my-project]  〔laptop-main〕  调试 sandbox 启动问题
                                                       (20260601-103045-调试sandbox启动.md)
  2. [更新 2 小时前 · 创建 2 小时前] [chat-app]        〔mac-mini〕     ⭐ 写通知中心 REST 文档
                                                       (20260601-091200-通知中心REST文档.md)

⭐ = 当前项目（<当前 project_key>）｜〔xxx〕= 存档机（与当前机不同则 load 时自动折算路径）

输入数字加载，或直接回车跳过：
```

- 一个都没有 → 「云端没有进行中的 checkpoint。要先 `/checkpoint-online` 存一个吗？」

### 3. 读取选中的 checkpoint

- 用 `read` 读全文（token 消耗 ≈ checkpoint 体积，正常 3-5k）

### 4. 跨机器折算（online 核心）

读 frontmatter 环境块，比较**存档机**（`machine` / `os` / `shell`）和**当前机器**：

- **同一台机器**（machine 相同）→ 直接用，无需折算
- **不同机器** → 你负责把下面这些翻译成当前机器的等价形式：
  - **project_root**：忽略 frontmatter 里记的，用当前 `pwd` 重新确定当前机器上这个项目的根（同一个 `project_key` 在当前机的实际位置）
  - **「环境上下文」段里的绝对路径 / 命令**：按当前机的 os / shell 折算。例：
    - 路径分隔符 `\` ↔ `/`、盘符 `F:\proj` ↔ `/Users/x/proj`
    - 运行时路径（JDK / Python / node / venv）换成当前机的实际位置，**不确定的就标「待用户确认」**，别瞎编
    - 平台命令换形式（如取时、文件操作）
  - **正文里的相对路径**：相对 project_root，拼上当前机的 project_root 即可，无需翻译
- 折算时**有把握的直接转，没把握的明确标「待用户确认」**，绝不臆造一个看似合理实则错误的路径

### 5. 记住文件路径

**在对话上下文里记住「当前维护的 online checkpoint 路径是 `<完整路径>`」**。同一会话内后续 `/checkpoint-online`（覆盖）和 `/task-done-online`（归档）默认对它操作。

### 6. 复述用户对齐

```
✅ 已加载云端 `dsh/<project_key>/<文件名>`（约 X.X k token）
   存档机：<machine>(<os>) → 当前机：<当前 machine>(<当前 os>)〔已折算 / 同机无需折算〕

**任务**：<title>
**当前进度**：<1-2 句>
**下一步**：<具体动作（已折算成当前机命令/路径）>
〔若有待确认的路径〕**待你确认**：<列出折算不确定的路径/命令>

需要我直接开干，还是先对一下？
```

等用户确认后再执行。

## 沙箱提示（DSH 特有）

`~/.dsh/checkpoints-online/` 与 `~/.dsh/scripts/` 都在**工作区之外**：`workspace-write` 档下 `git pull` 与脚本读取会被沙箱拒绝。遇到拒绝就按沙箱升权流程申请一次更宽档位（`read-only` → `workspace-write` → `danger-full-access`），或让用户用 `/permission` 切到含 full-access 的预设。详见同目录 `README.md` 的权限章节。

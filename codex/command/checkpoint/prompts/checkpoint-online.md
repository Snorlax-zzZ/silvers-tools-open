---
description: 保存当前会话为云端 checkpoint，便于跨机器恢复
argument-hint: 可选：online checkpoint 文件路径（用于覆盖）
---

把当前会话状态归档成精简 checkpoint，并同步到 github 云端，供跨机器 / 跨会话接力。

> **背景**：`/checkpoint` 的云端版。存档落到一个 clone 在本地的 github 仓库工作区，写完自动 commit + push。frontmatter 多记一段「环境块」（机器 / 系统 / shell / project_key），正文里机器相关路径与命令集中归档，供另一台机器 `/checkpoint-load-online` 时自动折算还原。完整说明见本工具包 README 的云端三件套章节。

## 云端工作区

- **仓库**：`<CHECKPOINT_REPO_URL>`（多客户端共用，按顶层 subdir 分命名空间）
- **本地工作区**：`~/.codex/checkpoints-online/`
- **Codex 顶层命名空间**：`codex/`（仓库内只读写自己的子目录，与 cc、zcode、shared 隔离）
- 工作区内的 `git add/commit/push/pull` 已在 permissions 白名单豁免确认（仅限这个目录），无感同步。

## 执行步骤

### 0. 确保工作区就绪（每次都做）

- 工作区不存在 → `git clone <CHECKPOINT_REPO_URL> ~/.codex/checkpoints-online`
- 工作区已存在 → 先 `git -C ~/.codex/checkpoints-online pull --ff-only`（拿别的机器推上来的最新，避免后面 push 冲突）
- pull 出现冲突 / 失败：告诉用户「云端工作区拉取异常，先别 checkpoint，需要我看看冲突吗？」，**中止**，不要强行覆盖。

### 1. 计算 project_key 与存档目录

- **project_key**（跨机稳定标识，不用绝对路径）：
  - 当前目录是 git 仓库 → 取 `git remote get-url origin` 的仓库名（去掉 `.git` 后缀），例：`...my-project.git` → `my-project`
  - 非 git 项目 → 取当前工作目录名（`pwd` 的 basename），例：`/f/my-notes` → `my-notes`
  - 必须是单个目录名：不得为空，不得是 `.` / `..`，不得含 `/`、`\` 或路径穿越片段；不满足时中止并告诉用户
- **存档目录**：`~/.codex/checkpoints-online/codex/<project_key>/`（**Codex 顶层命名空间下**），不存在则 `mkdir -p`

> 注意：跟本地版 `/checkpoint` 不同——online 版按 `codex/<project_key>` 分目录，
> 同一项目跨机器仍落在同一目录，同时不会与其他客户端互相覆盖。

### 2. 决定写哪个文件（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | 用户传了路径参数 `$ARGUMENTS`（且非空） | 用这个路径（覆盖更新） |
| 2 | 你（Codex）在**本次对话**里记得"当前维护的 online checkpoint 路径"（之前 load 过或创建过） | 用这个路径（覆盖更新） |
| 3 | 都没有 | 新建 `<存档目录>/YYYYMMDD-HHMMSS-<slug>.md`（即 `~/.codex/checkpoints-online/codex/<project_key>/...`）；同秒已存在则追加毫秒 `YYYYMMDD-HHMMSS-NNN-<slug>.md` |

**路径边界校验（强制）**：无论候选路径来自 `$ARGUMENTS`、对话记忆还是新建逻辑，写入前都要展开 `~`、把相对路径解析为绝对路径、消解 `.` / `..`，并解析现有文件或其父目录的符号链接。规范化后的绝对路径必须位于 `~/.codex/checkpoints-online/codex/` 内，且本命令的目标必须位于 `codex/<当前 project_key>/` 这一层；路径越界、指向其他客户端目录或 project_key 不一致时，明确报错并中止，**绝不读取、覆盖、stage 或提交该路径**。

**slug 规则**（同本地版）：从任务标题提炼 8-15 个中文字核心描述，去标点空格；首次创建定死不再改；列表展示用 frontmatter 的 `title`。

### 3. 采集环境元数据

- **machine**：`hostname`（跨平台都有）
- **os**：`uname -s`（Git Bash 下 Windows 返回 `MINGW*`/记为 `win32`，mac `Darwin`→`darwin`，Linux→`linux`），拿不准就按你已知的当前运行环境填
- **shell**：当前 shell（`bash` / `zsh` / `pwsh`）
- **project_root**：`pwd` 的绝对路径
- **取时间**：`date '+%Y-%m-%dT%H:%M:%S%z'`（GNU date）

### 4. 写入文档

**前置（强制）**：写入前必须先跑一次 `date '+%Y-%m-%dT%H:%M:%S%z'` 拿当前真实时间。`updated_at` 字段必须用这次跑出来的值，**禁止从对话上下文复用任何已有时间戳**（包括 frontmatter 里原有的 `updated_at`、之前跑 date 的输出、对话里出现过的时间引用）。长会话上下文里的时间戳极易漂移（曾出现 2h12m 偏差），这是硬约束。跨机器场景尤其要警惕——别用别的机器存档时的时间戳冒充当前机器的。

**Frontmatter**（环境块是 online 版核心增量）：

```yaml
---
project_key: <跨机稳定标识，见步骤 1>
codex_subdir: codex            # 固定值，标注本 checkpoint 属于 Codex 命名空间
machine: <存档机标识，hostname>
os: <win32 | darwin | linux>
shell: <bash | zsh | pwsh>
project_root: <存档机上的绝对路径，仅记录；load 时勿照搬，用当前机 pwd 重算>
created_at: <首次创建时填，复用则保持不变>
updated_at: <每次写入刷新为当前 ISO8601，含时区>
title: "<一句话任务标题，10-25 字>"
status: in-progress
---
```

**正文推荐结构**（跟 `/checkpoint` 同一套，额外多一段「环境上下文」）：

```markdown
## 任务目标
1-2 句话，用户启动这个任务时想要的最终结果。

## 当前进度
做到哪一步、下一步要干啥，3-5 行。

## 🚨 已踩过的认知陷阱（强制段,新 Codex 必读)
列出本轮探索中**走错并被纠正**的认知误区。新 Codex 拉起来如果不读这段,
极容易再次走同一个弯路。每条三段式:
- **陷阱**:（描述误区,比如"把 X 概念当成 Y 概念"/"以为 A 必须有 B"）
  - **真相**：（澄清后的正确认知）
  - **来源**：（哪句话 / 哪个文件 / 哪次澄清纠正的,含时间戳）

如果本轮真的没踩过认知陷阱,写"无（任务直线推进）"。**不要为了凑段编**。

## 关键决策（强制段,三段式: 决策 | 理由 | 来源,第四项按需）
- **决策**：（做了什么决断,如"采用 X 方案 / 删 Y 模块 / 选 Z 库"）
  - **理由**：（为什么这样,跟其他备选方案对比的核心差异点）
  - **来源**：（用户某次拍板 / 某轮 verify 反馈 / 实测发现,含时间戳）
  - **放弃的备选**：（认真比较过并否掉的方案 + 否掉的原因,防止下一轮 Codex 把它重新捡回来提一遍）
    **没有实质备选就不写这一项,不要为了凑格式编一个假备选**——只有一条自然路径的任务,省掉它才是对的。

## 关键发现（可选段,技术事实 / 位置）
- xxx 文件 line N 有竞态条件
- 上游 schema 字段类型严格性等非平凡事实

## Follow-up 清单（强制段,按触发条件分层）
没 follow-up 时写"无"占一行也要保留段。

### P0 - 主链路阻塞
（当前主任务收口前必须完成的）

### P1 - 主链路一并验证
（联调 / 主流程跑通过程中要 verify 的）

### P2 - 主链路完成后清理
（功能跑通后再做的）

### longterm 架构债
（评估后做的,可能跨发布周期）

每条要明示**触发条件**（什么时候做）+ **实施位置**（在哪改）。

## 联调步骤（可选段,任务真有联调 / 验证流程才写）
具象到能直接照着跑:
1. 启动命令:`<完整命令,含工作目录>`
2. 准备数据:认证信息 / 测试租户 / fixture 数据 来源
3. 调用模板:`<curl / 测试入口完整命令>`
4. 验证方式:`<diff 命令 / 看日志关键字 / 等等>`

## 🖥️ 环境上下文（online 专用,跨机还原依据）
本 checkpoint 在以下环境存档，load 到别的机器时 Codex 按此折算：
- **存档机**：<machine>（os: <os>，shell: <shell>）
- **项目根**：<project_root>  ← 当前机器请用 `pwd` 重新确定，**勿照搬本行**
- **机器相关的绝对路径 / 命令**（以下都是存档机形式，load 时翻译成当前机等价）：
  - 启动命令：`<含工作目录的完整命令>`
  - 运行时 / 工具路径：`<JDK / Python / node / venv 等存档机绝对路径>`
  - 其它平台相关命令：`<如取时、文件操作等>`

## 引用（不复述内容,只列路径）
- 设计文档：docs/architecture/xxx.md
- 关键 commit：`abc1234` <description>
- 已读关键文件：src/xxx.py（line N 是核心）

## 下一步建议
- 立即要做：xxx
- 可能要用的 skill：superpowers:test-driven-development
- 待确认问题：xxx

## ⚠️ AI verify 边际效用提醒（可选段,经过多轮 AI 审的任务才写）
避免新 Codex 又陷入"再审一轮"循环。
- 已做:<某某工具> 各 N 轮,产出报告 `xxx.md`
- 不要再做:第 N+1 轮 AI verify 边际效用极低
  （典型征兆:上一轮所有 BLOCKER 已修,只剩 NIT）
- 下一步建议:真实流量 / 联调驱动,跑出真问题再修;不要继续 AI 审
```

**可移植性铁律**（写正文时严格遵守，否则跨机还原会出错）：

- ✅ **项目内文件路径一律写相对 project_root 的相对路径**（如 `src/xxx.py`、`codex/command/...`），跨机天然通用
- ✅ **机器相关的绝对路径 / 命令集中写进「环境上下文」段**，不要散落在正文各处
- ✅ 引用 commit、文件位置等照本地版（只列不复述）
- ❌ 不要在「当前进度」「下一步」等段落里写死存档机的绝对路径（如 `F:\...` / `/Users/...`）——要写就写相对路径，或指向「环境上下文」段

### 5. 同步到 github（无感，工作区内已豁免确认）

```bash
git -C ~/.codex/checkpoints-online add "codex/<project_key>/<文件名>"
git -C ~/.codex/checkpoints-online commit --only -m "checkpoint(codex/<project_key>): <title> @<machine>" -- "codex/<project_key>/<文件名>"
git -C ~/.codex/checkpoints-online push
```

`git commit --only -- <Codex path>` 是共享仓库隔离边界：即使 cc、zcode、shared 或仓库根目录已有 staged 改动，也不得把它们带进本次 commit。

- **首次推送 / 报 "no upstream branch"**（空仓库或本地分支没设上游）：改用 `git -C ~/.codex/checkpoints-online push -u origin HEAD`。
- push 失败（网络不通 / 远端有新提交）：先 `git -C ~/.codex/checkpoints-online pull --ff-only` 再重试 push 一次；仍失败则告诉用户「文件已本地保存到 `<路径>`，云端同步失败（原因），稍后重试 `/checkpoint-online` 即可补推」，**不要丢数据**。

### 6. 记住当前文件路径

写入完成后，**在对话上下文里记住"当前维护的 online checkpoint 路径是 `<完整路径>`"**。后续同会话内的 `/checkpoint-online` 和 `/task-done-online` 默认对它操作。

### 7. 汇报用户

```
✅ 已保存并同步到云端：`codex/<project_key>/<文件名>`（约 X.X k token，覆盖/新建）
   存档机：<machine>（<os>）｜push：成功/失败(原因)
```

## 字段使用指导

上面的字段**只是参考结构，不是必须照搬的模板**。

**写作核心**：让另一台机器上全新的 Codex 读完能在 5 分钟内知道「做到哪 + 下一步干啥 + 在当前机器怎么跑起来」。

按任务情况调整：
- 简单任务可能只需要"当前进度 + 下一步"
- 复杂调试可能要展开"已排除路径"
- 多模块改动可能要加"涉及文件清单"

Codex 你自己判断哪些字段该留、该详细、该砍掉。智商在线，别照搬。

**唯一例外**：「环境上下文」段在 online 版是**强制**的——它是另一台机器还原路径 / 命令的唯一依据，再简单的任务也要写。

## 写作铁律

- ❌ 不要把读过的文件内容粘贴进来
- ❌ 不要复制 diff、commit、PR 描述
- ❌ 不要把已经在 plan/ADR/CONTEXT.md 里的决策再抄一遍
- ✅ 只记结论不记过程
- ✅ 死路也要记（避免下一轮 Codex 再走）
- ✅ 用项目术语（参考项目根 AGENTS.md / CONTEXT.md 里的语言）

## 体积约束（硬性）

目标 **3-5k token**（约 2000-4000 中文字，视 tokenizer 而定），超 5k 必须砍。环境块只占几行，别让它喧宾夺主。

## 参数

- `$ARGUMENTS` 可选：要更新的文件路径（兜底，Codex 上下文丢失时显式指定）。

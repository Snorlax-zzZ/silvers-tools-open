---
name: checkpoint-online
description: 把会话状态归档成精简 checkpoint 并同步到云端 git 工作区，供跨机器接力
user-invocable: true
---

<!--
用途：/checkpoint-online —— /checkpoint 的云端版：存档落到本地 clone 的 github 工作区，写完自动 commit + push，供另一台机器 /checkpoint-load-online 折算还原。
用法：/checkpoint-online            新建一份，或覆盖本会话正在维护的那份
      /checkpoint-online <路径>     显式指定要覆盖的文件（兜底）
位置建议：<CHECKPOINT_TOOLS>/dsh/command/checkpoint-online.md（DSH 扫 customSkillDirs 的平面 skill 文件）
来源：cc/command/checkpoint/commands/checkpoint-online.md 的 DSH 版；云端版设计与跨机折算原理见 <CHECKPOINT_TOOLS>/cc/command/checkpoint/README.md 的云端三件套章节
-->

# /checkpoint-online — 归档并同步到云端

DSH执行，对用户称用户。

> **纯本地版不够用、要 mac ↔ Windows 跨端接力时用这套**。本地三件套（`/checkpoint` 等）保持纯本地不动，两套平行独立、各有各的存储目录。

## 云端工作区

- **仓库**：`<CHECKPOINT_REPO_URL>`（多客户端共用一个仓库，按顶层目录分命名空间）
- **本地工作区**：`~/.dsh/checkpoints-online/`（就是该仓库的 clone）
- **DSH 命名空间**：`dsh/`——**只读写自己这个子目录**，与 cc 的 `cc/`、其它客户端的目录互不干扰
- 工作区内的 git 操作在 DSH 侧**没有 cc 那种「仅限本目录的豁免白名单」**：它就是普通 `bash` 调用，受当前沙箱档位与审批策略约束（见同目录 `README.md` 权限章节）

## 参数

从用户消息里取参数（`/checkpoint-online` 之后的文字）当要写入 / 覆盖的文件路径；为空走步骤 2 的默认判定。项目根取当前 cwd。

## 执行步骤

### 0. 确保工作区就绪（每次都做）

- 工作区不存在 → `git clone <CHECKPOINT_REPO_URL> ~/.dsh/checkpoints-online`
- 工作区已存在 → 先 `git -C ~/.dsh/checkpoints-online pull --ff-only`（拿别的机器推上来的最新，避免后面 push 冲突）
- pull 冲突 / 失败 → 告诉用户「云端工作区拉取异常，先别 checkpoint，需要我看看冲突吗？」，**中止**，不要强行覆盖

### 1. 计算 project_key 与存档目录

- **project_key**（跨机稳定标识，不用绝对路径）：
  - 当前目录是 git 仓库 → 取 `git remote get-url origin` 的仓库名（去掉 `.git` 后缀），例：`...my-project.git` → `my-project`
  - 非 git 项目 → 取当前工作目录名（`pwd` 的 basename），例：`/f/my-notes` → `my-notes`
- **存档目录**：`~/.dsh/checkpoints-online/dsh/<project_key>/`，不存在则 `mkdir -p`

> 跟本地版 `/checkpoint` 的关键差异：本地版按「绝对路径 `/` → `-`」分目录（同一项目在不同机器目录名不同）；online 版按 `dsh/<project_key>` 分目录，这样 mac 和 Windows 上的**同一个项目落到同一个目录**，跨机接力才成立。

### 2. 决定写哪个文件（按优先级）

| 优先级 | 条件 | 行为 |
|---|---|---|
| 1 | 用户消息里传了路径（非空） | 用这个路径（覆盖更新） |
| 2 | 你（DSH）在**本次对话**里记得「当前维护的 online checkpoint 路径」 | 用这个路径（覆盖更新） |
| 3 | 都没有 | 新建 `<存档目录>/YYYYMMDD-HHMMSS-<slug>.md`；同秒已存在则追加毫秒 `YYYYMMDD-HHMMSS-NNN-<slug>.md` |

**slug 规则**（同本地版）：从任务标题提炼 8-15 个中文字核心描述，去标点空格；首次创建定死不再改；列表展示用 frontmatter 的 `title`。

**路径边界校验（强制）**：写入前展开 `~`，消解 `.` / `..`，解析现有文件及父目录的符号链接。目标必须位于 `~/.dsh/checkpoints-online/dsh/<当前 project_key>/` 的活动目录；`project_key` 必须是非空单个目录名，不能为 `.` / `..`，不能包含 `/` 或 `\`。越界或来自其它客户端的文件只可只读参考，禁止读取后原地覆盖、stage 或提交。

提交使用 `commit --only -- <目标路径>`，保留其它文件的暂存状态，不把它们夹带进本次提交。

### 3. 采集环境元数据

- **machine**：`hostname`
- **os**：`uname -s` 折算成 `darwin` / `linux` / `win32`（git-bash 下 Windows 返回 `MINGW*`，记 `win32`）；拿不准就按你已知的当前运行环境填
- **shell**：当前 shell（`bash` / `zsh` / `pwsh`）
- **project_root**：`pwd` 的绝对路径
- **取时间**：跑一次 `date '+%Y-%m-%dT%H:%M:%S%z'`

### 4. 写入文档

**前置（强制）**：写入前必须先跑一次 `date '+%Y-%m-%dT%H:%M:%S%z'`。`updated_at` 必须用这次跑出来的值，**禁止复用对话上下文里任何已有时间戳**（含 frontmatter 里原有的 `updated_at`、之前跑 date 的输出）。长会话里的时间戳极易漂移（曾出现 2h12m 偏差）；跨机器场景尤其要警惕——别拿别的机器存档时的时间戳冒充当前机器。

**Frontmatter**（环境块是 online 版的核心增量）：

```yaml
---
project_key: <跨机稳定标识，见步骤 1>
dsh_subdir: dsh                 # 固定值，标注本 checkpoint 属于 DSH 客户端命名空间
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
（1-2 句话，用户启动这个任务时想要的最终结果）

## 当前进度
（做到哪一步、下一步要干啥，3-5 行）

## 🚨 已踩过的认知陷阱（强制段，新 session 必读）
- **陷阱**：（描述误区）
  - **真相**：（澄清后的正确认知）
  - **来源**：（哪句话 / 哪个文件 / 哪次澄清纠正的，含时间戳）

真没踩过就写「无（任务直线推进）」。不要为了凑段编。

## 关键决策（强制段，三段式 决策 | 理由 | 来源，第四项按需）
- **决策**：（做了什么决断）
  - **理由**：（为什么这样，跟备选方案对比的核心差异点）
  - **来源**：（用户拍板 / 某轮 verify 反馈 / 实测发现，含时间戳）
  - **放弃的备选**：（认真比较过并否掉的方案 + 否掉原因）没有实质备选就不写。

## 关键发现（可选段，技术事实 / 位置）
- xxx 文件 line N 有竞态条件

## Follow-up 清单（强制段，按触发条件分层）
没 follow-up 时写「无」占一行，段也要保留。
### P0 - 主链路阻塞
### P1 - 主链路一并验证
### P2 - 主链路完成后清理
### longterm 架构债
每条明示触发条件 + 实施位置。

## 联调步骤（可选段，任务真有联调 / 验证流程才写）
1. 启动命令：`<完整命令，含工作目录>`
2. 准备数据：认证信息 / 测试租户 / fixture 数据来源
3. 调用模板：`<curl / 测试入口完整命令>`
4. 验证方式：`<diff 命令 / 看日志关键字>`

## 🖥️ 环境上下文（online 专用，跨机还原依据 —— 强制段）
本 checkpoint 在以下环境存档，load 到别的机器时按此折算：
- **存档机**：<machine>（os: <os>，shell: <shell>）
- **项目根**：<project_root>  ← 当前机器请用 `pwd` 重新确定，**勿照搬本行**
- **机器相关的绝对路径 / 命令**（以下都是存档机形式，load 时翻译成当前机等价）：
  - 启动命令：`<含工作目录的完整命令>`
  - 运行时 / 工具路径：`<JDK / Python / node / venv 等存档机绝对路径>`
  - 其它平台相关命令：`<如取时、文件操作等>`

## 引用（不复述内容，只列路径）
- 设计文档：docs/architecture/xxx.md
- 关键 commit：`abc1234` <description>
- 已读关键文件：src/xxx.py（line N 是核心）

## 下一步建议
- 立即要做：xxx
- 可能要用的 skill：test-driven-development
- 待确认问题：xxx

## ⚠️ AI verify 边际效用提醒（可选段，经过多轮 AI 审的任务才写）
- 已做：<某某工具> 各 N 轮，产出报告 `xxx.md`
- 不要再做：第 N+1 轮 AI verify 边际效用极低
- 下一步建议：真实流量 / 联调驱动，跑出真问题再修
```

**可移植性铁律**（不遵守跨机还原必出错）：

- ✅ **项目内路径一律写相对 project_root 的相对路径**（如 `src/xxx.py`、`dsh/command/...`），跨机天然通用
- ✅ **机器相关的绝对路径 / 命令集中写进「环境上下文」段**，不要散落在正文各处
- ✅ 引用 commit、文件位置等照本地版（只列不复述）
- ❌ 不要在「当前进度」「下一步」等段里写死存档机的绝对路径（`F:\...` / `/Users/...`）——要写就写相对路径，或指向「环境上下文」段

### 5. 同步到云端

```bash
git -C ~/.dsh/checkpoints-online add "dsh/<project_key>/<文件名>"
git -C ~/.dsh/checkpoints-online commit --only -m "checkpoint(dsh/<project_key>): <title> @<machine>" -- "dsh/<project_key>/<文件名>"
git -C ~/.dsh/checkpoints-online push
```

- **首次推送报 `no upstream branch`**（空仓库或本地分支没设上游）→ 改用 `git -C ~/.dsh/checkpoints-online push -u origin HEAD`
- push 失败（远端有新提交 / 本地分支无上游）→ 先 `pull --ff-only` 再重试一次；仍失败就告诉用户「文件已本地保存到 `<路径>`，云端同步失败（原因），稍后重试 `/checkpoint-online` 即可补推」，**不要丢数据**

### 6. 记住当前文件路径

写完**在对话上下文里记住「当前维护的 online checkpoint 路径是 `<完整路径>`」**。同一会话内后续的 `/checkpoint-online` 和 `/task-done-online` 默认对它操作。

### 7. 汇报用户

```
✅ 已保存并同步到云端：`dsh/<project_key>/<文件名>`（约 X.X k token，覆盖/新建）
   存档机：<machine>（<os>）｜push：成功/失败(原因)
```

## 字段使用指导

上面的字段**只是参考结构**。

**写作核心**：让另一台机器上全新的会话读完能在 5 分钟内知道「做到哪 + 下一步干啥 + 在当前机器怎么跑起来」。

按任务情况调整：简单任务可能只要「当前进度 + 下一步」；复杂调试可能要展开「已排除路径」；多模块改动可能要加「涉及文件清单」。你自己判断哪些段该留、该详细、该砍掉。

**唯一例外**：「环境上下文」段在 online 版是**强制**的——它是另一台机器还原路径 / 命令的唯一依据，再简单的任务也要写。

## 写作铁律

- ❌ 不要把读过的文件内容粘贴进来
- ❌ 不要复制 diff、commit 信息、PR 描述
- ❌ 不要把已经写在 plan / ADR / 设计文档里的决策再抄一遍
- ✅ 只记结论不记过程
- ✅ 死路也要记
- ✅ 用项目术语（参考项目根的 `AGENTS.md` / `CLAUDE.md`）

## 体积约束（硬性）

目标 **3-5k token**（约 2000-4000 中文字），超 5k 必须砍。环境块只占几行，别让它喧宾夺主。

## 沙箱提示（DSH 特有）

`~/.dsh/checkpoints-online/` 在**工作区之外**：`workspace-write` 档下写文件与 `git` 操作都会被沙箱拒绝。遇到拒绝就按沙箱升权流程申请一次更宽档位（`read-only` → `workspace-write` → `danger-full-access`），或让用户用 `/permission` 切到含 full-access 的预设。详见同目录 `README.md` 的权限章节。

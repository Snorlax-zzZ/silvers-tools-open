---
name: checkpoint-shared-load
description: 拉取公共接力区，列出一份进行中的共享 checkpoint，校验并折算到当前机器后接棒
user-invocable: true
---

<!--
用途：/checkpoint-shared-load —— Checkpoint Shared 三件套的「接棒」一棒：pull 公共 clone，扫出进行中的共享 checkpoint，做协议校验 + 跨机折算，把下一棒上下文建起来。
用法：/checkpoint-shared-load            列出所有项目的进行中共享 checkpoint（当前项目 ⭐ 高亮）
      /checkpoint-shared-load --here     只列当前 project_key
      /checkpoint-shared-load <数字>     加载本次列表第 N 项
      /checkpoint-shared-load <路径>     直接校验并加载该活动 checkpoint
位置建议：<CHECKPOINT_TOOLS>/dsh/command/checkpoint-shared-load.md（DSH 扫 customSkillDirs 的平面 skill 文件）
来源：shared/command/checkpoint/commands/checkpoint-shared-load.md 语义模板的 DSH 原生版；配套 checkpoint-shared.md / task-done-shared.md；完整协议以 shared/command/checkpoint/design.md 为准。
-->

# /checkpoint-shared-load — 加载共享 checkpoint 接棒

DSH执行，对用户称用户。

> **本命令只负责恢复和对齐**：不做实现、不改文件、不 commit、不 push。
> **跟本地 / online 版是两套**：只扫 `~/.silvers/checkpoint-shared/shared/`，不碰 `/checkpoint-load`、`/checkpoint-load-online` 的目录和 clone。

## 0. 本机运行时约束（按当前 OS 取对应分支，强制）

<!-- CHECKPOINT-SHARED RUNTIME：按当前 OS 取对应分支；共同项无条件生效 -->
- **共同**：公共工作区固定为 `$HOME/.silvers/checkpoint-shared`；Markdown、脚本和文件名统一 UTF-8、LF；`client_name` 硬编码为 `dsh`（`last_client` 一律填 `dsh`，运行时禁止写 `unknown`，model 取不到时才允许 `unknown`）。
- **macOS / Linux**：shell 用 Bash/Zsh 语义；取时必须新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`；扫描脚本兼容 BSD `stat`，不假设 GNU `stat -c`。
- **Windows**：取时必须走 Git Bash 的 GNU `date`（`date '+%Y-%m-%dT%H:%M:%S%z'`），**禁用** PowerShell `Get-Date` / `[DateTime]::Now`（cold start + Defender 实时扫描会拖到超时甚至挂死）；路径用 `$HOME/` 由 Git Bash 展开。
<!-- END CHECKPOINT-SHARED RUNTIME -->

**强制**：本段缺失就停下来，提示重新按 `shared/command/checkpoint/install/` 下当前 OS 对应的手册（`macos.md` / `windows.md`） 安装。

## 固定资源与边界

- 远端：`<CHECKPOINT_REPO_URL>`
- 公共工作区：`~/.silvers/checkpoint-shared/`
- **只扫描**：`~/.silvers/checkpoint-shared/shared/<project_key>/*.md`
- **排除**：`~/.silvers/checkpoint-shared/shared/done/**`
- **仅限 `shared/`**：禁止扫描或修改远端其它顶层目录（`cc/`、`codex/`、`zcode/` 等）。
- **参数**：`/checkpoint-shared-load` 之后的文字就是用户消息原文，按下表解析；项目根取 **cwd**。

| 用户消息里的参数 | 行为 |
|---|---|
| 空 | 列出所有项目的活动 shared checkpoint（当前项目 ⭐ 高亮） |
| `--here` | 只列当前 `project_key` |
| 数字 N | 加载本次列表第 N 项 |
| 公共工作区内的显式路径 | 直接校验并加载该活动 checkpoint |

- 禁止修改 `~/.ssh/config`、`~/.gitconfig`；禁止擅自更换用户配置的远端地址或 URL scheme。认证 / 网络不通就停下来报告用户，不要自行绕过。

## 执行步骤

### 1. 确保公共工作区可读取

1. 工作区不存在 → clone 固定远端：

   ```bash
   git clone <CHECKPOINT_REPO_URL> "$HOME/.silvers/checkpoint-shared"
   ```

2. 已存在 → 用 `git -C "$HOME/.silvers/checkpoint-shared" remote -v` 核实 origin 指向固定仓库；不是就停下来报告，禁止改 remote。
3. 检查工作区（`bash` 跑 `git -C "$HOME/.silvers/checkpoint-shared" status --short --branch`）：
   - 有未知 dirty 文件：**停止**，**不自动** stash / reset。
   - 有未推送的本地提交：**立即停止**，避免从旧本地状态继续加载。`/checkpoint-shared-load` **不得执行 push**；优先提示用户回到产生该提交的会话，重新调用 `/checkpoint-shared` 或 `/task-done-shared` 完成同步。原会话不可用时，明确提示由用户手工执行 `git -C "$HOME/.silvers/checkpoint-shared" push`，成功后重新运行本命令——**load 只能展示这条恢复命令，不能代用户执行**。
4. 干净且没有未推送提交后，fast-forward-only 同步：

   ```bash
   git -C "$HOME/.silvers/checkpoint-shared" pull --ff-only
   ```

**只有 clone、pull 和读取是被允许的写远端之外的操作**；pull 失败或分叉就停止，**禁止** merge、rebase 或 force push。

### 2. 计算当前项目身份

Git 项目必须按 `/checkpoint-shared` 同一算法把 SSH SCP、`ssh://`、HTTPS 的 `origin` 规范化为 `host/owner/repo`，再取最后一段作为 `project_key`；GitHub host/path 转小写并去 `.git`——三种 GitHub URL 都应得到 `github.com/owner/repo`。非 Git 项目取 cwd basename，remote 记 `none`。

当前项目**只用于** `--here` 高亮和同名 remote 校验，**不限制**默认的全局列表。

### 3. 解析参数并扫描

**强制调用安装好的扫描脚本**，不要临时拼接 `for/find/head/stat` 复合命令（多文件读取 + 跨平台 stat 自己拼极易漏文件、算错时间）：

```bash
bash ~/.dsh/scripts/list-shared-checkpoints.sh
bash ~/.dsh/scripts/list-shared-checkpoints.sh --here <project_key>
```

脚本输出（每行一个 checkpoint，`|` 分隔，直接 split）：

```text
FILE|...|PROJ|...|CHECKPOINT_ID|...|REVISION|...|CREATED|...|UPDATED|...|COMMIT_TIME|...|LAST_CLIENT|...|LAST_MODEL|...|LAST_MACHINE|...|LAST_OS|...|LAST_SHELL|...|PATH_STYLE|...|TITLE|...
```

- 脚本已过滤 `status: in-progress`、已排除 `shared/done/`、已兼容 BSD / GNU 两种 `stat`；一个都没有时安静退出，不算报错。
- **有效时间用 Git commit time（`COMMIT_TIME`），不是 pull 之后被刷新的文件系统 mtime**。
- **双时间校验（强制）**：比较 `UPDATED` 与 `COMMIT_TIME`，偏差**超过 5 分钟**时用**较晚者**排序，并显示 frontmatter 时间漂移警告。
- 默认**最多展示 12 个**，按有效更新时间**倒序**：

```text
找到 N 个共享接力点：
  1. ⭐ [project] r4 [更新 12 分钟前]
     标题：<title>
     上一棒：<last_client>/<last_model> @ <last_machine>(<last_os>)
     文件：<checkpoint_id>.md

输入数字加载，或直接回车跳过：
```

- 一个都没有 → 告诉用户「公共接力区没有进行中的共享 checkpoint」，安静收尾。
- 列完**等用户回数字或路径**，不要自选一份闷头加载。

### 4. 选择后做协议校验

- 路径必须位于公共工作区 `shared/` 且**不在** `shared/done/`。
- `status` 必须为 `in-progress`，`revision` 必须是正整数。
- `schema_version: 1` 才能进入**可更新状态**；未知版本**只允许只读展示并告警**，不能记为当前维护文件。
- frontmatter 必填字段和正文「接棒入口」必须存在。
- 文件的 `project_key` 必须与**所在目录**一致。
- checkpoint 的 `project_key` 与当前项目 `project_key` **不一致**时，必须在跨机路径折算前**强制暂停**：显示当前项目和 checkpoint 各自的 key，让用户选「中止 / 切到目标项目根后重试 / 显式进入只读 review」；**默认不得继续接力**。
- **显式进入只读 review** 时：不做路径折算，不把该文件记为当前维护 checkpoint，也不记住 expected revision；**不得把当前 cwd 当作目标项目根**，后续不能据此调用 `/checkpoint-shared` 或 `/task-done-shared`。
- key 相同时比较两侧规范化 `project_remote`：两侧都不是 `none` 且值相等时才可自动继续；两侧都不是 `none` 且值不相等时视为**项目碰撞并停止**；任一侧为 `none` 时身份无法自动核实，选择、加载或更新前**必须取得用户显式确认**。
- 文件超过 7k token 时可以只读，但**必须警告**它违反保存协议，接棒后第一次保存应压缩到上限内。

### 5. 跨机器 / 跨客户端折算

读 `last_client`、`last_model`、`last_machine`、`last_os`、`last_shell`、`path_style`、`last_project_root`，与当前环境比较：

- 当前项目根**以当前机器真实 cwd / git root 为准**，忽略上一棒的绝对根路径。
- 正文里的项目相对路径直接拼当前项目根。
- `windows ↔ posix` 转换盘符和路径分隔符。
- 按当前 shell 把 PowerShell / Bash 命令转换成等价形式。
- 运行时、虚拟环境、JDK、Node、Python 等绝对路径**必须在当前机实际探测**；不能把上一台机器的路径直接替换用户名后使用。
- 无法确定的转换标成「待用户确认」，**禁止臆造**。
- **不在 load 阶段修改 checkpoint 文件**。

### 6. 记住接力状态

在本次对话里明确记住：

- 当前 shared checkpoint 的**完整路径**
- **expected revision N**
- `project_key` 与 `project_remote`
- 上一棒 client / model / machine

后续 `/checkpoint-shared` 和 `/task-done-shared` **只能以这个 expected revision 为覆盖依据**。

### 7. 详细复述并等待

```text
✅ 已加载共享 checkpoint：shared/<project_key>/<文件名>
revision：N
上一棒：<last_client>/<last_model> @ <last_machine>(<last_os>)
当前棒：dsh/<current_model> @ <current_machine>(<current_os>)
环境：<同机无需折算 / 已折算 / 有待确认项>

任务与范围：<摘要>
当前完成边界：<摘要>

第一条有效操作：
  目的：...
  工作目录：...
  必读文件：...
  完整命令：...
  预期结果：...
  完成标准：...
  失败分支：...

后续步骤：<2–6 步摘要>
不要重复：<已完成/已排除项>
风险与阻塞：...
仍需确认：...
```

复述后**等用户确认再开始工作**。`/checkpoint-shared-load` 只负责恢复和对齐，**不得擅自执行实现、修改文件、提交或 push**。

## 沙箱提示（DSH 特有）

`~/.silvers/checkpoint-shared/` 与 `~/.dsh/scripts/` 都在**工作区之外**：`workspace-write` 档下脚本可能读不到、`git pull` 也会被拒。遇到拒绝就按沙箱升权流程申请一次更宽档位（`read-only` → `workspace-write` → `danger-full-access`），或让用户用 `/permission` 切到含 full-access 的预设。详见同目录 `README.md` 的权限章节。

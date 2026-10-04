# `/checkpoint-shared` 语义模板

> 本文件供任意大模型理解后转换为自己的 command、prompt 或 skill。安装时可以改命令头、参数变量和脚本安装路径，但不得改变下面的存储、schema、revision、安全和 Git 规则。

把当前任务状态整理成一份详细的共享 checkpoint，写入公共接力区并同步远端，供另一个模型、客户端或机器继续。

## 固定资源与授权边界

- 远端：`<CHECKPOINT_REPO_URL>`
- 公共工作区：`~/.silvers/checkpoint-shared/`
- 活动目录：`~/.silvers/checkpoint-shared/shared/<project_key>/`
- 归档目录：`~/.silvers/checkpoint-shared/shared/done/<project_key>/`
- 只允许操作 `shared/`；禁止改动远端仓库的其他目录。

用户主动调用 `/checkpoint-shared`，即授权本次命令在上述公共工作区内执行限定的 clone、pull、add、commit 和 push；不授权修改当前项目的 Git 历史，也不授权普通项目 push。

## 执行步骤

### 0. 载入本机运行时约束

安装后的命令必须内嵌当前平台约束：

- macOS 使用 Bash/Zsh、BSD `stat` 兼容路径。
- Windows 运行时必须是 Git Bash；禁止 PowerShell `Get-Date` / `[DateTime]::Now`。
- 文件统一 UTF-8、LF；中文 slug 不能用 `head -c` 按字节截断。
- `<client_name>` 必须由安装者在安装时硬编码到本机命令，运行时不得写 `unknown`。

如果安装结果中没有平台块，停止并提示重新按模板安装。

### 1. 确保公共工作区可安全同步

1. `~/.silvers/checkpoint-shared/.git` 不存在：clone 固定远端到该目录。
2. 已存在：确认 remote 指向固定仓库。
3. 检查工作区：
   - 有未知 tracked/untracked 修改：停止，列出文件；禁止自动 stash、reset 或覆盖。
   - 有未推送的本地提交：先尝试补 push。补推失败则停止，本轮不能创建新 revision。
4. 工作区干净且无未推送提交后，执行 fast-forward-only pull。

同步策略固定为 `git pull --ff-only`。实际命令可使用：

```bash
git -C "$HOME/.silvers/checkpoint-shared" pull --ff-only
```

pull 失败或出现分叉时停止，禁止 merge、rebase 或 force push。

### 2. 计算项目身份

- Git 项目：读取 `origin`，把 SSH SCP、`ssh://`、HTTPS 三种 URL 统一规范化为 `host/owner/repo`：移除 scheme、SSH user、查询参数、fragment、首尾斜杠和 `.git`，host 转小写；GitHub owner/repo 也转小写。`project_key` 取规范化结果最后一段。
- 非 Git 项目：`project_key` 取当前目录 basename，`project_remote: none`。
- 如果 `shared/<project_key>/` 已有 checkpoint，比较当前项目与 checkpoint 中的规范化 `project_remote`：两侧都不是 `none` 且值相等时才可自动继续；两侧都不是 `none` 且值不相等时，视为项目碰撞并停止。任一侧为 `none` 时，身份无法自动核实，选择、加载或更新前必须取得用户显式确认。

规范化示例：`git@github.com:Owner/Repo.git`、`ssh://git@github.com/Owner/Repo.git`、`https://github.com/Owner/Repo.git` 都得到 `github.com/owner/repo`。

### 3. 决定创建还是更新

优先级：

1. 用户显式传入 shared checkpoint 路径：只接受公共工作区 `shared/<project_key>/` 下、状态为 `in-progress` 的文件。
2. 本次对话记得 `/checkpoint-shared-load` 加载的完整路径和 expected revision：更新该文件。
3. 都没有：创建新文件 `YYYYMMDD-HHMMSS-<8–15 个中文字 slug>.md`，初始 revision 为 1。

没有 expected revision 时禁止覆盖已有文件。如果当前项目存在看起来属于同一任务的活动 checkpoint，先列出并让用户选择 load/update 还是创建新任务，不能靠标题猜测后覆盖。

更新已有文件时：pull 后再次读取远端 revision。它必须等于本次对话记住的 expected revision N；否则停止并要求重新 `/checkpoint-shared-load`。校验通过后写 revision N+1。

### 4. 采集真实时间、客户端和环境

写入前必须新执行一次：

```bash
date '+%Y-%m-%dT%H:%M:%S%z'
```

禁止复用对话、旧 frontmatter 或另一台机器留下的时间戳。

采集：

- `last_client`：使用安装时硬编码的 `<client_name>`，运行时不得写 `unknown`。
- `last_model`：当前模型；无法可靠得知写 `unknown`，禁止猜测。
- `last_machine`：`hostname`。
- `last_os`：`Darwin → darwin`、Linux → `linux`、`MINGW*/MSYS*/CYGWIN* → win32`。
- `last_shell`：当前实际 shell。
- `path_style`：`posix` 或 `windows`。
- `last_project_root`：当前项目真实绝对路径，仅作环境记录。

首次创建时 `created_at` 等于本次时间；更新时保持原 `created_at` 不变。`updated_at` 每次刷新。

### 5. 生成 frontmatter

必须包含以下扁平字段：

```yaml
---
schema_version: 1
checkpoint_id: <与稳定文件名主体一致>
project_key: <项目标识>
project_remote: <规范化远端或 none>
title: "<一句话任务标题>"
status: in-progress
revision: <1 或 N+1>
created_at: <首次创建时间，后续不变>
updated_at: <本次真实时间>
last_client: <安装时硬编码的 client_name>
last_model: <当前模型或 unknown>
last_machine: <hostname>
last_os: <darwin | linux | win32>
last_shell: <当前 shell>
path_style: <posix | windows>
last_project_root: <当前项目绝对路径>
---
```

### 6. 生成正文

正文建议 4–6k token，**硬上限 7k token**。简单任务可以更短；超限时的压缩优先级是 **过程叙述 > 可选附录 > 九个必备章节**，不能压缩接棒入口、风险和验证证据。

```markdown
# <任务标题>

## 1. 接棒入口

### 一句话状态
<完成到什么边界，当前卡点是什么>

### 接棒后的第一步
- **目的**：<这一步解决什么>
- **工作目录**：<当前机器应进入哪里；项目内路径优先相对路径>
- **前置条件**：<分支、依赖、服务、凭据来源、测试数据>
- **必读文件**：<相对路径 + 关键行/章节 + 阅读目的>
- **修改入口**：<预计从哪些文件/模块开始>
- **执行命令**：<可复制的完整命令，敏感值用占位符>
- **预期结果**：<正常输出或行为>
- **完成标准**：<看到什么才算完成>
- **失败分支**：<常见失败的判定方式 + 下一条诊断命令>

### 后续步骤
1. <动作；实施位置；验证方法；完成条件>
2. <动作；实施位置；验证方法；完成条件>

### 不要重复的工作
- <已完成或已排除路径 + 证据>

### 接棒前仍需用户确认
- <真正需要拍板的事项；没有写“无”>

## 2. 任务目标与范围
<最终交付、包含项、不做项>

## 3. 当前进度与工作区状态
<已完成/进行中/未开始；分支、未提交文件、远端状态>

## 4. 已完成工作及验证证据
<改了什么、在哪里、运行过什么、结果是什么>

## 5. 关键决策
<决策、理由、来源、放弃的备选>

## 6. 认知陷阱与已排除路径
<误区、真相、证据；本轮真没踩过就写“无（任务直线推进）”。
 **不要为了凑段编**——编出来的假陷阱会让接棒方绕开一条根本不存在的坑，比留白更糟。>

## 7. 剩余任务
### P0
### P1
### P2
### long-term
<每项写依赖、实施位置和完成条件>

## 8. 环境与跨机折算
<存档机环境；机器相关绝对路径/命令；凭据重新取得位置>

## 9. 引用
<只列相对文件、设计文档、提交和报告位置，不复制正文>

<!-- 以下附录均为可选，不计入正文九个必备章节。
     没有实质内容时不生成标题，也不写“无”。 -->

## 可选附录：关键发现
<跟本轮改动无关、但下一棒不知道就会踩的代码库既存事实。
 与第 4 节的分界：第 4 节写“本轮改了什么、跑了什么、结果如何”（改动证据），
 本节写“某文件 line N 有隐式默认分支 / 上游 schema 字段类型严格”（既存事实）。
 同一件事不要两节各写一遍。>

## 可选附录：AI verify 边际效用提醒
<仅在已完成多轮 AI 审查、继续审的边际收益明显降低时才写。
 写清：已做几轮 / 报告位置 / 不要再审的理由 / 建议改走什么路径（如真实流量、联调驱动）。>
```

跨机可移植性：项目内路径用相对路径；机器相关绝对路径和命令只放第 8 节。另一端不确定如何折算时，应标记“待用户确认”。

### 7. 写入前强制校验

- 路径位于 `shared/<project_key>/`，不在 `shared/done/`。
- frontmatter 必填字段齐全，`schema_version: 1`，`status: in-progress`。
- `checkpoint_id` 与稳定文件名一致。
- 新建 revision 为 1；更新 revision 恰好为 expected revision + 1。
- `created_at` 更新时未改变，`updated_at` 来自本次真实取时。
- 正文**九个必备章节**齐全，尤其“接棒后的第一步”包含可执行命令、预期结果、完成标准和失败分支。
- 两个**可选附录**（关键发现 / AI verify 边际效用提醒）**缺失不构成校验失败**；一旦出现，仍受 7k token 上限、脱敏和“禁止复制大段源码 / 完整 diff”等校验约束。
- 估算正文没有超过 7k token。
- 没有 token、密码、Cookie、私钥、完整 `.env` 或账号凭据。敏感参数统一替换成 `<REDACTED>`，并说明从哪里重新取得。
- 没有完整聊天记录、完整 diff 或大段源码。

任一校验失败都拒绝保存，并列出缺项。

### 8. 原子写入、提交和推送

先把完整内容写到目标同目录的临时文件，校验通过后再**原子替换**目标文件；失败时保留原 checkpoint。不要先破坏旧文件再生成新内容。

只 stage 目标 checkpoint，不使用无边界的 `git add -A`：

```bash
git -C "$HOME/.silvers/checkpoint-shared" add -- "shared/<project_key>/<文件名>"
git -C "$HOME/.silvers/checkpoint-shared" commit -m "checkpoint(shared/<project_key>): r<revision> <title> @<client>/<model>"
git -C "$HOME/.silvers/checkpoint-shared" push
```

push 被拒绝时只允许再次 fetch/pull --ff-only 后重试；如果不能 fast-forward，停止。网络中断时保留本地提交，明确汇报“**尚未交棒成功**”，下次 shared 命令必须先补推，不能创建另一 revision。

### 9. 记住并汇报

push 成功后在本次对话中记住完整路径和 revision，供后续更新或 `/task-done-shared` 使用：

```text
✅ 共享 checkpoint 已保存并同步
路径：shared/<project_key>/<文件名>
revision：<N>
写入者：<client>/<model> @ <machine>
接棒状态：远端已就绪
```

## 参数

安装者应把客户端的原生参数映射为：可选 shared checkpoint 路径。显式路径只用于更新已加载任务，仍必须满足 expected revision 校验。

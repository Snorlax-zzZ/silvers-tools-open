# Checkpoint Shared 设计与协议

> 本文件是 Checkpoint Shared 协议的唯一事实来源（SSOT）。命令模板、安装说明和历史计划与本文件冲突时，以本文件为准。

## 1. 目标与边界

Checkpoint Shared 用于单写者顺序接力：模型 A 保存，模型 B 加载后继续，最后一棒归档。它支持换客户端、换模型和换机器，但不支持多个模型并发修改同一任务。

旧体系保持不变：每个客户端原有的本地 checkpoint、`checkpoint-online` 命令、本地 clone 和远端命名空间均不迁移、不改名、不复用。新三件套只复用同一个 Git 远端。

## 2. 存储

本机固定工作区：

```text
~/.silvers/checkpoint-shared/
```

远端固定布局：

```text
shared/<project_key>/<checkpoint_id>.md
shared/done/<project_key>/<checkpoint_id>.md
```

一个任务始终维护一个稳定文件。接棒模型更新同一文件；历史版本由 Git 提供。任何命令都不得读取或修改远端其他顶层目录。

## 3. Schema v1

Frontmatter 必须保持扁平，便于 Bash 和不同模型解析：

```yaml
---
schema_version: 1
checkpoint_id: 20260710-153000-统一接力工具
project_key: my-project
project_remote: github.com/example/my-project
title: "设计多模型共享接力工具"
status: in-progress
revision: 3
created_at: 2026-07-10T15:30:00+0800
updated_at: 2026-07-10T17:20:00+0800
last_client: codex
last_model: <MODEL>
last_machine: example-mac
last_os: darwin
last_shell: zsh
path_style: posix
last_project_root: /Users/example/Documents/my-project
---
```

必填字段：

- 身份：`schema_version`、`checkpoint_id`、`project_key`、`project_remote`
- 生命周期：`status`、`revision`、`created_at`、`updated_at`
- 展示：`title`
- 最后一棒：`last_client`、`last_model`、`last_machine`、`last_os`、`last_shell`、`path_style`、`last_project_root`

完成归档时追加：`done_at`、`done_client`、`done_model`、`done_machine`。

`last_client` 和 `done_client` 必须使用安装时硬编码的 `<client_name>`，运行时不得写 `unknown`。`last_model` 和 `done_model` 无法可靠识别时写 `unknown`，禁止猜测。`path_style` 只能是 `posix` 或 `windows`；`last_os` 使用 `darwin`、`linux` 或 `win32`。

`project_key` 优先取当前项目 origin 的仓库名并去掉 `.git`。`project_remote` 必须规范化成 `host/owner/repo`，不能直接保存各客户端拿到的原始 URL：

- `git@github.com:owner/repo.git`
- `ssh://git@github.com/owner/repo.git`
- `https://github.com/owner/repo.git`

以上都必须得到 `github.com/owner/repo`。规范化时移除 scheme、SSH user、查询参数、fragment、开头斜杠、结尾斜杠和 `.git`；host 转小写，GitHub 的 owner/repo 也转小写。其他 host 保留路径大小写。`project_key` 取规范化结果最后一段。

非 Git 项目或只存在不可跨机识别的本地/file remote 时，使用目录 basename 作为 key，并将 remote 写成 `none`。同名 key 已有 checkpoint 时，比较当前项目与 checkpoint 中的规范化 `project_remote`：两侧都不是 `none` 且值相等时才可自动继续；两侧都不是 `none` 且值不相等时，视为项目碰撞并停止。任一侧为 `none` 时，身份无法自动核实，选择、加载或更新前必须取得用户显式确认。

未知 `schema_version` 只能只读展示，禁止覆盖。

## 4. Revision 协议

- 新任务从 revision 1 开始。
- load 时在对话中记住完整文件路径与 revision N。
- update/done 前必须 pull，并确认远端文件仍为 revision N。
- 校验通过后只能写 revision N+1。
- revision 不一致时中止，重新 load；没有 expected revision 时不得覆盖已有文件。

该机制不是并发合并工具，而是防止旧会话、旧机器或恢复后的过期上下文误覆盖新一棒。

## 5. 正文协议

建议 4–6k token，硬上限 7k token。简单任务可以更短；超过上限时的压缩优先级是 **过程叙述 > 可选附录 > 九个必备章节**，不能压缩接棒入口、风险和验证证据。

### 5.1 接棒入口（强制、必须放第一节）

- 一句话状态：当前完成到什么边界。
- 接棒后的第一步：
  - 目的
  - 工作目录
  - 前置条件（分支、依赖、服务、凭据来源、测试数据）
  - 必读文件（相对路径、关键行/章节、阅读目的）
  - 修改入口
  - 可复制的完整命令
  - 预期结果
  - 完成标准
  - 失败分支及下一条诊断命令
- 后续 2–6 步：每步写动作、实施位置、验证方式和完成条件。
- 不要重复的工作：已完成或已否定路径及证据。
- 接棒前仍需用户确认：没有则写“无”。

### 5.2 其余强制章节

1. 任务目标与范围
2. 当前进度与工作区状态
3. 已完成工作及验证证据
4. 关键决策
5. 认知陷阱与已排除路径（本轮真没踩过就写“无（任务直线推进）”，不要为了凑段编——编出来的假陷阱会让接棒方绕开一条根本不存在的坑）
6. 剩余任务（P0、P1、P2、long-term）
7. 环境与跨机折算
8. 引用

目标是让一个全新模型只读 checkpoint 与其中列出的必读文件，就能在五分钟内开始第一条有效操作。

### 5.3 可选附录（不计入必备章节）

以下两个附录**可写可不写，缺失不构成校验失败**；没有实质内容时**不生成标题，也不写“无”**。一旦出现，仍受 7k token 上限、安全脱敏和“禁止复制大段源码 / 完整 diff”约束。

- **关键发现**：跟本轮改动无关、但下一棒不知道就会踩的代码库既存事实。与 5.2 第 3 项的分界——“已完成工作及验证证据”写本轮改了什么、跑了什么、结果如何（改动证据）；本附录写某文件 line N 有隐式默认分支、上游 schema 字段类型严格之类的既存事实。同一件事不要两处各写一遍。
- **AI verify 边际效用提醒**：仅在已完成多轮 AI 审查、继续审的边际收益明显降低时写。写清已做几轮、报告位置、不要再审的理由、建议改走什么路径。

## 6. 跨机协议

- 项目内文件始终使用相对 `last_project_root` 的路径。
- 机器相关绝对路径和命令集中在“环境与跨机折算”，不能散落在其他章节。
- load 时以当前项目根为准，不照搬 `last_project_root`。
- 根据 `last_os + last_shell + path_style` 折算盘符、分隔符和 PowerShell/Bash 命令。
- 不确定的路径或命令必须标为“待用户确认”，禁止编造。

## 7. Git 与失败语义

每次操作先检查工作区，再执行 fast-forward-only 同步。未知 dirty 修改、非 fast-forward、revision 冲突都必须停止；禁止自动 stash、reset、rebase 或 merge。

保存和归档仅 stage 目标 checkpoint，不使用无边界的 `git add -A`。只有 push 成功才算交棒或归档成立。网络失败时保留本地提交并明确报告“尚未交棒成功”；下一次 save/done 命令先处理该未推送提交。load 只允许 clone、pull 和读取，不得 commit 或 push；发现未推送提交时必须停止并提示使用原 save/done 命令完成同步。

用户主动调用 `/checkpoint-shared` 或 `/task-done-shared`，即授权本次对公共工作区的限定 commit/push，不授权对当前项目或远端其他目录做 Git 写操作。

## 8. 安全

- 禁止写 token、密码、Cookie、私钥、完整 `.env` 和账号凭据。
- 命令中的敏感参数改成 `<REDACTED>`，同时写明从哪里重新取得。
- 禁止嵌入完整聊天记录、完整 diff 或大段源码。
- 引用已有 artifact 时只写路径、提交或文档位置。

## 9. 平台

- macOS：Bash/Zsh；兼容 BSD `stat`。
- Windows：Git for Windows / Git Bash 是运行时硬前提；PowerShell 只负责安装。
- 两端均通过 `date '+%Y-%m-%dT%H:%M:%S%z'` 取得当前真实时间。
- Windows 禁止运行时使用 `Get-Date` 或 `[DateTime]::Now`。
- 文件统一 UTF-8、LF；不得使用按字节截断中文的命令。

详细安装要求见 `install/`。

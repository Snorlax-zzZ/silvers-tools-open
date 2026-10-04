---
name: checkpoint-shared-load
description: Use when the user explicitly asks to "checkpoint shared load"/"加载共享 checkpoint"/"接棒"/"列出共享接力". shared 三件套之接棒：拉取公共接力区，协议校验后折算到当前模型/客户端/机器，建立下一棒上下文。存棒走 checkpoint-shared，收棒走 task-done-shared。本地版走 checkpoint-load，云端版走 checkpoint-load-online。不要主动触发，只有用户明确要求时才执行。
---

# Checkpoint-Shared-Load（公共接力 · 接棒）

拉取公共任务池，选择一份进行中的共享 checkpoint，校验后折算到当前机器，建立下一棒上下文。存棒走 checkpoint-shared，收棒走 task-done-shared。

## 固定资源

- 远端：`<CHECKPOINT_REPO_URL>`
- 公共工作区：`~/.silvers/checkpoint-shared/`（全客户端共用）
- 只扫描 `shared/<project_key>/*.md`，排除 `shared/done/**`；禁止扫改远端其他顶层目录

## 运行时约束

<!-- CHECKPOINT-SHARED RUNTIME -->
- `client_name` 固定硬编码 `zcode`，运行时不得写 `unknown`。
- macOS / Linux：Bash/Zsh 语义；时间必须新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`。Windows（`MINGW*`/`MSYS*`/`CYGWIN*`）：必须 Git Bash，禁 PowerShell `Get-Date` / `[DateTime]::Now`。
- 扫描脚本兼容 BSD / GNU `stat`；文件 UTF-8、LF。
- 公共工作区固定 `$HOME/.silvers/checkpoint-shared`；同步固定 `git pull --ff-only`，禁 merge / rebase / force push。
<!-- END CHECKPOINT-SHARED RUNTIME -->

> 协议 SSOT：本工具仓库的 `shared/command/checkpoint/design.md`，冲突以其为准。

## 接棒步骤（checkpoint-shared-load）

### 1. 工作区就绪（load 不得 push）

1. 工作区不存在 → clone 固定远端；已存在 → 确认 remote 正确
2. 有未知 dirty 文件 → 停止，不自动 stash/reset
3. 有未推送的本地提交 → **立即停止**：load 不得 push。提示用户回到产生该提交的会话重新调存棒/收棒完成同步，或由用户手工执行 `git -C ~/.silvers/checkpoint-shared push`（load 只展示这条恢复命令，不代执行）
4. 干净后 `git -C ~/.silvers/checkpoint-shared pull --ff-only`；失败/分叉停止

### 2. 计算当前项目身份

Git 项目按存棒同一算法规范化 origin（SSH SCP / `ssh://` / HTTPS → `host/owner/repo`，host 和 GitHub owner/repo 转小写、去 `.git`），`project_key` 取最后一段；非 Git 取 cwd basename（remote 为 `none`）。当前项目身份只用于 `--here` 高亮和同名 remote 校验，不限制默认全局列表。

### 3. 解析参数并扫描

| 输入 | 行为 |
|---|---|
| 空 | 列出所有项目的活动 shared checkpoint |
| `--here` | 只列当前 `project_key` |
| 数字 N | 加载本次列表第 N 项 |
| 公共工作区内的显式路径 | 直接校验并加载该活动 checkpoint |

**必须**跑已安装的扫描脚本，不要临时拼 `for/find/head/stat` 复合命令：

```bash
bash ~/.zcode/scripts/list-shared-checkpoints.sh
bash ~/.zcode/scripts/list-shared-checkpoints.sh --here <project_key>
```

输出行格式：`FILE|...|PROJ|...|CHECKPOINT_ID|...|REVISION|...|CREATED|...|UPDATED|...|COMMIT_TIME|...|LAST_CLIENT|...|LAST_MODEL|...|LAST_MACHINE|...|LAST_OS|...|LAST_SHELL|...|PATH_STYLE|...|TITLE|...`

- 有效时间用 **git commit time**（COMMIT_TIME），不是 pull 后被刷新的文件系统 mtime
- `UPDATED` 与 `COMMIT_TIME` 偏差超过 5 分钟 → 用较晚者排序并显示时间漂移 ⚠️
- 最多展示 12 个，按有效更新时间倒序：

```text
找到 N 个共享接力点：
  1. ⭐ [project] r4 [更新 12 分钟前]
     标题：<title>
     上一棒：<last_client>/<last_model> @ <last_machine>(<last_os>)
     文件：<checkpoint_id>.md

输入数字加载，或直接回车跳过：
```

### 4. 选中后协议校验

- 路径必须在 `shared/` 且不在 `shared/done/`；`status` 必须 `in-progress`；revision 必须正整数
- `schema_version: 1` 才能进入可更新状态；未知版本只允许只读展示 + 告警，不能记为当前维护文件
- frontmatter 必填字段和正文"接棒入口"必须存在；文件 `project_key` 必须与所在目录一致
- checkpoint 的 `project_key` 与当前项目不一致 → 跨机路径折算前**强制暂停**，显示两侧 key，让用户选中止 / 切换到目标项目根重试 / 显式进入只读 review（只读 review 不折算、不记为当前维护 checkpoint、不记 expected revision，后续不能据此存棒/收棒，也不得把当前 cwd 当目标项目根）
- key 相同时比较两侧规范化 `project_remote`：两侧都非 `none` 且相等 → 自动继续；不等 → 项目碰撞停止；任一侧 `none` → 用户显式确认
- 文件超 7k token 可只读，但必须警告违反保存协议，接棒后第一次保存应压缩到上限内

### 5. 跨机器和跨客户端折算

读取 `last_client`、`last_model`、`last_machine`、`last_os`、`last_shell`、`path_style`、`last_project_root`，与当前环境比较：

- 当前项目根以当前机器真实 cwd / git root 为准，**忽略上一棒绝对根路径**
- 正文项目相对路径直接拼当前项目根；`windows ↔ posix` 转换盘符和路径分隔符；按当前 shell 转换等价命令
- 运行时、虚拟环境、JDK、Node、Python 等绝对路径必须在当前机实际探测，不能把上一台机器的路径替换用户名后直接用
- 无法确定的转换标"待用户确认"，禁止臆造
- load 阶段**不修改** checkpoint 文件

### 6. 记住接力状态（本次对话内）

完整路径 + expected revision N + `project_key` / `project_remote` + 上一棒 client / model / machine。后续存棒 / 收棒只能以这个 expected revision 为覆盖依据。

### 7. 详细复述并等待确认

```text
✅ 已加载共享 checkpoint：shared/<project_key>/<文件名>
revision：N
上一棒：<last_client>/<last_model> @ <last_machine>(<last_os>)
当前棒：zcode/<model> @ <machine>(<os>)
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

复述后**等待用户确认**再开始工作。load 只负责恢复和对齐，不得擅自执行实现、修改文件、提交或 push。

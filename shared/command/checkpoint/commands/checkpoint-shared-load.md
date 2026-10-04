# `/checkpoint-shared-load` 语义模板

> 本文件供任意大模型转换为自己的 command、prompt 或 skill。允许调整命令头、参数变量和扫描脚本安装路径，不得改变公共存储、schema、revision、跨机和安全规则。

拉取公共任务池，选择一份进行中的共享 checkpoint，校验后折算到当前模型和机器，并建立下一棒上下文。

## 固定资源与边界

- 远端：`<CHECKPOINT_REPO_URL>`
- 公共工作区：`~/.silvers/checkpoint-shared/`
- 只扫描：`~/.silvers/checkpoint-shared/shared/<project_key>/*.md`
- 排除：`~/.silvers/checkpoint-shared/shared/done/**`
- 禁止扫描或修改远端其他顶层目录。

## 执行步骤

### 0. 载入平台块

确认安装后的命令已经注入 macOS 或 Windows Git Bash 运行时约束。Windows 禁止用 PowerShell 取时或执行扫描脚本。`<client_name>` 必须由安装者在安装时硬编码到本机命令，运行时不得写 `unknown`。

### 1. 确保公共工作区可读取

工作区不存在时 clone 固定远端。存在时核实 remote：

- 有未知 dirty 文件：停止，不自动 stash/reset。
- 有未推送的本地提交：立即停止，避免从旧本地状态继续加载。`/checkpoint-shared-load` 不得执行 push；优先提示用户回到产生该提交的会话，重新调用 `/checkpoint-shared` 或 `/task-done-shared` 完成同步。原会话不可用时，明确提示由用户手工执行 `git -C "$HOME/.silvers/checkpoint-shared" push`，成功后重新运行 `/checkpoint-shared-load`；load 只能展示这条恢复命令，不能代用户执行。
- 工作区干净且没有未推送提交后，使用 `git pull --ff-only` 策略同步：

```bash
git -C "$HOME/.silvers/checkpoint-shared" pull --ff-only
```

pull 失败或分叉时停止，禁止 merge、rebase 或 force push。

### 2. 计算当前项目身份

Git 项目必须按 save 命令同一算法把 SSH SCP、`ssh://`、HTTPS origin 规范化为 `host/owner/repo`，再取最后一段作为 `project_key`；GitHub host/path 转小写并去 `.git`。例如三种 GitHub URL 都应得到 `github.com/owner/repo`。非 Git 项目取 cwd basename，remote 为 `none`。当前项目只用于 `--here` 高亮和同名 remote 校验，不限制默认全局列表。

### 3. 解析参数并扫描

| 输入 | 行为 |
|---|---|
| 空 | 列出所有项目的活动 shared checkpoint |
| `--here` | 只列当前 `project_key` |
| 数字 N | 加载本次列表第 N 项 |
| 公共工作区内的显式路径 | 直接校验并加载该活动 checkpoint |

强制调用安装后的 `list-shared-checkpoints.sh`，不要临时拼接 `for/find/head/stat` 复合命令。安装模型必须把下面的占位路径替换为自己的真实脚本位置：

```bash
bash <installed-script-path>/list-shared-checkpoints.sh
bash <installed-script-path>/list-shared-checkpoints.sh --here <project_key>
```

扫描脚本输出：

```text
FILE|...|PROJ|...|CHECKPOINT_ID|...|REVISION|...|CREATED|...|UPDATED|...|COMMIT_TIME|...|LAST_CLIENT|...|LAST_MODEL|...|LAST_MACHINE|...|LAST_OS|...|LAST_SHELL|...|PATH_STYLE|...|TITLE|...
```

online 有效时间使用 Git commit time，而不是 pull 后被刷新的文件系统 mtime。比较 `updated_at` 与 `COMMIT_TIME`：偏差超过 5 分钟时用较晚者排序，并显示 frontmatter 时间漂移警告。

默认最多展示 12 个，按有效更新时间倒序：

```text
找到 N 个共享接力点：
  1. ⭐ [project] r4 [更新 12 分钟前]
     标题：<title>
     上一棒：<last_client>/<last_model> @ <last_machine>(<last_os>)
     文件：<checkpoint_id>.md

输入数字加载，或直接回车跳过：
```

### 4. 选择后做协议校验

- 路径必须位于公共工作区 `shared/` 且不在 `shared/done/`。
- `status` 必须为 `in-progress`，revision 必须是正整数。
- `schema_version: 1` 才能进入可更新状态。未知版本只允许只读展示并告警，不能记为当前维护文件。
- frontmatter 必填字段和正文“接棒入口”必须存在。
- 文件 `project_key` 必须与所在目录一致。
- checkpoint 的 `project_key` 与当前项目 `project_key` 不一致时，必须在跨机路径折算前强制暂停，显示当前项目和 checkpoint 各自的 key，并让用户选择中止、切换到目标项目根后重试，或显式进入只读 review；默认不得继续接力。
- 显式进入只读 review 时，不做路径折算，不把该文件记为当前维护 checkpoint，也不记住 expected revision。只读 review 不得把当前 cwd 当作目标项目根，后续不能据此调用 `/checkpoint-shared` 或 `/task-done-shared`。
- 当前项目与 checkpoint 的 key 相同时，比较两侧规范化 `project_remote`：两侧都不是 `none` 且值相等时才可自动继续；两侧都不是 `none` 且值不相等时，视为项目碰撞并停止。任一侧为 `none` 时，身份无法自动核实，选择、加载或更新前必须取得用户显式确认。
- 文件超过 7k token 时可以只读，但必须警告它违反保存协议，接棒后第一次保存应压缩到上限内。

### 5. 跨机器和跨客户端折算

读取 `last_client`、`last_model`、`last_machine`、`last_os`、`last_shell`、`path_style`、`last_project_root`，与当前环境比较：

- 当前项目根以当前机器真实 cwd/git root 为准，忽略上一棒绝对根路径。
- 正文里的项目相对路径直接拼当前项目根。
- `windows ↔ posix` 转换盘符和路径分隔符。
- 根据当前 shell 把 PowerShell/Bash 命令转换成等价形式。
- 运行时、虚拟环境、JDK、Node、Python 等绝对路径必须在当前机实际探测；不能把上一台机器的路径直接替换用户名后使用。
- 无法确定的转换标成“待用户确认”，禁止臆造。
- 不在 load 阶段修改 checkpoint 文件。

### 6. 记住接力状态

在本次对话中明确记住：

- 当前 shared checkpoint 完整路径
- expected revision N
- `project_key` 与 `project_remote`
- 上一棒 client/model/machine

后续 `/checkpoint-shared` 和 `/task-done-shared` 只能以这个 expected revision 为覆盖依据。

### 7. 详细复述并等待

```text
✅ 已加载共享 checkpoint：shared/<project_key>/<文件名>
revision：N
上一棒：<last_client>/<last_model> @ <last_machine>(<last_os>)
当前棒：<current_client>/<current_model> @ <current_machine>(<current_os>)
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

复述后**等待用户确认**再开始工作。`/checkpoint-shared-load` 只负责恢复和对齐，不得擅自执行实现、修改文件、提交或 push。

## 参数

安装者应把客户端原生参数映射为：空、`--here`、数字编号或公共工作区内的 shared checkpoint 路径。

# `/task-done-shared` 语义模板

> 本文件供任意大模型转换为自己的 command、prompt 或 skill。允许调整命令头和参数变量，不得改变公共存储、revision、归档和 Git 安全规则。

把当前共享接力任务标记完成，保存最终收口信息，移动到公共归档区并同步远端。

## 固定资源与边界

- 公共工作区：`~/.silvers/checkpoint-shared/`
- 活动位置：`~/.silvers/checkpoint-shared/shared/<project_key>/<文件名>`
- 归档位置：`~/.silvers/checkpoint-shared/shared/done/<project_key>/<文件名>`
- 只允许操作该目标 checkpoint；禁止改动远端其他目录。

用户主动调用 `/task-done-shared` 即视为确认本次可追溯归档和限定 push，不再插入 y/n；这不授权删除文件或操作当前项目 Git。

## 执行步骤

### 0. 载入平台块并同步

确认安装结果含当前平台约束。`<client_name>` 必须由安装者在安装时硬编码到本机命令，运行时不得写 `unknown`。检查固定 remote、未知 dirty 文件和未推送提交；有异常先停止或补推，禁止 stash/reset。

同步策略固定为 `git pull --ff-only`：

```bash
git -C "$HOME/.silvers/checkpoint-shared" pull --ff-only
```

不能 fast-forward 时停止，禁止 merge、rebase 或 force push。

### 1. 定位目标和 expected revision

优先级：

1. 用户显式传入公共工作区内的活动 checkpoint 路径。
2. 参数是数字：按 `/checkpoint-shared-load` 同一列表规则定位。
3. 本次对话记得当前 shared checkpoint 路径和 expected revision。
4. 以上都没有：停止，要求先 `/checkpoint-shared-load`。

只接受 `shared/<project_key>/` 下、状态为 `in-progress` 的文件。必须持有 expected revision N；pull 后远端仍为 N 才能归档，并把 revision 更新为 N+1。revision 不一致时停止并重新 load。

### 2. 采集本次真实身份与时间

新执行：

```bash
date '+%Y-%m-%dT%H:%M:%S%z'
```

client 使用安装时硬编码的 `<client_name>`，运行时不得写 `unknown`。采集当前 model/machine/os/shell/path style；无法可靠得知 model 时写 `unknown`，不能猜测。

### 3. 写最终状态

保持 `checkpoint_id`、`project_key`、`project_remote` 和 `created_at` 不变，更新：

```yaml
status: done
revision: <N+1>
updated_at: <本次真实时间>
last_client: <安装时硬编码的 client_name>
last_model: <当前模型或 unknown>
last_machine: <当前 hostname>
last_os: <darwin | linux | win32>
last_shell: <当前 shell>
path_style: <posix | windows>
last_project_root: <当前项目根>
done_at: <本次真实时间>
done_client: <安装时硬编码的 client_name>
done_model: <当前模型或 unknown>
done_machine: <当前 hostname>
```

归档前同步正文最终状态：

- 当前进度改为已完成边界。
- 已完成工作补上最后一轮验证命令和实际结果。
- 接棒入口改成“任务已完成，无需继续接棒”，但保留历史关键决策、陷阱和证据。
- 尚未处理的非阻塞事项移到 P2/long-term，明确它们不影响本任务完成。
- 正文仍不得超过 7k token，不得包含秘密；敏感参数写 `<REDACTED>`。

先写临时文件，校验后原子替换活动文件；失败时保留原文件。

### 4. 移动、提交和推送

确保目标目录存在，然后使用 `git mv`，禁止 `rm`、先删后写或复制后删除：

```bash
mkdir -p "$HOME/.silvers/checkpoint-shared/shared/done/<project_key>"
git -C "$HOME/.silvers/checkpoint-shared" mv -- \
  "shared/<project_key>/<文件名>" \
  "shared/done/<project_key>/<文件名>"
git -C "$HOME/.silvers/checkpoint-shared" add -- "shared/done/<project_key>/<文件名>"
git -C "$HOME/.silvers/checkpoint-shared" commit -m "done(shared/<project_key>): r<revision> <title> @<client>/<model>"
git -C "$HOME/.silvers/checkpoint-shared" push
```

只 stage 该 checkpoint，不使用无边界的 `git add -A`。

push 失败时保留本地提交并明确报告“归档尚未同步成功”；下次 shared 命令必须先补推。禁止把本地移动误报为远端归档成功。

### 5. 清理上下文并汇报

只有 push 成功后，才忘掉当前 shared checkpoint 路径和 expected revision：

```text
✅ 共享任务已归档并同步
原位置：shared/<project_key>/<文件名>
归档到：shared/done/<project_key>/<文件名>
revision：<N+1>
收尾者：<client>/<model> @ <machine>
```

## 参数

安装者应把客户端原生参数映射为：可选数字编号或公共工作区内的活动 checkpoint 路径。两种形式都不能绕过 expected revision 校验。

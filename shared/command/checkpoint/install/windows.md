# Windows 自主安装说明

本说明给正在执行安装的大模型使用。PowerShell 可以作为安装入口，但新三件套的 shell 运行时必须统一为 Git Bash。

## 1. 硬前提

Git for Windows / Git Bash 是**硬前提**。第一版不支持纯 PowerShell 运行时。

在 PowerShell 中定位 Git Bash，并在 Git Bash 中验证：

```bash
git --version
bash --version
date '+%Y-%m-%dT%H:%M:%S%z'
stat -c '%y' / >/dev/null
git ls-remote <CHECKPOINT_REPO_URL> HEAD
```

`MINGW*`、`MSYS*`、`CYGWIN*` 都归一化为 `last_os: win32`。

### 硬约束：不改用户已有连接配置

- 禁止修改 `~/.ssh/config`、`~/.gitconfig` 或任何用户级、系统级 Git 配置。
- 禁止擅自更换用户配置的远端地址或 URL scheme。
- 网络或认证不通时停止并报告用户，等待用户处理；不得自行切代理、端口、镜像或认证方式绕过。

## 2. Windows 取时硬约束

运行时必须使用 Git Bash 自带的：

```bash
date '+%Y-%m-%dT%H:%M:%S%z'
```

禁止 PowerShell `Get-Date` 和 `[DateTime]::Now`。它们在 Windows 上可能受 cold start 与 Defender 实时扫描影响，单次调用拖到数十秒甚至超时；长会话还容易误用旧时间戳。

该限制必须注入本机安装后的三条命令，不能只写在 README。

## 3. 创建独立公共工作区

不得复用任何客户端已有的 `checkpoints-online` clone。通过 Git Bash 执行：

```bash
git clone <CHECKPOINT_REPO_URL> \
  "$HOME/.silvers/checkpoint-shared"
```

PowerShell 中显示的 `$HOME` 与 Git Bash 的 `$HOME` 可能采用不同路径形式；三条运行时命令一律以 Git Bash 展开的 `$HOME/.silvers/checkpoint-shared` 为准。

目录已存在时先核实 remote、Git 状态和未推送提交，不能覆盖。

## 4. 转换并安装三条命令

完整读取 `../design.md` 与 `../commands/` 三份模板，识别当前客户端的 command、prompt、skill 或等价机制，自主生成：

- `checkpoint-shared`
- `checkpoint-shared-load`
- `task-done-shared`

可以转换客户端元数据、参数变量和安装路径；不能修改公共路径、schema、revision、7k 上限、接棒正文、redaction 和 Git 安全规则。只安装当前客户端文件，不修改其他客户端或旧 checkpoint 系列。

## 5. 脚本、编码和换行

把 `../scripts/list-shared-checkpoints.sh` 安装到当前客户端稳定脚本目录，所有调用都显式经过 Git Bash：

```bash
bash <installed-script-path>/list-shared-checkpoints.sh --help
```

强制要求：

- Markdown、脚本和 checkpoint 文件使用 UTF-8、LF。
- 避免 Windows PowerShell 5 默认 `Out-File` 编码；写入后检查不是 UTF-16，也没有乱码。
- 不允许 CRLF 破坏 shebang 或 Bash 解析；安装后运行 `bash -n`。
- 中文 slug 由模型按字符生成，禁止用 `head -c` 或其他按字节截断方法。
- Git Bash 使用 GNU `stat` 分支；online 有效修改时间仍以 Git commit time 为准。

## 6. 注入 Windows 运行时块

三条安装结果必须包含以下等价约束：

```markdown
<!-- CHECKPOINT-SHARED RUNTIME: windows-git-bash -->
- shell 操作强制通过 Git Bash；PowerShell 只用于安装。
- 当前时间必须新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`。
- 禁止 `Get-Date` / `[DateTime]::Now`。
- `MINGW*` / `MSYS*` / `CYGWIN*` 记为 win32。
- 路径记录必须同时尊重 `last_shell` 与 `path_style`，不能混用 `C:\...` 和 `/c/...`。
- 公共工作区固定为 `$HOME/.silvers/checkpoint-shared`。
- 文件统一 UTF-8、LF，禁止按字节截断中文。
- `<client_name>` 必须在安装时硬编码到本机三条命令，运行时禁止写 `unknown`；model 无法可靠取得时才允许写 `unknown`。
<!-- END CHECKPOINT-SHARED RUNTIME -->
```

## 7. 最小权限

当前客户端若有权限白名单：

- 只增量授权 `~/.silvers/checkpoint-shared/**` 的读写。
- 只授权通过 Git Bash 执行已安装扫描脚本。
- Git 自动写操作只允许 `git -C ~/.silvers/checkpoint-shared ...`。
- 不开放当前项目普通 push。
- 能可靠解析配置时保留原内容并做最小增量；不能可靠判断时输出片段让用户合并，禁止覆盖现有配置。

## 8. 冒烟验证

安装模型必须验证：

1. 三条命令在客户端中可发现。
2. 所有运行时 shell 调用都经过 Git Bash。
3. `date`、GNU `stat`、已配置远端访问和公共 clone 正常。
4. 用临时 `$HOME` Git fixture 验证 active/done、`--here`、中文、空格路径、UTF-8 和 LF。
5. 测试不向真实远端 push。
6. 新会话或必要刷新后，执行只读 `/checkpoint-shared-load` 列表验证。

最后汇报安装文件、配置增量、模板 source commit、运行时块与验证结果。

## 9. 卸载边界

只删除当前客户端新生成的三条命令、扫描脚本和对应最小权限。没有用户明确指令时，不得删除 `~/.silvers/checkpoint-shared/`，其中可能存在未推送接力提交。

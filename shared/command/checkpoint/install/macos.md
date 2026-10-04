# macOS 自主安装说明

本说明给正在执行安装的大模型使用。你需要把三份语义模板转换成当前客户端的原生命令，而不是把 Markdown 机械复制过去。

## 1. 前提检查

确认以下命令可用：

```bash
git --version
bash --version
date '+%Y-%m-%dT%H:%M:%S%z'
stat -f '%Sm' / >/dev/null
git ls-remote <CHECKPOINT_REPO_URL> HEAD
```

macOS 默认是 BSD `stat`；不能假设存在 GNU `stat -c`。`date '+%Y-%m-%dT%H:%M:%S%z'` 在 macOS 可直接使用，输出必须带时区。

远端探测须成功退出；空仓库没有 HEAD 输出也属正常。

### 硬约束：不改用户已有连接配置

- 禁止修改 `~/.ssh/config`、`~/.gitconfig` 或任何用户级、系统级 Git 配置。
- 禁止擅自更换用户配置的远端地址或 URL scheme。
- 网络或认证不通时停止并报告用户，等待用户处理；不得自行切代理、端口、镜像或认证方式绕过。

## 2. 创建独立公共工作区

不得复用任何客户端已有的 `checkpoints-online` clone：

```bash
git clone <CHECKPOINT_REPO_URL> \
  "$HOME/.silvers/checkpoint-shared"
```

目录已存在时先确认它是正确 remote 的干净 Git 工作区；不能直接覆盖。

## 3. 转换并安装三条命令

完整读取：

- `../design.md`
- `../commands/checkpoint-shared.md`
- `../commands/checkpoint-shared-load.md`
- `../commands/task-done-shared.md`

识别当前客户端使用 command、prompt、skill 还是其他机制，并生成：

- `checkpoint-shared`
- `checkpoint-shared-load`
- `task-done-shared`

可以转换命令元数据、参数占位符和提示措辞；不能修改公共路径、远端、schema、revision、7k 上限、详细接棒正文、安全规则和 fast-forward-only Git 行为。

只安装当前客户端自己的文件，禁止碰其他客户端目录，也禁止覆盖旧 checkpoint 命令。

## 4. 安装扫描脚本

把 `../scripts/list-shared-checkpoints.sh` 安装到当前客户端稳定的脚本目录，设置可执行位：

```bash
chmod +x <installed-script-path>/list-shared-checkpoints.sh
bash -n <installed-script-path>/list-shared-checkpoints.sh
```

然后把 load 命令中的 `<installed-script-path>` 替换为真实路径。路径含空格时必须正确引用。

## 5. 注入 macOS 运行时块

三条安装结果都必须包含以下等价约束，不能只留在本说明：

```markdown
<!-- CHECKPOINT-SHARED RUNTIME: macos -->
- shell 操作使用 Bash/Zsh 语义。
- 当前时间必须新执行 `date '+%Y-%m-%dT%H:%M:%S%z'`。
- 扫描脚本必须兼容 BSD `stat`；不可假设 GNU `stat -c`。
- 公共工作区固定为 `$HOME/.silvers/checkpoint-shared`。
- Markdown、脚本和文件名统一 UTF-8、LF。
- `<client_name>` 必须在安装时硬编码到本机三条命令，运行时禁止写 `unknown`；model 无法可靠取得时才允许写 `unknown`。
<!-- END CHECKPOINT-SHARED RUNTIME -->
```

## 6. 最小权限

如果当前客户端存在权限白名单或可信目录配置：

- 只增量授权读写 `~/.silvers/checkpoint-shared/**`。
- 只授权执行已安装的扫描脚本。
- Git 自动写操作只允许 `git -C ~/.silvers/checkpoint-shared ...`。
- 不扩大当前项目的 push 权限。
- 修改配置前先读取现状；能可靠增量合并时保留原内容，不能可靠判断格式时输出待合并片段，不得覆盖文件。

## 7. 冒烟验证

安装模型必须验证：

1. 客户端能发现三条新命令。
2. 三条命令均引用新公共路径，没有旧 `checkpoints-online` 路径。
3. 扫描脚本 `--help` 正常。
4. 用临时 `$HOME` 和临时 Git fixture 验证 active、done、`--here`、UTF-8 标题及带空格路径。
5. 冒烟不得向真实远端 push fixture。
6. 在新会话或客户端要求的刷新动作后，再做一次只读 `/checkpoint-shared-load` 列表验证。

最后汇报实际安装文件、配置增量、模板 source commit、运行时块和验证结果。

## 8. 卸载边界

卸载只删除当前客户端新生成的三条命令、扫描脚本和对应最小权限条目。除非用户明确要求，不能删除 `~/.silvers/checkpoint-shared/`，因为其中可能有尚未推送的接力提交。

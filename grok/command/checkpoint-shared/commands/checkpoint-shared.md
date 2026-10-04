把当前任务写成共享 checkpoint，写入公共接力区并同步远端。

本命令是 Grok 适配。协议强制规则见 `<CHECKPOINT_TOOLS>/shared/command/checkpoint/commands/checkpoint-shared.md` 和 `<CHECKPOINT_TOOLS>/shared/command/checkpoint/design.md`，先 `read_file` 再执行。

安装时已硬编码：

- client_name: `grok`
- 工作区: `~/.silvers/checkpoint-shared/`
- 只允许 `shared/`
- 远端: `<CHECKPOINT_REPO_URL>`

用 `run_terminal_command` 做 git clone/pull/add/commit/push。时间用 Bash `date`，不要 PowerShell。文件 UTF-8 LF。

## 本机运行时约束

<!-- CHECKPOINT-SHARED RUNTIME -->
- client_name 固定为 `grok`，不得写 `unknown`。
- macOS/Linux 使用 Bash/Zsh，Windows 使用 Git Bash，禁止 PowerShell 取时；时间必须新执行 `date`。
- 文件 UTF-8、LF；扫描器兼容 BSD/GNU stat；公共工作区 `$HOME/.silvers/checkpoint-shared`。
- 模板中的 `<installed-script-path>` 映射为 `~/.grok/scripts`；参数从用户调用本命令后的文字取得。
- 同步和 revision 等行为全部遵守读取的共享协议；load 不得 commit 或 push。
<!-- END CHECKPOINT-SHARED RUNTIME -->

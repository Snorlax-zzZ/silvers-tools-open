从公共接力区加载一棒共享 checkpoint，折算到当前机器和 Grok。

先读 `<CHECKPOINT_TOOLS>/shared/command/checkpoint/commands/checkpoint-shared-load.md`。

硬编码：client_name=`grok`，工作区 `~/.silvers/checkpoint-shared/`，只读 `shared/`（不含乱翻 `cc/` `codex/` 等目录，除非文件在 `shared/`）。

必须调用 `bash ~/.grok/scripts/list-shared-checkpoints.sh`（当前项目模式追加 `--here <project_key>`）；未安装则停止并按 README 安装，禁止临时拼接扫描命令。

## 本机运行时约束

<!-- CHECKPOINT-SHARED RUNTIME -->
- client_name 固定为 `grok`，不得写 `unknown`。
- macOS/Linux 使用 Bash/Zsh，Windows 使用 Git Bash，禁止 PowerShell 取时；时间必须新执行 `date`。
- 文件 UTF-8、LF；扫描器兼容 BSD/GNU stat；公共工作区 `$HOME/.silvers/checkpoint-shared`。
- 模板中的 `<installed-script-path>` 映射为 `~/.grok/scripts`；参数从用户调用本命令后的文字取得。
- 同步和 revision 等行为全部遵守读取的共享协议；load 不得 commit 或 push。
<!-- END CHECKPOINT-SHARED RUNTIME -->

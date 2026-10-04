# Checkpoint Shared 三件套

> 给多个大模型顺序接力同一个任务使用，同时支持 macOS ↔ Windows 跨机器恢复。

## 三条新命令

| 命令 | 作用 |
|---|---|
| `/checkpoint-shared` | 把当前任务状态保存到公共接力区并同步远端 |
| `/checkpoint-shared-load` | 拉取公共接力区，加载一棒并折算当前机器环境 |
| `/task-done-shared` | 完成任务，把公共 checkpoint 归档并同步远端 |

这套命令与各客户端原有的本地 checkpoint、`checkpoint-online` 系列完全并行。旧命令、旧 clone 和旧数据目录都不修改、不迁移。

## 重要：这是自主安装模板

[`commands/`](commands/) 中的文件**不是待直接复制的成品命令**，而是三条命令的模型无关语义模板。安装它的大模型必须：

1. 识别自己的原生命令载体（command、prompt、skill 或等价机制）。
2. 完整阅读本 README、[`design.md`](design.md)、三份命令模板和当前平台说明。
3. 把模板转换成自己的原生格式，安装到自己的配置目录；不要安装或修改其他客户端的文件。
4. 保留所有标注为“强制”“禁止”“仅限”的协议规则。
5. 把扫描脚本安装到自己可稳定调用的位置，并把实际路径写进 load 命令。
6. 注入当前平台的运行时约束。
7. 如客户端需要权限配置，只对新公共工作区和已安装脚本做最小增量授权；不得覆盖已有配置。
8. 做完只读扫描和临时 fixture 冒烟，汇报安装文件、适配差异和验证结果。

没有预先适配文档的新模型，也应按以上步骤自行判断安装方式；仓库不维护 adapter 清单。

## 固定运行时资源

- 远端仓库：`<CHECKPOINT_REPO_URL>`
- 新公共 clone：`~/.silvers/checkpoint-shared/`
- 进行中：`shared/<project_key>/<checkpoint_id>.md`
- 已完成：`shared/done/<project_key>/<checkpoint_id>.md`

新三件套只能操作 `shared/`。远端现有的 `cc/`、`codex/`、`zcode/` 及其他目录不在授权范围内。

## 安装前提

- 能访问上面填入的 `<CHECKPOINT_REPO_URL>`（`git ls-remote <CHECKPOINT_REPO_URL> HEAD` 能读到即可）。
- 已安装 Git 和 Bash。
- macOS：阅读 [`install/macos.md`](install/macos.md)。
- Windows：Git for Windows / Git Bash 是硬前提，阅读 [`install/windows.md`](install/windows.md)。

## 安装验收

安装模型必须至少核实：

- 三条命令能在客户端原生入口中被发现。
- 三条命令均指向 `~/.silvers/checkpoint-shared/`，没有引用旧 `checkpoints-online` 目录。
- scan 脚本能在临时 `$HOME` fixture 中列出 `shared/` 活动项并排除 `shared/done/`。
- macOS/Windows 运行时约束已经进入本机安装结果，而不只是留在 README。
- 测试没有向远端 push fixture。

完整协议与状态流以 [`design.md`](design.md) 为准。

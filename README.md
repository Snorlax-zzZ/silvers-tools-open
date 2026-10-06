# silvers-tools-open

面向 AI 编码客户端的开源工具集合，集中维护可复用的 skill、command、公共脚本与工具，以及对应的安装和使用说明。

各工具在同一仓库中按目录组织和持续更新，可以按需选择安装。Checkpoint 是首批收录的工具系列；后续新增工具也会加入本仓库，并更新下面的索引。

## 当前收录

| 工具 | 用途 | 内容与安装入口 |
|---|---|---|
| Checkpoint | 保存任务状态，在新会话、另一台机器或另一个客户端中继续 | 本地、云端、公共接力三组命令；见下方 [Checkpoint](#checkpoint) |
| Relay 接力棒 | 按阶段在不同会话、模型和机器之间交接任务，保留决策、完成标准与证据 | [入门与机制](shared/tool/relay/README.md)、[统一安装说明](shared/command/relay/README.md)、[三个共享 skill](shared/skill/README.md) |

## 目录组织

```text
cc/       Claude Code 的工具与适配
codex/    Codex 的工具与适配
zcode/    ZCode 的工具与适配
grok/     Grok 的工具与适配
pi/       pi 的工具与适配
dsh/      DSH 的工具与适配
shared/   跨客户端共享的工具、协议和安装模板
```

一级目录按客户端或共享范围组织，目录内再按工具类型和具体工具划分。每个工具的依赖、支持平台和安装步骤，以对应目录的 README 为准。

## 使用方式

从工具索引选择需要的功能，再阅读对应安装说明。也可以让当前客户端的助手阅读说明，识别自己的原生 command、prompt 或 skill 机制，完成适配安装与验证。

共享工具由 `shared/` 提供统一协议和模板；客户端专属入口保留在对应目录。安装时保留说明要求的依赖目录，并填写本机路径及自己的远端地址。

## Checkpoint

把任务状态保存为文档，在新会话、另一台机器或另一个客户端中继续。

### 三个系列

| 系列 | 用途 | 命令 |
|---|---|---|
| 本地 | 同一台电脑跨会话恢复 | checkpoint / checkpoint-load / task-done |
| 云端 | 同一客户端跨机器恢复 | checkpoint-online / checkpoint-load-online / task-done-online |
| 公共接力 | 多客户端按顺序接力同一任务 | checkpoint-shared / checkpoint-shared-load / task-done-shared |

公共接力有 revision 校验及跨机器环境折算，支持顺序交接；不支持并发改写同一个任务。
各系列使用独立目录，安装时按需求选择。

### 客户端与安装入口

| 客户端 | 本地 | 云端 | 公共接力 | 安装说明 |
|---|---|---|---|---|
| Claude Code | 有 | 有 | 共享模板适配 | [本地与云端](cc/command/checkpoint/README.md) |
| Codex | 有 | 有 | 共享模板适配 | [本地与云端](codex/command/checkpoint/README.md) |
| ZCode | 有 | 有 | 有 | [九个 skill 入口](zcode/skill/README.md)、[公共接力](zcode/skill/checkpoint-shared/README.md) |
| Grok | 有 | 暂无专属版本 | 有 | [本地](grok/command/checkpoint/README.md)、[公共接力](grok/command/checkpoint-shared/README.md) |
| pi | 有 | 暂无专属版本 | 有 | [本地](pi/command/checkpoint/README.md)、[公共接力](pi/command/checkpoint-shared/README.md) |
| DSH | 有 | 有 | 有 | [九条命令及安装](dsh/command/README.md) |

公共接力的统一协议与安装入口在 [shared/command/checkpoint/README.md](shared/command/checkpoint/README.md)。

- **DSH** 指 DeepSeek 官方开源的 **DeepSeek Harness**。获取方式见 [官方项目](https://github.com/deepseek-ai/deepseek-harness)；本仓适配依赖其文件系统 skill 插件，具体要求见 [DSH 安装说明](dsh/command/README.md)。
- **ZCode** 指 ZCode AI 编程客户端。本仓适配使用 **ZCode Agent** 的用户级 Skill 机制；客户端下载见 [官方安装文档](https://zcode.z.ai/cn/docs/install)，接入方式见 [ZCode 安装说明](zcode/skill/README.md)。

### 安装前

准备 Git 和 Bash；Windows 使用 Git Bash，并阅读对应平台的安装说明。
完整保留仓库目录结构，部分客户端的薄适配会读取 `cc/command/checkpoint/` 和
`shared/command/checkpoint/` 下的协议，不能只搬走一条命令文件。

- `<CHECKPOINT_REPO_URL>`：替换为你自己用于保存 checkpoint 的 Git 仓库地址，可以是私有仓。
- `<CHECKPOINT_TOOLS>` / `<SILVERS_TOOLS>`：替换为本工具仓库在当前机器的绝对路径，两者含义相同。
- `<client_name>` / `<installed-script-path>`：按对应安装说明填当前客户端名称和实际脚本位置。

只替换上述安装配置，不替换命令正文中的 `<title>`、`<project_key>` 等运行时字段。
没有配置存档仓库时可以使用本地系列；云端和公共接力系列须先配置自己的远端。
两个系列的 clone 目录独立，即使远端相同也不能共用同一工作区。

### 存档数据与可见范围

本仓库发布工具；`<CHECKPOINT_REPO_URL>` 指你自己用于保存任务存档的另一个 Git 仓库。
云端和公共接力会把存档正文及元数据提交、推送到该仓库。存档可能包含任务说明、项目远端地址、
机器名和项目绝对路径；绝对路径也可能带有本机用户名。这些内容会对有权读取存档仓库的人可见。

建议使用权限受控的私有仓库存放实际任务存档，并在推送前核对正文和元数据，移除不宜共享的内容。
工具仓库公开不代表存档仓库也应公开；删除最新版本中的内容也不会自动清除 Git 历史。

### 使用

安装并确认当前客户端能发现入口后，显式调用存档、加载或完成归档命令。
加载首先报告恢复位置、下一步和风险，是否继续动手遵循对应协议及用户授权。
存档前应核对真实内容，移除 token、密码、Cookie、私钥等敏感值，避免保存完整聊天记录和大段源码。

## Relay 接力棒

Relay 包含一套 Python CLI、稳定 launcher、三个共享 skill 参考源以及统一安装/升级手册。
模型负责整理和理解任务，CLI 负责结构校验、revision 冲突检查、独立 Git 存储和同步。
日常只需交棒 `relay`、接棒 `relay-load`、收棒 `relay-done` 三个原生入口，具体调用形式由客户端安装适配决定。

先阅读 [Relay 入门](shared/tool/relay/README.md#第一次使用从这里开始)，再让当前客户端的助手按
[统一安装说明](shared/command/relay/README.md) 识别环境并安装。需要 Python 3.11+、Git 和自己创建的独立 Relay 数据仓库；同机各客户端共用 runtime，各自安装入口。
存储仓库中包含任务正文与元数据，建议保持私有；它与本工具仓库、业务项目及 Checkpoint 数据仓库分别管理。

## 贡献

此仓库由维护者的源仓库生成，后续同步会覆盖生成文件并删除产物之外的文件。
提交问题或改进建议时，请先开 Issue；维护者把等价变更合入源文件后再导出，避免下次更新丢失贡献。

## License

[MIT](LICENSE)

---
name: dsh-checkpoint-index
description: DSH checkpoint 安装索引，不是可调用技能
user-invocable: false
disable-model-invocation: true
---

# DSH Checkpoint 系列

DSH 是 DeepSeek 官方开源的 **DeepSeek Harness**。获取与启动方法见
[官方项目](https://github.com/deepseek-ai/deepseek-harness)，使用文档见
[官方文档站](https://deepseek-harness.github.io/deepseek-harness/)。

DSH 通过用户可调用 skill 提供命令入口。本目录的平面 Markdown 文件包含 name、description
和 user-invocable 元数据，由当前客户端支持的 skill 目录引用机制接入。
本适配要求当前 DSH profile 启用 `@deepseek-ai/dsh-skill-filesystem`，并支持平面 Markdown
技能及 `customSkillDirs` 配置；机制以 [官方插件说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md) 为准。
DSH 目前处于开发者预览阶段，版本升级后请重新核对配置和下方验收项。

## 九个入口

| 系列 | 存档 | 加载 | 完成 |
|---|---|---|---|
| 本地 | [checkpoint](checkpoint.md) | [checkpoint-load](checkpoint-load.md) | [task-done](task-done.md) |
| 云端 | [checkpoint-online](checkpoint-online.md) | [checkpoint-load-online](checkpoint-load-online.md) | [task-done-online](task-done-online.md) |
| 公共接力 | [checkpoint-shared](checkpoint-shared.md) | [checkpoint-shared-load](checkpoint-shared-load.md) | [task-done-shared](task-done-shared.md) |

## 安装

使用云端或公共接力前，先阅读根目录的 [存档数据与可见范围](../../README.md#存档数据与可见范围)。

1. 在当前 DSH profile 的配置中，把本仓 `dsh/command/` 的**绝对路径**加入
   `skill-filesystem` 的 `customSkillDirs`。先确认当前 profile 及已有配置，合并该项，不覆盖整份配置。
2. 把命令中的 `<CHECKPOINT_TOOLS>` 换成本工具仓库的绝对路径；云端或公共接力还需把
   `<CHECKPOINT_REPO_URL>` 换成自己的 checkpoint 存储仓库。引用目录时在自己维护的工具副本中配置。
3. 安装扫描脚本（macOS / Linux / Windows Git Bash）：

```bash
mkdir -p ~/.dsh/scripts
cp dsh/command/scripts/list-checkpoints.sh ~/.dsh/scripts/list-checkpoints.sh
cp shared/command/checkpoint/scripts/list-shared-checkpoints.sh ~/.dsh/scripts/list-shared-checkpoints.sh
chmod +x ~/.dsh/scripts/list-checkpoints.sh ~/.dsh/scripts/list-shared-checkpoints.sh
bash -n ~/.dsh/scripts/list-checkpoints.sh
bash -n ~/.dsh/scripts/list-shared-checkpoints.sh
```

本地根为 `~/.dsh/checkpoints/`。云端 clone 为 `~/.dsh/checkpoints-online/`，只写 `dsh/` 命名空间；
公共接力 clone 为 `~/.silvers/checkpoint-shared/`，只操作 `shared/`，两者不要复用。
需要使用对应系列时再 clone 自己配置的仓库；已有 clone 先核对 origin，不覆盖或修改远端。

macOS / Linux 的引用路径如 `/absolute/path/to/tools/dsh/command`；Windows 如
`C:/absolute/path/to/tools/dsh/command`。Windows 的扫描和 Git 操作按当前客户端能力调用 Git Bash，
不要直接用 PowerShell 重写扫描器。

## 验收

- 当前客户端的 skill 列表能发现上述九个入口；必要时按当前版本重新加载或开启新会话。
- 两份扫描器的 `--help` 可运行；在临时存档中验证本地/云端只扫描 DSH 对应范围，公共扫描只操作 shared。
- 试跑不要把合成存档推到真实远端。真实使用时按命令协议确认项目、权限、环境和修订号。

本地及云端基础说明见 [cc 版协议入口](../../cc/command/checkpoint/README.md)，
公共接力完整协议见 [shared 说明](../../shared/command/checkpoint/README.md) 和 [design.md](../../shared/command/checkpoint/design.md)。

## 权限

存档和脚本位于项目工作区外，是否可读写取决于当前客户端的沙箱与审批策略。发生拒绝时按客户端提供的审批入口申请本次所需访问，或请用户调整权限；不得自行绕过限制、修改全局配置或把存档搬入项目。模板中的权限说明不能代替实际授权。

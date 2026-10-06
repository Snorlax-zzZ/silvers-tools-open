# Codex 权限适配参考

> 本页供安装模型结合当前 Codex 版本、本机路径和既有配置生成候选；不是可机械复制的配置，也不授权直接覆盖 `~/.codex/config.toml` 或现有规则文件。

## 目标

用户显式调用 Relay 入口后，本次入口所需的稳定 launcher、独立 Relay store 和请求草稿操作应作为一个完整流程执行，不得按 `status`、`draft create`、编辑草稿、`validate`、`pass/successor/done`、`cleanup` 逐步弹窗。

Codex 的权限适配必须同时覆盖两条路径，两者缺一不可：

1. 允许模型编辑 `<RELAY_WORK_DIR>` 下由 `relay draft create` 返回的临时草稿；
2. 允许 `<STABLE_RELAY_LAUNCHER>` 执行日常 Relay 子命令，由 CLI 自己管理正式 store、内部 Git 和已配置 remote。

只加命令规则会让草稿编辑继续询问；只加 writable root 又会让 store 内部 Git 与远端同步继续询问。

## 候选 writable root

先读取现有 Codex 配置，确认它使用传统 `sandbox_workspace_write` 还是命名 permission profile。只把实际 `<relay-home>/work` 作为额外可写目录，不把整个 home、用户目录或业务项目扩大成新权限边界。

传统配置的候选语义是把 `<RELAY_WORK_DIR>` 合并进现有 `sandbox_workspace_write.writable_roots` 列表，而不是新建重复 TOML section：

```toml
[sandbox_workspace_write]
writable_roots = ["<RELAY_WORK_DIR>"]
```

若当前 Codex 使用命名 permission profile，按该版本官方格式生成等价的、只覆盖 `<RELAY_WORK_DIR>` 的 filesystem 增量。不得同时混用两套互斥配置。

## 候选 execpolicy 规则

优先生成独立 Relay 规则文件，而不是继续向 `default.rules` 累积每个 relay id、revision 或草稿路径的一次性规则。下面只表达语义，安装模型必须替换路径、核对当前 Codex 规则语法并生成候选：

```python
prefix_rule(
    pattern = [
        "<STABLE_RELAY_LAUNCHER>",
        [
            "--version",
            "--help",
            "status",
            "list",
            "load",
            "history",
            "recall",
            "draft",
            "validate",
            "pass",
            "successor",
            "done",
            "withdraw",
        ],
    ],
    decision = "allow",
    justification = "用户显式调用 Relay 时，允许稳定 launcher 管理独立 Relay store 与请求草稿。",
    match = [
        "<STABLE_RELAY_LAUNCHER> status",
        "<STABLE_RELAY_LAUNCHER> draft create --operation successor --relay-id <RELAY_ID>",
        "<STABLE_RELAY_LAUNCHER> pass --request <RELAY_WORK_DIR>/request.json --client <WRITER_IDENTITY> --model <MODEL>",
        "<STABLE_RELAY_LAUNCHER> successor --request <RELAY_WORK_DIR>/request.json --client <WRITER_IDENTITY> --model <MODEL>",
    ],
    not_match = [
        "<STABLE_RELAY_LAUNCHER> setup --remote git@github.com:example/relay.git",
        "<STABLE_RELAY_LAUNCHER> migrate",
    ],
)
```

`setup` 不得进入免询问规则；安装、更换 remote 或修改配置仍需单独授权。规则也不得放行源码仓里的开发入口、任意 Python、任意 Git 或任意 shell 包装命令。

`migrate` 属于数据升级维护，会改写当前项目的存储记录并提交、同步；它也不进入日常入口的免询问白名单。显式交棒、接棒或收棒不包含数据迁移授权，只有用户明确授权本次迁移后，才按宿主权限执行该维护动作，不因此扩大全局放行范围。

用当前 Codex CLI 对代表性命令逐项运行 `codex execpolicy check`，至少证明日常入口为 `allow`、`setup` 和 `migrate` 不匹配。若客户端无法验证规则，保持候选未安装并报告。

## 执行时语义

- 入口先使用当前已经生效的权限，不得预先把每条 Relay 命令标成升级执行；
- `--help` 和只读 `status` 不得成为主动升级理由；
- 当前环境为 Full access / no-approval 时，调用中不得附加任何升级审批元数据；
- 若宿主真实拒绝一次必要操作，停止逐条重试，只请求一次覆盖稳定 launcher、`<RELAY_WORK_DIR>` 和已配置 remote 的有界权限；
- 权限切换只在当前命令结束并刷新执行环境后生效；不得把仍按旧权限运行的调用误报成新权限失效。

## 安装与更新门

权限配置和三个客户端入口一样是本机长期文件。安装模型必须读取现状，在临时位置生成候选，逐文件 diff，区分共享语义、本机路径与既有规则，等待用户明确确认后手工叠加。禁止覆盖 `config.toml`、覆盖整个 `default.rules`，或删除无关规则。

独立 Relay 规则文件可作为 Codex 客户端适配文件记录 SHA-256；共享 `config.toml` 不应整文件登记为 Relay 所有物，但安装报告必须记录加入的精确键和值。更新时应收敛旧的逐条 Relay allow 规则，且只删除已被新规则完整覆盖的 Relay 专属项。

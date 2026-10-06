# Relay

Relay 是模型无关的确定性接力 CLI。它让不同模型、客户端和机器围绕同一根阶段棒顺序接力，同时控制默认上下文体积、旧决策遗忘和 Git 写入风险。

## 第一次使用，从这里开始

假设你正在让一个编码助手实现功能，想换另一个助手继续。Relay 把目标、阶段完成标准、有效决策、已验证证据、当前代码状态和下一步整理成结构化接力棒；新助手从独立 Git 存储仓库加载它，先与你核对理解，再继续工作。它也适合在另一台机器或新会话中恢复同一任务。

Relay 由两部分协作：

| 部分 | 作用 | 所在位置 |
|---|---|---|
| Python CLI 与稳定 launcher | 校验结构与 revision、维护 JSON/Markdown、控制 Git 同步和写入边界 | 本目录的 `src/`、`launcher/` |
| 三个模型侧入口 | 从会话提炼内容、调用 CLI、向你报告结果或确认理解 | [`../../skill/README.md`](../../skill/README.md) 和 [`../../command/relay/README.md`](../../command/relay/README.md) |

CLI 不调用模型 API，也不会自动派发给其他助手。**你决定何时交棒、交给谁，以及阶段边界。**同一根棒用于顺序接力；不同模型同时写入时，旧 revision 会被拒绝，需要先重新核对当前状态。

### 安装前准备什么

1. Python 3.11+、Git，以及能够读文件和执行终端命令的编码客户端。Python 包没有运行时第三方依赖；具体安装环境与构建条件由安装模型检查。
2. 本工具仓库的一份完整 checkout。保留 `shared/tool/relay/`、`shared/command/relay/` 和 `shared/skill/relay*` 的相对位置，安装来源应对应已提交版本。
3. 一座你自己创建、各参与机器都能访问的**独立 Relay Git 仓库**，建议为私有仓。它不能是正在开发的项目仓库，也不能复用 Checkpoint 或其他工具的数据仓库。不要把令牌或密码写进仓库 URL。
4. 一个你确认的稳定交棒作者名称。它用于记录谁写入这次接力，可以是自选名称，与客户端类型或实际模型名称分开记录。

业务项目必须是**至少已有一次提交、能解析 `HEAD` 的 Git 仓库**。只有 `git init` 而没有提交的新仓，尚不能运行需要项目快照的 Relay 操作。首次交棒前可只读执行 `git rev-parse --verify HEAD` 核实；失败时先说明该前提，由用户按项目规则完成首次提交，不得为了让 Relay 通过而自动提交业务代码。该限制不妨碍查看 `relay --version` 或只读 `relay status`。

同一台电脑只需要一套 Relay runtime、稳定 launcher 和 store；每个客户端分别安装三个原生入口即可。另一台电脑安装自己的 runtime，通过同一个独立远端同步数据。

跨机器接棒还要求**业务项目的 `origin` 经 CLI 规范化后相同**。同一仓库的 HTTPS 与 SSH 地址目前会生成不同的项目身份，项目路径大小写也不会自动合并；仅使用同一个 Relay 数据远端不足以满足这个条件。业务项目没有 `origin` 时，身份使用本机绝对路径，不保证跨机器对应。接棒列表意外为空时，先核对两端的业务项目身份，不要据此另建一根棒或擅自更改项目 remote。

### 怎么安装

让**当前客户端的助手**从 [统一安装说明](../../command/relay/README.md) 开始，按当前平台和客户端生成安装候选。可直接告诉它：

> 请阅读此仓库 `shared/tool/relay/README.md` 和 `shared/command/relay/README.md`，为当前客户端安装 Relay。先核实本机环境和已有安装；我会提供独立 Relay 仓库地址及交棒作者名称。请按统一手册安装或复用 runtime，为当前客户端生成交棒、接棒、收棒三个入口，并展示入口与权限的逐文件差异供我确认。

共享 skill 是安装时的行为参考源，不能直接整目录复制后就认为安装完成。安装模型会适配客户端的 command / prompt / skill 格式、稳定 CLI 路径和本机权限。运行时与安装回执通过核验、三个原生入口可发现，并完成临时存储仓库验证后，才算安装可用。平台操作见 [macOS/Linux](../../command/relay/install/macos.md)、[Windows](../../command/relay/install/windows.md)；已有安装见 [升级说明](../../command/relay/UPGRADE.md)。

### 日常只记三个入口

| 时机 | 你调用 | 助手会做什么 |
|---|---|---|
| 当前会话准备交给下一位 | `relay`（交棒） | 整理当前真相并保存或更新接力棒，报告同步结果 |
| 新会话、另一客户端或另一台机器接手 | `relay-load`（接棒） | 加载当前项目的棒；多项时让你选编号；给出理解回执，等你确认后继续 |
| 当前阶段完成且暂时没有下一阶段 | `relay-done`（收棒） | 核对完成标准及证据，符合条件后归档 |

这三个是客户端中安装后的语义入口，例如 `/relay` 或 `$relay`；具体调用形式由安装模型告诉你。你不需要手填 relay id、revision 或请求 JSON。先切到相应业务项目再调用，项目身份由 CLI 检查。只有显式调用才执行接力操作。

一个简单流程：在助手 A 中调用交棒 → 切换到助手 B 的同一项目 → 调用接棒 → 阅读并确认理解回执 → 继续实现 → 阶段完成后调用收棒。中途再次换助手仍更新同一根棒；你明确开启下一阶段时，交棒入口用一次 `successor` 操作完成旧阶段归档与新阶段建立。

### 数据、隐私与失败处理

Relay 的独立存储仓库会保存任务内容、决策和证据、项目远端与代码版本、作者/模型标识及运行环境信息，其中 `last_machine` 保存写入机器的主机名；正文、机器名和路径可能包含个人或业务信息。能读取该仓库的人也能读取这些内容及 Git 历史。CLI 的安全扫描不能替代你和写入助手对实际内容的核对，使用前应限制仓库访问权限；本工具源码公开不要求你的接力数据公开。

Relay 数据仓的自动 Git 提交通过命令级配置使用 `Silvers Relay <relay@localhost>`，这是工具内置的合成身份，与记录里的 `--client` 作者标识、公开工具源码仓的提交身份分别独立。安装时应确认独立数据远端允许这种提交身份；若远端有作者邮箱校验规则，先核对其要求。不要因此修改业务仓或全局 Git 身份。

如果报告同步失败，先查看返回的 `sync_error` 和 `details.local_committed`：本地可能已经推进了 revision，不能当成“完全没保存”而重复新建。按返回的恢复信息核对本地/远端状态；接棒遇到代码不同、未提交修改、版本不兼容或缺少完成证据时，也应先处理该差异。不要手工编辑正式 canonical JSON 来跳过检查。

## 0.9.1 核心模型

每根棒保存同名文件对：

```text
store/
├── .silvers-relay-store.json
├── active/<project_key>/<relay_id>.json
├── active/<project_key>/<relay_id>.md
├── done/<project_key>/<relay_id>.json
├── done/<project_key>/<relay_id>.md
├── withdrawn/<project_key>/<relay_id>.json
└── withdrawn/<project_key>/<relay_id>.md
```

- canonical JSON 是唯一权威真相；
- 派生 Markdown 由 CLI 从 canonical JSON 确定性生成，供人阅读；
- JSON 与 Markdown 在同一锁、同一 commit 和同一回滚边界内更新；
- canonical JSON 缺失或损坏时停止；Markdown 缺失、被改或过大只写入非阻断的 `document_export` 诊断，`load` 始终采用 canonical JSON 现渲染内容；
- 正式产物永远不写进当前业务项目。

`withdrawn/` 保存用户裁定为错误创建的棒及其撤销信息；它不是已完成阶段，不进入 `history`，也不能充当前序阶段。

结构化 delta、阶段 history、decision/criteria recall、完整活动决策、当前 revision 判据回执和前阶段收尾摘要都由 canonical JSON/Git 生成，不增加 timeline、changelog 或旁路摘要文件。当前 CLI 写入 `relay_schema = 6`，并兼容读取 schema 2/3/4/5/6 的既有文件对。本版提供 `relay migrate` 原子迁移当前项目的全部 tip；当前 runtime 继续承担受支持旧格式的历史读取。

## 长期接力边界

- request JSON 最大 96 KiB；canonical JSON、派生 Markdown、完整 `load`、`history` 和单项 `recall` 共用 128 KiB 总硬上限；
- 完整 `load` 超过 48 KiB 时只返回统一的 `budget_advice`，提示最厚的顶层内容字段，不拒绝写入；
- 每次 active 写入都按最终 canonical、现渲染 Markdown 和完整 load 响应做精确序列化预检，超限时在写文件、bump revision 和 commit 之前拒绝；
- 当前 canonical 的 `snapshot.decisions` 始终携带全部活动决策全文；请求用 `changes.active_decision_ids` 精确确认活动集合，退出必须通过 `changes.decisions` 显式 `retire` 或 `supersede`；
- `decision_id_high_watermark` 防止已经退出的决策 ID 被静默复用；
- `criteria_changes` 只保存本 revision 的完整判据变更回执，并分配本 revision 内从 1 开始的 `ordinal`；Git revision 保存旧回执，不维护累计 registry，也不分页；
- Git commit message 不承担语义大纲，Git/canonical diff 才是 revision 历史。

128 KiB 是唯一内容硬门，不再拆成 Markdown、结构化热层、delta、固定壳层或安装警告预留等互相争用的分区。安装诊断有独立的 8 KiB 截断上限，不能让一根已经成功写入的棒因为源码转 dirty 而突然无法 load。软预算只提示内容精炼：只删流水账、时间线、重复结论、日志与源码转储；决策四要素、逐条完成状态和仍有效约束不得删除。

阶段棒必须包含整体结果、CLI 固定的 `phase_id`、`phase.outcome`、`phase.done_when`、与判据逐条对齐的 `phase.done_when_status` 和可执行第一步。状态支持 `pending`、`met`、`partial`、`unverifiable`，后两者必须带原因；CLI 不替写入方推定 `met`。`phase_id` 与承载该阶段的 relay id 相同，模型不可通过改写 `phase.name` 制造阶段切换。新阶段引用同项目 done predecessor，CLI 会固化 predecessor revision，逐字继承整体设计契约并继承仍有效决策。

Relay 的典型用途是让用户按自己定义的阶段把工作交给不同模型，以发挥各自的模型优势、成本或偏好。**用户拥有唯一交棒决定权，阶段边界也由用户定义**：是否交棒、何时交棒、交给谁都由用户决定；显式交棒请求必须执行，不得以任务或阶段的大小设置交棒门槛。Relay 不选择或调用下一模型，只保存供下一模型加载的当前真相。

内部批次、测试检查点或普通代码审查不是模型自行停下、交棒或创建新阶段的理由；用户明确选择在这些节点交棒时则必须照办。`next_step.done_when` 只定义接棒后的第一步完成，不等于整阶段 `phase.done_when`，也不是模型自行设定的阶段停点。用户未要求换模型时，接棒模型应持续推进整根棒；只有阶段完成、真实阻塞或权限升级才可自行停止。

阶段中途由用户明确换模型时，交棒入口更新同一 active Relay，下一模型直接 load；不得要求用户在模型之间复制粘贴审查文本，也不会自动调用其他模型或外部服务。用户定义下一阶段时，交棒入口用一个 `successor` CAS 同时归档旧阶段并创建新 active；交棒方只写新阶段变化量，不重建整个容器。

完整协议见 [`design.md`](design.md)。

## 跨平台运行目录

`SILVERS_RELAY_HOME` 非空时始终优先。未覆盖时：

| 平台 | 默认 Relay home |
|---|---|
| macOS / Linux | `~/.silvers/relay` |
| Windows | `%LOCALAPPDATA%\Silvers\Relay` |

Windows 缺少 `LOCALAPPDATA` 时才回退到用户目录下的 `AppData\Local\Silvers\Relay`。版本化代码与持久数据平级隔离：

```text
<relay-home>/
├── bin/                         # 稳定 launcher
├── runtimes/<version>/          # 不原地覆盖的独立 venv 与 runtime receipt
├── current.json                 # 活动 runtime 指针
├── install.json                 # 本机安装回执
├── config.json                  # 独立 remote
├── .store.relay.lock
├── store/
└── work/
```

`config.json`、`.store.relay.lock`、`store/` 和 `work/` 均由 CLI 解析；客户端适配器不得自行拼接平台路径。runtime 更新不得重建持久数据。

`current.json` 只保存 `current_schema` 和 `runtimes/<version>/` 下的 POSIX 相对 entrypoint。`runtimes/<version>/runtime.json`、`install.json` 与 current pointer 会由 `relay status` 做结构和引用一致性校验；部分存在、版本不一致、source commit 不一致或路径逃逸时 fail closed。`status` 还会重新散列每个 client 产物，并在当前项目含 Relay 源码时比较各 client 的 source commit；落后返回 `installation_stale` 重装提示。相关源码存在未提交改动时返回 `dirty_unverifiable` 并让 `load` / `done` 携带 `installation_source_dirty`，因为此时最新 commit 不能代表待安装规则；仓库不可用则降级为 `unavailable`。

安装或更新的源码版本验收应显式执行 `relay --repo "<TOOL_SOURCE_DIR>" status`，其中 `<TOOL_SOURCE_DIR>` 是安装来源工具仓的本地 Git checkout，公开用户使用自己的 `silvers-tools-open`，不需要访问维护者私仓。`--repo` 是全局参数，必须放在 `status` 前；省略时使用当前工作目录。比较对象是该 checkout 内 Relay 相关路径的本地提交，不自动查询远端最新版；先确认 checkout 已包含目标版本。普通业务项目通常不含 Relay 源码，此时 `unavailable` 表示不能核对工具源码版本，不是已安装版本最新的证明。安装文件哈希核验与来源版本核对是两项独立证据。

稳定 launcher 模板位于 [`launcher/relay_launcher.py`](launcher/relay_launcher.py)。它只依赖 Python 标准库，只读取固定 pointer schema 的 `current.json`，执行目标 runtime 并透传参数和退出码。它不读取 remote、config、store 或安装回执，也不实现 Relay runtime 版本判断、业务/数据 schema、更新或回滚。

源码目录中的 `bin/relay` 是依赖 Bash 与 `python3` 的辅助脚本，适用于 POSIX 环境，或已具备这些命令的 Windows Git Bash。Windows 原生 PowerShell / CMD 应使用平台安装手册生成的 venv 入口和稳定 launcher；不能直接把这份 Bash 脚本当作 Windows 命令安装。

## 安装方式

本目录是 CLI 源码和协议事实来源，不是一条可跨机器照抄的通用安装命令。安装模型必须从 [`../../command/relay/README.md`](../../command/relay/README.md) 开始，完整阅读当前平台手册、三份语义模板和 [`../../skill/README.md`](../../skill/README.md) 下的 Relay **共享 Skill 参考源**，再根据当前 OS、Python、Git、客户端扩展机制和本机既有增量生成安装候选。语义模板与共享 Skill 均不得原样复制。

安装模型只处理当前客户端，不顺带修改其他客户端。创建远端、安装运行时或依赖、修改系统配置、改 SSH/Git 凭据配置仍需遵守当前环境的用户授权边界。

一次显式 Relay 入口调用授权的是该入口完整的 Relay CLI、独立 store 和请求草稿流程，不是逐条子命令授权。客户端适配器必须先使用已生效权限，禁止为 `--help`、只读 `status` 或每个动态参数预先申请升级；真实拒绝时只请求一次有界的 Relay 权限配置。Codex 的 writable root 与 execpolicy 适配见 [`../../command/relay/install/codex-permissions.md`](../../command/relay/install/codex-permissions.md)。

客户端入口必须先在临时目录生成候选、逐文件 diff、展示对账矩阵并等待用户明确确认。任何 `cp -f`、`--force` 或等价覆盖都被禁止。更新和重装的完整边界见 [`../../command/relay/UPGRADE.md`](../../command/relay/UPGRADE.md)。

## 一次性远端配置

**生产操作必须配置独立 remote**：

```text
relay setup --remote <用户确认的独立 Relay Git remote>
```

安装模型必须取得用户明确确认的 remote，不得猜测、创建或复用业务项目远端。remote 不能携带 PAT、密码、signed query 或 fragment；HTTPS 凭据交给 credential helper，或使用 SSH。remote 是安装时的一次性输入，日常三个用户入口仍然零参数。

## CLI API

用户只调用交棒、接棒、收棒三件套。下列是适配器使用的内部接口：

写入参数 `--client` 使用用户确认的稳定作者身份；`--model` 使用当前客户端提供的**实际模型稳定 ID**，不是带空格的显示名。两者的字符与长度约束见[统一安装说明](../../command/relay/README.md)；不能凭空编造模型 ID，也不能通过删空格或截断显示名冒充已核实的 ID。

| CLI | 作用 |
|---|---|
| `relay --version` | 无需 home、remote 或业务项目，输出当前 CLI 版本 |
| `relay setup --remote URL` | 一次性验证并保存独立远端 |
| `relay status` | 只读查看 home、配置、store 和安装回执摘要 |
| `relay draft create --operation create` | 创建唯一、私有的根棒请求草稿 |
| `relay draft create --operation update --relay-id ID` | 从当前 active 棒生成同阶段更新草稿，自动写入 target id/revision |
| `relay draft create --operation successor --relay-id ID` | 从当前棒生成 successor 变化量草稿，自动写入 target id/revision |
| `relay draft create --operation done\|withdraw --relay-id ID` | 从当前 active 棒生成收棒或撤销草稿 |
| `relay draft cleanup --path FILE` | 只清理 Relay work 根目录中的合法草稿 |
| `relay validate --request FILE` | 对 create/update/successor/done/withdraw 走与 apply 相同的 materialize 和语义校验，但不写入 |
| `relay pass --request FILE --client C --model M` | 按 request envelope 的 operation/target 创建根棒或 CAS 更新当前棒 |
| `relay successor --request FILE --client C --model M` | 按 request envelope 的 target，一个 CAS 归档旧阶段并创建 successor |
| `relay list` | 列出当前项目 active 棒 |
| `relay load --relay-id ID` | 返回行动卡、当前快照、source relation 和结构化 delta |
| `relay history` | 一次返回全部 done 阶段大纲，不分页 |
| `relay recall --relay-id ID --revision N --decision-id D-NNN` | 读取一个历史决策 |
| `relay recall --relay-id ID --revision N --criteria-ordinal N` | 按本 revision ordinal 读取当前格式的历史判据变更 |
| `relay recall --relay-id ID --revision N --criteria-id C-NNN` | 只兼容旧档案里的历史判据 ID |
| `relay migrate` | 原子迁移当前项目全部 tip；幂等，失败时恢复 HEAD、tracked bytes 与工作树 |
| `relay done --request FILE --client C --model M` | 按 request envelope 的 target 验证阶段完成并成对归档 |
| `relay withdraw --request FILE` | 按 request envelope 的 target/reason 撤销错误创建的 active 棒，不计为完成阶段 |

`history` 和 `recall` 由接棒入口按需调用，不要求用户记忆参数。所有业务结果输出单行 JSON。写入后的远端同步失败使用 `sync_error`；`details.local_committed=true` 表示本地 revision 已推进，details 给出恢复所需的 id、revision、status、Markdown path 和 canonical path。

查询已退出决策正文时，`recall --revision` 必须指定**仍包含该决策正文的历史 revision**。例如决策在第 N 版被 `retire` 或 `supersede` 移除，应查仍含正文的 N−1 版；直接查退出发生的 N 版会报告该版不包含此决策，CLI 不会自动回溯其他版本。判据变更回执则查询变更发生的 revision 和该版 `criteria-ordinal`，两者不要混用。

当前格式的 Markdown 将判据回执序号显示为 `C-001`、`C-002` 等。例如所查 revision 中的 `C-001` 对应 `--criteria-ordinal 1`，这个显示标签不是旧档案的 `criteria-id`；不能据此改用 `--criteria-id C-001`。旧档案的 ID 必须以该档案真实保存的值为准。

同一阶段内，`phase.outcome`、`phase.done_when`、`design.invariants` 和 `design.non_goals` 是受保护判据。CLI 只把**逐字完全一致**的条目视为保留；在旧文本后追加“废弃”“不适用”或例外同样是改写。任何旧文本替换都必须通过 request 的 `changes.criteria` 显式登记：真正收紧阶段交付、完成标准或不变量时用 `strengthened`，精确记录旧文本、replacement、原因并令 `authorized_by` 为 null；`removed`、`weakened`、`merged_into` 必须记录用户明确授权。任何新增列表项都必须用 `added` 登记；新增正向完成标准或不变量不要求用户授权，**新增 `design.non_goals`** 会缩小范围，必须带用户明确授权。对 non-goal 使用 `strengthened`、静默改写或静默新增都会被拒绝并返回 `criteria_transition_required`。

跨阶段只能走独立的 `successor` 操作，不能靠改 `phase.name` 触发。旧阶段先按原判据完成并冻结；`completion.snapshot.phase.done_when_status` 必须逐条显式声明，缺项或仍为 `pending` 时 fail closed。新阶段的 outcome/done_when 是全新契约，不算删除旧判据；CLI 将其状态初始化为 `pending`。整体 `design.invariants` / `design.non_goals` 则逐字继承，显式改变它们仍走上述 G1 校验。CLI 自动生成的前阶段收尾摘要包含旧阶段 outcome、声明来源、每条 done_when 的真实状态、证据计数和 done 档案指针。schema 4 及更早记录没有逐条声明，其旧 `met` 只按 `legacy_inferred/unknown` 暴露，不继续传播成真值。

每条通过的 `changes.criteria` 都以完整 action、原文、replacement、reason 与 authorized_by 写入当前 revision 的 `criteria_changes`，并由 CLI 分配本 revision 内从 1 开始的 `ordinal`。下一 revision 只保留自己的新回执，旧详情继续存在于对应 Git revision；当前格式用 `--criteria-ordinal` 取回，`--criteria-id` 只兼容旧档案。`load` 的 `delta.criteria_changes` 会直接报告当前 revision 的完整判据变化。`strengthened` 的语义真实性无法由 CLI 自动证明，它仍是写入方声明；持久回执、delta 和 recall 让下游能够发现、审计和追责错误声明。

## 跨机器 schema 漂移

格式合法但当前 CLI 不支持的 `config_schema`、`relay_store_schema`、canonical `relay_schema` 或 `render_version` 统一返回 `schema_unsupported`。`details` 包含当前 CLI 版本、当前支持值、实际遇到值和“更新本机 Relay、不要手工改写数据”的建议动作。

canonical reader 接受精确的 schema/render 2/2、3/3、4/4、5/5 与 6/6 组合，新写入固定为 6/6；其他混搭组合视为损坏。无效 JSON、字段缺失、类型错误或同 schema 的内容损坏仍返回原有格式/`store_error`，不会被误报为版本问题。旧 CLI 不知道未来应该安装哪个具体版本，因此错误不会伪造目标版本号。

## source relation

`load` 从权威 canonical JSON 现渲染 Markdown，并返回结构化 delta、`phase_completion`、前阶段收尾摘要，以及 `snapshot.decisions` 中的**全部活动决策全文**。`phase_completion.alignment_complete=true` 证明本阶段判据与状态逐条对齐；旧 schema 缺少声明时只返回 `unknown` 和兼容警告。`active_decisions_complete=true` 才能交给接棒方；完整响应超过 128 KiB 时 fail closed。相同的精确体积检查在 active 写入前执行，不能在接棒后静默截断或要求接棒方猜该 recall 哪条活动决策。响应超过 48 KiB 软预算时只附带统一的 `budget_advice`，指出最厚的顶层内容字段但不拒绝写入；磁盘 Markdown 漂移则写入非阻断的 `document_export` 诊断。

它同时返回：

- `exact`：交棒与接棒均为相同 clean HEAD；
- `dirty_unverifiable`：HEAD 相同但任一工作区 dirty，无法证明未提交内容一致；
- `changed`：当前 HEAD 与交棒 source HEAD 不同。

只有 `exact` 可以直接采用行动卡的第一步。`dirty_unverifiable` 额外返回结构化 `source_verification.checklist`，要求核对 status、diff、相关路径和实跑测试；其他状态也应先核对真实代码差异。

## 许可证

本工具统一采用[仓库根目录的 MIT 许可证](../../../LICENSE)，工具目录不维护单独副本。源码构建时，`setup.py` 临时读取根许可证并带入源码分发包和 wheel，构建结束即清理工具目录中的临时副本；构建失败时也清理。源码分发包携带同一份许可证，脱离仓库重建 wheel 时直接使用包内文件。缺少根许可证或分发包内许可证时停止构建，不能生成缺少许可文件的安装包。包元数据声明 `MIT`，独立分发时应保留许可信息；构建前按 `pyproject.toml` 核对 `setuptools>=77`。

`relay status` 的源码陈旧度核对覆盖运行时代码、包配置（含 `setup.py`）、launcher 和客户端适配器规则，不覆盖仓库根 `LICENSE`。仅修改许可证不会触发这项陈旧度提示；发布或独立打包时须检查源码分发包和 wheel 中的许可内容与根许可证一致，不能用 `status` 代替许可证验收。

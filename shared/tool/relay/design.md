# Relay 0.9.1 / schema 6 协议

本文是 Relay 行为的事实来源。客户端命令和 Skill 只编排语义，不得重新实现 revision、阶段继承、决策生命周期、大小、安全、草稿或 Git 规则。

## 目标与状态流

Relay 保存的是一根**阶段级接力棒的当前真相**，不是会话备份：

```text
不存在 ── pass ──> active r1
active rN ── pass(expected N) ──> active rN+1
active rN ── load ──> 行动卡 + 当前快照 + 结构化 delta
active rN ── done(expected N) ──> done rN+1
active rN ── successor(expected N) ──> done rN+1 + 新 active r1
```

只支持单写者顺序接力。并行会话可以读取，但任何旧 revision 写入都必须以 `stale_revision` 失败。产品未完成不妨碍阶段收棒；`done` 表示这根棒声明的阶段交付已经满足，而不是整个产品必然结束。

Relay 的典型用法是由用户按阶段把工作分配给不同模型，以利用模型能力、成本或个人偏好。**用户拥有唯一交棒决定权，阶段边界也由用户定义**：用户决定是否交棒、何时交棒以及下一模型；Relay 不判断阶段是否“足够大”。用户显式要求交棒时，模型不得以阶段大小、完成度或效率判断拒绝、推迟或反问。Relay 只持久化接力棒，不选择、调用或通知下一模型。

内部批次、单次测试检查点、普通代码审查或临时执行停顿不是模型自动交棒或建立 successor 的依据；但用户明确选择在任何一个节点交棒时必须照办。当前阶段尚未完成时更新同一 active Relay，让下一模型直接 load；用户已经定义下一阶段时，由一个 successor 事务同时完成旧阶段归档与新阶段创建。单独 `done` 只用于当前没有 successor 的收棒。

`next_step.done_when` 只定义第一步完成；它不等于 `phase.done_when`，也不是模型自行设定的阶段停点。接棒理解确认后，用户未要求换模型时，模型应持续推进整根棒，只有阶段完成、真实阻塞或权限升级才可自行停止。用户可随时明确要求中途换模型；交棒不得要求用户复制粘贴审查文本，也不得自动调用模型或外部服务。

CLI 只客观校验字段、生命周期和证据结构，不以最小时长、最少步骤或主观评分判定阶段粒度。用户路由权、持续执行和禁止模型自行制造审查乒乓，属于客户端命令与 Skill 必须执行的语义约束。

## 独立运行时与持久化结构

`SILVERS_RELAY_HOME` 是最高优先级覆盖。否则 macOS/Linux 使用 `~/.silvers/relay`，Windows 使用 `%LOCALAPPDATA%\Silvers\Relay`；Windows 环境变量缺失时回退到用户目录下的 `AppData\Local\Silvers\Relay`。

```text
<relay-home>/
├── bin/
│   ├── relay                    # 平台稳定入口
│   └── relay_launcher.py        # 冻结 launcher
├── runtimes/<version>/
│   ├── venv/
│   └── runtime.json
├── current.json
├── install.json
├── config.json
├── .store.relay.lock
├── store/
│   ├── .silvers-relay-store.json
│   ├── active/<project_key>/<relay_id>.json
│   ├── active/<project_key>/<relay_id>.md
│   ├── done/<project_key>/<relay_id>.json
│   ├── done/<project_key>/<relay_id>.md
│   ├── withdrawn/<project_key>/<relay_id>.json
│   └── withdrawn/<project_key>/<relay_id>.md
└── work/
    └── relay-request-<random>.json
```

代码层 `bin/`、`runtimes/`、`current.json`、`install.json` 与数据层 `config.json`、`store/`、`work/` 平级隔离。更新 runtime 不得移动、重建或清空数据层。新版本必须排他创建全新的 `runtimes/<version>/`，直接在最终路径构建 venv，避免搬家后绝对 shebang 或 launcher 失效。runtime receipt 写成前目录只是未完成安装，不能切换 current；receipt 写成后不可原地覆盖。最后以原子替换 `current.json` 切换活动版本。

launcher 只读取 `current.json`，确认 entrypoint 是 `runtimes/` 下的普通非符号链接文件，然后转发参数和退出码。launcher 不读取 config、install receipt、remote、store 或业务项目，不包含 Relay runtime 版本、业务/数据 schema、更新、回滚与命令逻辑。`current.json` 的 pointer schema 1 格式随 launcher 冻结，只包含 `current_schema` 与 POSIX 相对 entrypoint。

`runtimes/<version>/runtime.json` 记录 runtime schema、Relay 版本、完整 source commit、相对 entrypoint、UTC 安装时间和 Python 版本。`install.json` 记录本机 Relay home、launcher 文件及 SHA-256、当前 runtime、source commit、安装时间，以及每个已确认客户端入口自己的 source commit、绝对路径与 SHA-256。`relay status` 只读校验三份 JSON 的结构、路径和交叉引用，重新散列 client 文件，并在业务项目包含 Relay 源码时比较相关路径的最新 commit。相关路径存在未提交改动时，顶层和各 client 的 source status 为 `dirty_unverifiable`，同时保留基于 commit 的 `commit_relation`；`load` / `done` 返回 `installation_source_dirty`。仓库不可用降级为 unavailable，不影响基本状态读取。

安装与更新验收使用 `relay --repo "<TOOL_SOURCE_DIR>" status`，显式指向安装来源工具仓的本地 Git checkout；公开用户使用自己的 `silvers-tools-open`。`--repo` 必须位于子命令前，省略时取当前目录。版本核对仅比较该 checkout 的本地提交，不自动获取远端；普通业务项目中返回的 `unavailable` 不构成源码版本已对齐的证据。

三份 JSON 都是固定字段、UTF-8、同目录临时文件原子替换。runtime receipt 的精确形状为：

```json
{
  "runtime_schema": 1,
  "relay_version": "<version>",
  "source_commit": "<完整小写 Git commit id>",
  "entrypoint": "venv/bin/relay",
  "installed_at": "<UTC ISO 8601 Z 时间>",
  "python_version": "<major.minor.patch>"
}
```

Windows 的 runtime entrypoint 通常是 `venv/Scripts/relay.exe`。本机安装回执的精确形状为：

```json
{
  "install_schema": 1,
  "relay_home": "<本机绝对路径>",
  "launcher_files": [
    {
      "path": "bin/relay_launcher.py",
      "sha256": "<64 位小写 SHA-256>"
    }
  ],
  "current_runtime": "<version>",
  "source_commit": "<与 runtime 相同的完整 commit>",
  "installed_at": "<UTC ISO 8601 Z 时间>",
  "clients": [
    {
      "client": "<当前客户端标识>",
      "adapter_protocol": 2,
      "source_commit": "<生成该客户端适配器所依据的完整 commit>",
      "files": [
        {
          "path": "<客户端入口绝对路径>",
          "sha256": "<64 位小写 SHA-256>"
        }
      ]
    }
  ]
}
```

`launcher_files` 必须记录所有实际参与稳定调用的文件；`clients` 在用户尚未确认客户端候选时可以为空。早期回执若缺少 client 级 source commit，读取时退回全局 source commit 并标记 `legacy_install`，下次人工更新适配器时补齐。JSON 不允许协议外字段，remote 和任何凭据都不得写入安装回执。

`current.json` 与 `install.json` 各自可以原子替换，但两个文件不能组成一个文件系统事务。更新时必须预先生成并交叉校验两份候选，在一个短临界步骤内连续替换，中间不运行 Relay。若进程在两次替换之间崩溃，`relay status` 会因 current/install 不一致而 fail closed；恢复时同样连续还原两份旧文件，不能只改其中一个。

每根棒只有两个正式文件：

- canonical JSON 是唯一权威真相；
- Markdown 是派生导出物，由 CLI 从 canonical JSON 确定性生成，方便人直接阅读 Git 和 `done/`。

写操作仍在同一把锁、同一次 CAS、同一个 Git commit 和同一份回滚 snapshots 中创建、更新或移动 JSON/Markdown。读操作只要求 canonical JSON 存在且合法：Markdown 缺失、手工修改、前言损坏或过大时，`load` 从 canonical 现渲染并返回非阻断的 `document_export` 诊断。没有 canonical JSON 的孤立 Markdown 仍是 `store_error`。Git commit 对远端可见性是原子的；若进程在本地写入中崩溃，store 会保持 dirty，下一次命令必须停止，不得猜测修复。

store 顶层只允许 marker、`active/`、`done/` 和 `withdrawn/`；三座状态树只允许 `<project_key>/<relay_id>.json|.md`，且 Markdown 不能脱离同名 canonical JSON 单独存在。`withdrawn/` 保存错误创建棒的原内容、撤销时间和原因，不进入完成 history，也不能作为 predecessor。结构化 delta、history、recall、活动决策、timeline 和 changelog 都不是额外文件。

## 请求、canonical record 与当前真相

模型写入 `work/` 的临时 request envelope；CLI 按 `operation` 的单一 spec 生成草稿、校验字段并 materialize 成内部请求。`target.relay_id` 与 `target.expected_revision` 由 contextual draft 自动带出，不再作为写命令参数。`payload.snapshot` 是完整当前快照；`payload.changes.active_decision_ids` 确认活动决策全集，`payload.changes.decisions` 表达 retire/supersede，`payload.changes.criteria` 表达 G1 判据变更。changes 是瞬时输入，不进入持久化 snapshot。

canonical record 固定包含：

```text
relay_schema
render_version
metadata
lineage
snapshot
decision_id_high_watermark
criteria_changes
```

schema/render 6/6 的 `metadata`、稳定 `phase_id`、lineage 的 predecessor revision/收尾摘要、决策 ID 水位线和本 revision 判据回执由 CLI 管理。`phase_id` 固定等于承载当前阶段的 relay id，不进入模型请求，也不因 `phase.name` 改写而变化。`snapshot` 保存固定业务字段：标题、当前状态、阶段契约及逐条完成状态、整体设计契约、全部活动决策全文、权限与歧义、状态与证据、第一步、剩余优先级、偏差和引用。reader 仍接受精确的 2/2、3/3、4/4 与 5/5 文件对；`relay migrate` 将当前项目全部 tip 原子转换为当前结构。**migrate 只改当前文件，Git 历史里的旧 revision 不可能被迁移，仍由当前 runtime 的旧结构读取与渲染路径承担**。详见「历史兼容边界」。

没有 append、timeline、changelog 或“本轮新增”字段。更新时必须重写当前快照；已经失效的计划、重复验证、完整命令输出、聊天原话和旧状态留在 Git 历史，不留在热层。commit message 只供人诊断，不承担语义大纲；结构化历史来自 canonical JSON。

## 阶段契约与可执行入口

每根棒必须显式声明：

- 整体用户结果；
- 当前阶段名称；
- 当前阶段交付 `phase.outcome`；
- 当前阶段完成标准 `phase.done_when`；
- 与完成标准逐条对齐的 `phase.done_when_status`；
- 明确非目标和不变量；
- 接棒后的第一步；
- 当前阶段的 predecessor。

第一步必须包含目的、项目相对工作目录、前置条件、带用途的必读路径、跨环境命令提示、预期结果、单步完成标准和失败分支。`read` 至少一项，纯只读任务允许 `modify=[]`，禁止为满足 schema 伪造“不得修改”的修改入口。持久化路径统一使用 `/` 的项目相对路径，禁止绝对路径、Windows drive、反斜杠和 `..`。

`phase.done_when_status` 与 `phase.done_when` 使用位置一一对应，状态只能是 `pending|met|partial|unverifiable`。`partial` 与 `unverifiable` 必须带单行原因；`pending` 与 `met` 的原因必须为空。active 棒持续保存这些状态，接棒方不必从 `completed` 自行猜测。done 与 successor completion 要求写入方重新逐条声明且不得残留 `pending`；CLI 允许带原因的 `partial/unverifiable` 被如实归档，不会替写入方硬编码 `met`。

`command_hint` 只是当前环境的启动提示，不能替代语义步骤。接棒方应先按行动卡确认：

```text
最终用户结果 → 本阶段交付 → 当前状态/约束 → 第一动作 → 阶段完成标准
```

项目 HEAD 与 source HEAD 不同返回 `source_relation=changed`；HEAD 相同但交棒方或接棒方工作区 dirty 时返回 `dirty_unverifiable`；只有相同 clean HEAD 返回 `exact`。非 `exact` 时不能盲跑旧命令，第一步先核对真实磁盘差异。

阶段交付、阶段完成标准、不变量与非目标是信任根。同一阶段的 update/done 中，CLI 只承认条目**逐字完全一致**；前缀相同但追加废弃、不适用、例外或其他后缀仍是替换。所有替换和新增都必须登记到 request 的 `changes.criteria`。真正收紧 `phase.outcome`、`phase.done_when` 或 `design.invariants` 时用 `strengthened`，记录精确旧文本、精确 replacement、原因和 `authorized_by: null`；删除、弱化、合并使用 `removed|weakened|merged_into` 并要求非空用户授权。列表新增使用 `added`：新增正向完成标准或不变量允许 `authorized_by: null`，新增 `design.non_goals` 会缩小范围，必须有用户明确授权；单值 `phase.outcome` 不能使用 `added`，non-goal 不能使用 `strengthened`。CLI 验证所有 transition 必须对应真实的旧文本退出、新条目或 replacement。`strengthened` 的语义真实性无法由 CLI 自动证明，授权来源真实性也不能由字符串校验保证；适配器不得用错误 action 绕过用户决定，下游必须借助持久回执审计。

## 阶段契约与棒内角色边界

`design.non_goals` 是**阶段级**契约：整个阶段都不做的事，受 G1 保护并跨阶段逐字继承。
`authority.must_not` 是**棒级**边界：接过这一棒的人不能做的事，主语始终是接棒方自己。

两者必须分清。「这一棒只审计、不改代码」属于 `must_not`，不属于 `non_goals` —— 它约束的是当前持棒方，不是这个阶段。写错位置的代价不对称：写进 `must_not` 下一棒直接重写，写进 `non_goals` 会被 G1 锁死，交回原作者修复时反而要走删除授权，或者被逼开一个本不该开的新阶段。

因此 `must_not` 不受 G1 保护，也**不跨阶段继承**：successor 一律把它清空，由交棒方为新棒重新声明。同阶段更新本就整份重写，每次交棒都是一次重新声明。schema 6 之前的记录没有这个字段，读取时按旧渲染器逐字读出，下次正常写入时补为空列表。

## 开启下一阶段需要用户授权

`successor` 请求必须带非空 `authorization`，逐字记录用户授权开启下一阶段的原话，CLI 拒绝空值和模板占位文本，上限 1 KiB。它随新阶段 lineage 落盘为 `phase_authorization`，并渲染在接棒入口。

开不开新阶段是用户的决定：**模型可以建议，但不得自行判断**。用户没有明确同意时只能用 `pass` 更新同一根棒。CLI 无法证明这段话真的出自用户，这道门禁提供的是强制留痕，把"顺手开个新阶段"变成一次必须显式伪造的动作；真实性由持久登记供事后审计。

根棒的 `phase_authorization` 为 null。有 predecessor 但字段缺失的记录来自 schema 6 之前，渲染时必须与根棒区分，不能把推进出来的棒显示成根棒。

跨阶段不通过字段比较推断，而只能由独立 `successor` 操作表达；CAS target 位于 request envelope。事务先按旧阶段原判据运行完整完成门，再把新阶段 outcome/done_when 当作全新契约，因此不要求“删除旧判据”的授权。整体 `design.invariants` / `design.non_goals` 必须逐字继承；successor 若显式改变它们，仍按 G1 登记和授权。这样改 `phase.name` 不能绕过 G1，未完成不能刷新判据，换阶段不能删除整体不变量。

`dirty_unverifiable` 还返回 CLI 固定生成的 `source_verification.checklist`，至少覆盖 status、完整 diff/未跟踪内容、Relay 引用路径和关键测试实跑。它不自动修改工作树，也不把人工核对结果写入 Relay。

## 活动决策全集与水位线

当前 canonical 的 `snapshot.decisions` 始终携带全部活动决策全文。模型无需回抄继承决策的全文，但必须在 `changes.active_decision_ids` 中精确确认本轮结束时仍活动的全部 ID；少列、多列、重复或引用不存在的 ID 都会被拒绝并点名差异。

规则如下：

- 新增或原地收敛的决策全文写入 `snapshot.decisions`；
- 退出必须显式提交 `changes.decisions`：
  - `retire`：填写原因且 replacement 为 null；
  - `supersede`：填写原因和仍然活动的新 ID；
- 未知、已退出或重复使用的 ID 拒绝；
- `locked` 决策的 status、label、decision、reason、rejected、reopen_when 不能静默改写，必须用新 ID 和 `supersede` 显式替代；
- canonical 的 `decision_id_high_watermark` 防止退出后的 ID 被复用，使正文里不带 revision 的 `D-NNN` 引用不会改指。

successor 事务从当前 active 棒生成同项目 done predecessor并固化 predecessor revision。交棒方只提交旧阶段最终状态和逐条完成声明、新阶段 outcome/done_when、第一步与明确变化；CLI 逐字继承整体 design、authority、remaining、references 和活动决策，并把新阶段状态初始化为 `pending`。`authority.must_not` 是唯一例外：它绑定当前持棒方而非阶段，跨阶段一律清空由交棒方重写。活动棒更新或收棒时不得改变既有 predecessor。

## 本 revision 判据变更回执

- request 的 `changes.criteria` 保存本次 action、原文、replacement、reason 和 authorized_by；
- 通过校验后，canonical 的 `criteria_changes` 保存同样的完整回执，并由 CLI 分配本 revision 内从 1 开始的 `ordinal`；
- 下一 revision 的 `criteria_changes` 只记录本轮变化，旧回执由对应 Git revision 保留，不维护累计 registry 或全局递增 ID；
- `load` 的 `delta.criteria_changes` 直接返回当前 revision 的完整回执；
- 当前格式用 `relay recall --relay-id ID --revision N --criteria-ordinal N` 取回，`--criteria-id` 只兼容旧档案；
- successor 不把前序阶段的回执复制到新阶段，done 文件与 Git revision 继续保存原记录。

这套回执不能阻止提交方把弱化谎报成 `strengthened`，但能让该声明、理由和授权永久可定位，不再静默消失。

## 有界加载、结构化 delta、history 与 recall

默认 `load` 返回当前热层、本阶段逐条完成状态、CLI 自动生成的前阶段收尾摘要，以及全部活动决策全文，不自动加载无关历史：

- request JSON 最大 96 KiB；
- canonical JSON、派生 Markdown、完整 CLI `load`、`history` 和单项 `recall` 共用 128 KiB 总硬上限；
- 完整 `load` 超过 48 KiB 时只返回统一的 `budget_advice`，提示最厚的顶层内容字段，不拒绝写入。

写入前按最终 canonical、现渲染 Markdown 和完整 load 响应做精确序列化计数；任一项超过总硬上限就在写文件、bump revision 和 commit 前拒绝，因此不存在“写得进、后来 load 不出”的死区。安装诊断单独受 `MAX_INSTALLATION_WARNING_BYTES` 约束并在出口截断，不占接力棒写入额度，也不能让已写入的棒因为源码转 dirty 而突然无法 load。

delta 比较同一 canonical JSON 路径的前后两个 revision，而不是盲用 `HEAD~1`。它完整报告 changed paths、决策新增/更新/退出、本 revision 的 `criteria_changes` 和 source baseline 变化，不依赖模型摘要或 commit message，也不截断或分页。

`load` 直接从 canonical 的 `snapshot.decisions` 返回 `active_decisions`、`active_decision_count` 与 `active_decisions_complete=true`。派生 Markdown 同样渲染全部活动决策四要素全文（决策 / 理由 / 否决方案 / 重议条件）。`phase_completion` 以 index/status/reason 返回本阶段状态，并用 count 与 `alignment_complete=true` 证明逐条对齐。磁盘 Markdown 漂移不改变这些真相，只通过 `document_export` 报告并采用 canonical 现渲染内容。

`relay history` 扫描 `done/` 的 canonical metadata，按 Git commit 顺序一次返回全部阶段名称、阶段交付、前序关系和完成信息，不加载阶段正文、不分页。

`relay recall` 一次读取指定 relay/revision 下的一个已退出 decision ID 或判据回执，不分页。 查询已退出决策正文时，必须选择仍包含正文的历史 revision；例如在第 N 版退出，就查询仍含正文的 N−1 版。退出发生的 N 版已没有该决策正文，CLI 不会自动回溯。判据回执则查询其变更发生的 revision 与该版 ordinal。当前格式的判据回执按 `--criteria-ordinal` 定位，`--criteria-id` 只兼容旧档案。活动决策已经由 load 摊平，接棒方不得为理解活动决策逐条 recall；recall 只服务退出决策和判据审计历史。

`done/` 是阶段档案层，Git 是 revision 历史层，当前 active record 是热层。successor 只在当前 lineage 中额外保存一条结构化前阶段收尾摘要：旧 outcome、逐条 done_when 达成状态、状态来源、evidence 计数与 done relay/revision 指针；不复制历史正文，也不无限累计。schema 4 的摘要中 `met` 来自旧 CLI 推定，不是写入方声明；v5 load 将其标准化为 `status_source=legacy_inferred`、逐条 `unknown` 并附兼容说明，旧文件本身保持字节级不变。

## 大小与安全

- request JSON：最大 96 KiB，必须是 UTF-8 普通文件；
- canonical JSON、派生 Markdown 与完整 load/history/recall 响应：各自最大 128 KiB；
- 单个通用文本字段最大 32 KiB；阶段授权原话最大 1 KiB；
- 超限时整次拒绝，不写正式文件、不 bump revision、不 commit；
- `SOFT_LOAD_BYTES = 48 KiB` 只提示不拒绝，且必须严格低于 128 KiB 总硬上限；
- 收到 `budget_advice` 后只精炼流水账、时间线、重复结论、日志与源码转储；决策四要素、逐条完成状态和仍有效约束不得删除。仍超软预算时说明原因后继续，不额外询问用户。

私钥、常见云厂商 token、API key、密码和 Cookie 模式拒绝；request、canonical record 和 CLI 生成的项目 metadata 都必须扫描。正则扫描不是任意内部裸凭据的密码学兜底，模型仍必须用 `<REDACTED>` 代替真实值并记录重新获取位置；完整聊天、完整 diff、大段源码和真实凭据禁止进入 Relay。

remote 禁止 URL userinfo、query 和 fragment，凭据交给 credential helper 或 SSH。业务 origin 写入 metadata 前同样去除敏感组成。

## 完成门与理解确认

Markdown 固定八节：

1. 接棒入口：阶段概要后先显示一句话状态与第一步，再显示本阶段逐条完成状态和前阶段摘要
2. 设计契约
3. 活动决策全文与本 revision 判据变更回执
4. 权限与歧义
5. 当前状态与证据
6. 剩余任务
7. 偏差与阻塞
8. 引用

load 后的模型必须先读一句话状态和第一步，再复述用户结果、阶段交付、阶段完成标准及逐条状态、非目标、不变量、活动决策、未知项和 source relation。用户确认前当前业务项目只读；标题和未标状态的判据措辞不能覆盖明确的 current summary/next step。

done 要求 P0 为空、偏差为空、`completed` 和 `evidence` 均非空、`in_progress` 为空，且 `phase.done_when_status` 数量完全对齐、没有 `pending`。`partial/unverifiable` 必须保留原因，CLI 不把它们改写成 `met`。P1/P2 可以属于后续阶段；它们不得伪装为已完成的本阶段 P0。

## Git、CAS 与失败语义

- store 操作前有任何 tracked、untracked 或 ignored 内容时停止；不得自动删除、stash 或 reset；
- 同一 store 的线程锁和跨进程文件锁覆盖 prepare、CAS、双文件替换、commit 和 push；
- 只 stage 当前 `.json/.md` 文件对；done 精确 stage active 两文件删除和 done 两文件创建；
- successor 在同一 CAS/commit 中精确 stage 旧 active 两文件删除、旧 done 两文件创建和新 active 两文件创建；
- withdraw 精确 stage active 两文件删除和 `withdrawn/` 两文件创建，要求 CAS 与非空原因；撤销棒不进入 history 或 predecessor 查找；
- 内部 commit 使用空 hooks 目录、`--no-verify` 和 `commit.gpgsign=false`；
- commit 后核对实际变更路径、marker、完整文件对和 clean 状态；
- 只允许 fast-forward，禁止 merge、rebase 和 force push；
- commit 前失败同时恢复 JSON 与 Markdown；
- push 失败保留本地 commit，返回 `sync_error`、`local_committed=true` 以及新的 id/revision/status/两条路径；
- 下一次操作先补推，旧 revision 不得重试。

Relay home/store 与业务项目任一方向重叠时，在创建锁或目录前拒绝。Relay remote 与业务 origin 任一 fetch/push 身份相同也拒绝。Relay 命令授权只覆盖 Relay home 和独立 store，不覆盖业务项目修改、commit 或 push。

一次显式 Relay 入口调用在客户端权限层视为该入口完整的 Relay CLI、独立 store 与请求草稿流程，不得拆成逐子命令或逐草稿授权。适配器先使用当前已生效权限；`--help`、只读 `status` 和动态 relay id/revision/path 不是预先升级理由。宿主实际拒绝必要操作时，只请求一次覆盖稳定 launcher、Relay work 目录和已配置 remote 的有界权限；full-access/no-approval 环境必须省略升级审批元数据。该流程授权仍不包含 `setup`、业务项目修改、commit/push 或其他客户端配置。

## 自主安装边界

共享仓库保存 CLI 协议、模型无关语义模板和平台参考手册，不保存一份假定所有机器相同的成品客户端命令。安装模型必须完整阅读协议，探测当前 OS、shell、Python、Git 与客户端原生扩展机制，只安装当前客户端需要的三个显式入口。

安装必须取得用户确认的独立 remote；不得猜测、创建、复用业务 origin 或修改凭据配置。remote 是一次性安装输入，日常入口零用户参数。`history` 和 `recall` 是接棒入口内部使用的 CLI 能力，不要求用户记参数。安装验证使用临时 home 与临时 bare remote，不向真实 remote 写 fixture。

客户端入口强制人工确认：安装或更新模型必须在临时位置生成候选，逐文件读取本机规则和旧内容，提供 diff 与对账矩阵，等待用户明确决定后手工叠加。禁止对 `~/.claude/commands/**`、`~/.claude/skills/**/SKILL.md` 或其他客户端同类目录做覆盖式写入。

本版提供 `relay migrate`，在同一事务中把当前项目的全部 tip 转成当前 canonical 结构；任一转换、commit 或 push 失败都会恢复原 HEAD、tracked bytes 和工作树，成功后重跑幂等。当前 runtime 自身负责受支持旧格式的历史读取。其他兼容性检查仍并入后续 `doctor`。


## 历史兼容边界（永久）

**旧结构的读取与渲染能力永久保留，不因 `migrate` 完成而可删。** 这条是不变量，不是待清理项。

`migrate` 只把**当前**文件转成新结构。Git 历史里的每个旧 revision 仍是写入时的结构，
而 Relay 的读路径会真实回到那些历史对象：

- `relay recall` 经 `_record_at_revision()` 用 `git show <commit>:<path>` 直接取历史 canonical，
  再按旧字段集解析；
- `list` / `history` / `load` 都进 `_validate_record_pair()`，它**无条件**调用 `render_record()`，
  于是旧 `render_version` 会命中对应的历史渲染分支；
- `_require_record_versions()` 的 `supported_pairs` 必须让每个历史版本对用**自己的固定常量**入表。
  写成随当前版本移动的那一项，下次升版本时该版本对会静默消失，对应档案当场变
  `schema_unsupported`。


因此下列代码属于历史兼容边界内，**删除即事故**：canonical reader 的旧字段集分支、
旧字段放宽校验、UTF-8 截断与判据 label 重算、旧决策 delta 兜底、跨 revision 决策指针解析、
旧完成状态的 `legacy_inferred`/`unknown` 归一，以及全部历史渲染分支。

历史兼容性验证应使用对应旧版本生成的固定样例，不得用当前实现重新生成的内容替代历史样例。本公开包不附带这些测试样例。


判断某段兼容代码能否删除，判据只有一个：**拿真实旧数据跑通全部读路径后仍不经过它**。
`src/` 里引用数为 0 不是证据 —— 那个零可能是重构时自己改调用点造成的。

## schema 不兼容失败语义

CLI 在读取 config、store marker、canonical record 和 render version 时，先区分“版本不受支持”与“同版本内容损坏”。canonical reader 接受精确的 2/2、3/3、4/4、5/5 和 6/6 schema/render 组合，新写入固定为 6/6。遇到其他合法 integer 但不受支持的 schema，返回 `schema_unsupported`，details 固定包含组件、当前 CLI 版本、支持 schema、实际 schema 与更新本机 Relay 的建议；已知版本的非法混搭返回 `store_error`。缺字段、错误类型、非法 JSON 和同 schema 未知字段继续使用格式或 `store_error`。

旧 CLI 无法知道未来版本号，建议动作不得声称升级到某个未经证实的版本。跨机器共享 store 时，未升级机器必须 fail closed，不能手改 marker 或 canonical JSON 伪造降级。

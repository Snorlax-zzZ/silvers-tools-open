# relay 语义模板

菜单注释：交棒：保存或更新当前任务，交给下一模型

本文件由安装模型转换为当前客户端的原生显式入口，不是客户端成品文件，严禁原样复制。用户不需要输入任何参数；内部请求路径、relay id、revision、`<WRITER_IDENTITY>` 和 model 由适配后的入口维护。安装模型必须把作者占位符替换为用户确认的稳定助手身份，不得用宿主客户端名自动代替。

写入参数 `--model <当前模型>` 使用当前客户端提供的实际模型稳定 ID，不使用带空格的显示名或猜测值；`--client` 使用已确认的稳定作者身份。两者的字符、长度与取值要求见[统一安装说明](../README.md)。

## 授权边界

显式调用只授权 Relay CLI 创建/清理请求草稿并对独立 Relay store 做限定 commit/push，不授权修改、提交或推送当前业务项目。

## 权限执行

显式调用把本入口所需的 Relay CLI、独立 store 与请求草稿操作视为一个完整授权流程；不得按 Relay 子命令或草稿文件逐步询问。先按宿主当前已生效权限执行，禁止预先申请升级权限；`--help` 和只读 `status` 不得成为主动升级理由。只有宿主返回实际权限拒绝时才停止重试，并请求一次有界的 Relay 权限配置，覆盖稳定 launcher、Relay work 目录和已配置 remote。处于 full access / no-approval 时必须省略全部升级审批元数据。该权限不扩大到业务项目。

## 执行语义

1. 检查稳定的 Relay CLI 入口并运行 `relay status`。CLI 不可用或 `configured=false` 时停止；日常入口不得安装、setup、创建远端或改用户配置。
2. 确定本会话是否拥有成功创建或经确认接棒取得的 `relay_id + expected revision`。没有可靠指针时可运行 `relay list`：零项允许新建；存在 active 时提供“新建阶段棒”或先接棒。不得仅凭 `relay list` 更新，也不得猜最新 revision。
3. **是否交棒、何时交棒、交给谁，均由用户决定；阶段边界也由用户定义。**用户显式调用交棒入口时必须执行；不得以阶段太小、尚未完成或效率判断为由拒绝、推迟或反问。Relay 只保存接力棒，不选择或调用下一模型；目标模型由用户在 Relay 之外选择。
4. 内部批次、测试检查点、普通代码审查或执行检查点不是模型自动交棒或新建阶段的理由；如果用户明确选择在这些节点交棒，必须照办。用户只要求中途换模型、未宣布新阶段时，更新同一 active Relay；模型不得自行制造微阶段、successor 或把审查工作甩给用户。
5. 根据用户表达区分两条内部路径，不根据 `phase.name` 猜测：同阶段换模型或补充当前真相，继续更新可靠指针指向的 active；用户已经定义下一阶段且当前阶段满足完整收棒门禁时，执行 successor 事务。**开不开新阶段由用户决定，不是模型能自行判断的事**：模型可以建议开新阶段，但用户没有明确同意时只有 `pass` 一条路。successor 请求必须带非空 `authorization`，逐字填写用户授权的原话；CLI 拒绝空值和模板占位文本，因此模型自己认定的新阶段根本写不进去。successor 直接使用本会话可靠的 active id/revision，用户不需要复制文本、选择 predecessor id 或补第二组参数。 successor 前先用可靠指针运行 `relay load --relay-id <内部 relay id>` 并核对 revision；若 warnings 含 `installation_stale` 或 `installation_source_dirty`，必须在归档旧阶段前停止并报告所需的适配器重装或源码核对，与独立收棒使用相同条件。
6. 根棒运行 `relay draft create --operation create`；同阶段运行 `relay draft create --operation update --relay-id <内部 relay id>`；跨阶段运行 `relay draft create --operation successor --relay-id <内部 relay id>`。contextual draft 会把可靠的 relay id、expected revision、当前快照和活动决策确认字段写入请求 envelope；只使用响应 `result.path`，并立即登记 finally 清理，适配器不得自行构造草稿路径或把目标参数留到写命令再补。
7. 同阶段更新时整份填写**当前真相快照**：
   - 整体用户结果、阶段交付 `phase.outcome`、阶段完成标准 `phase.done_when`，以及与其逐条对齐的 `phase.done_when_status`；
   - 非目标、不变量和冲突优先级；
   - `authority.must_not`：**接过这一棒的模型**不能做的事，用第二人称写。这是棒级边界不是阶段契约，每次交棒都要重写，下一棒没有额外限制时诚实填 `[]`。只约束当前持棒方的限制（「这一棒只审计、不改代码」）一律写这里，**绝不能写进 `design.non_goals`**：非目标受 G1 保护并逐字继承，把角色边界写进去，等于把下一棒要干的活儿本身锁死，交回去修的时候还得走删除授权，或者被逼开一个本不该开的新阶段。
   - 当前详细决策、权限边界、状态/证据、P0/P1/P2、偏差、引用；
   - 可执行第一步：目的、项目相对 cwd、带用途的 read/modify 路径、`command_hint`、预期、完成条件和失败分支；纯只读任务的 `modify` 必须诚实写空数组，禁止伪造“不得修改”的修改入口。
   每条阶段状态只能是 `pending`、`met`、`partial` 或 `unverifiable`；后两者必须写明原因，`met` 不得由 CLI 或模型默认推定。
   `next_step.done_when` 只定义第一步完成，绝不替代整阶段的 `phase.done_when`；不得把第一步完成当作阶段完成或阶段停点。
8. successor 草稿由 contextual draft 预填旧阶段完整 `completion.snapshot`，交棒方只更新其最终 summary、完成证据和逐条 `completion.snapshot.phase.done_when_status`；`next` 必填新阶段 summary、`phase.outcome`、`phase.done_when` 和第一步，并只在 `overrides` / `changes` 中声明变化。顶层 `authorization` 必须逐字写用户授权开启下一阶段的原话。CLI 从旧阶段继承整体设计契约、`design.invariants`、`design.non_goals`、权限、未完事项、引用和活动决策，唯独 `authority.must_not` 一律清空——它约束的是持棒的人不是阶段，新阶段的边界要在 `next.overrides.authority.must_not` 里重新声明；自动写入 `phase.predecessor_relay_id`、lineage 与前阶段收尾摘要，并把新阶段状态初始化为逐条 `pending`。新阶段 outcome/done_when 是全新契约，不登记为旧判据删除。
9. 同阶段的 `phase.outcome`、`phase.done_when`、`design.invariants`、`design.non_goals` 是受保护验收契约；只有逐字完全相同才算保留，在旧文本后追加“废弃”“不适用”或例外也属于改写。**任何文字变化都必须显式登记**到请求 envelope 的 `changes.criteria`：真正收紧阶段交付、完成标准或不变量时用 `strengthened`，填写精确旧文本、精确 replacement、原因和 `authorized_by: null`；删除、弱化或合并必须有用户明确授权。任何新列表项都用 `added`；新增正向判据使用 `authorized_by: null`，而**新增 `design.non_goals` 会缩小范围**，必须记录用户明确授权。禁止对 non-goal 使用 `strengthened`，不得把“实现已经完成”冒充授权。收到 `criteria_transition_required` 时恢复精确旧文本或填写正确的显式 transition。successor 仍逐字保护整体 `design.invariants` / `design.non_goals`，其变更继续走同一登记规则。CLI 把每条变更作为本 revision 的 `criteria_changes` 完整回执，并分配本 revision 内从 1 开始的 `ordinal`；`delta.criteria_changes` 直接返回完整回执，历史审计以 relay id + revision + ordinal 定位。`strengthened` 是提交方声明，不是 CLI 的语义证明，必须保证 action、原因和授权真实。
10. 决策短标签必须稳定、简短。完整决策正文属于当前 `snapshot.decisions`；successor 需要改这组正文时使用 `next.overrides.decisions`。同阶段更新和 successor 都**不得通过遗漏删除活动决策**：在每个 `changes.active_decision_ids` 中逐项列出本轮结束后仍活动的全部 ID；漏列、多列、重复或列入已退出 ID 都会被拒绝。`changes.decisions` 只登记退出 lifecycle transition：
   - `retire`：原因 + `replacement: null`；
   - `supersede`：原因 + 仍活动的 replacement ID。
   不得复用退出 ID，不得把流水账写进 snapshot。
11. 禁止追加聊天时间线、更新日志、本轮变化、旧 revision、完整 diff、长日志或大段源码。同阶段更新整份替换；跨阶段只写 contextual successor 草稿要求的完成声明与变化。canonical JSON 是正式真相，派生 Markdown 由 CLI 现渲染；模型不得直接编辑任一正式文件。Markdown 缺失、被改或格式损坏只通过 `document_export` 返回非阻断诊断，load 仍采用 canonical 现渲染内容；canonical 损坏才停止。
12. 每种 operation 的草稿都先运行 `relay validate --request <内部临时文件>`。请求文件超过 96 KiB，或最终 canonical、派生 Markdown、完整 load 响应超过统一 128 KiB 总硬上限时，CLI 会在任何正式文件写入前拒绝；写入预检按最终完整活动决策集和最终序列化结果计数，保证成功写入后仍能 load。完整活动决策正文始终随当前 canonical 携带，并由 load 的 `active_decisions` 一次返回。不得靠省略逐条完成状态、当前有效决策、阶段完成标准、不变量、P0、失败分支、安全边界或必须升级项换取通过。返回出现唯一的 `budget_advice`（完整响应超过 48 KiB 软预算）时，先按它点名的最厚顶层字段做一轮精炼再重新 `validate`：只删流水账、时间线叙事、重复结论、日志与源码转储，**决策四要素、逐条完成状态和仍然有效的约束一律不许删**；若活动决策占大头，正确动作是把不再约束后续工作的决策 `supersede` / `retire`。精炼后仍超软预算，就在交棒说明里写清最厚字段为什么不能再缩然后继续，不必额外询问用户。上限放宽不等于可以写得更啰嗦。
13. 根棒和同阶段更新都运行 `relay pass --request <内部临时文件> --client <WRITER_IDENTITY> --model <当前模型>`；跨阶段运行 `relay successor --request <内部临时文件> --client <WRITER_IDENTITY> --model <当前模型>`，一个 CAS 同时归档旧记录并创建新记录。relay id 与 expected revision 已在 contextual draft 的 `target` envelope 中，写命令不得再拼目标参数。
14. 用户明确要求阶段中途换模型时，必须更新同一 active Relay 的当前真相，让下一模型直接接棒；不得让用户手工复制粘贴审查或审计文本。用户定义下一阶段时走 successor 事务，不得先单独 done 再要求用户补建新棒。
15. 用户裁定当前 active 棒本身创建错误时，运行 `relay draft create --operation withdraw --relay-id <内部 relay id>`，在草稿 `payload.reason` 填写基于用户裁定的原因，validate 后执行 `relay withdraw --request <内部临时文件>`；撤销不是阶段完成，禁止用 `done` 掩盖错误创建。`stale_revision`、dirty/diverged store、`request_too_large`、`load_too_large`、`phase_authorization_required`、敏感信息或 canonical 损坏一律停止；不得静默截断当前真相。派生 Markdown 漂移只按诊断报告，不冒充 canonical 损坏。若 `sync_error` 带 `details.local_committed=true`，用 details 的新指针更新恢复状态，不得使用旧 revision。
16. 成功后记住新指针；successor 时同时汇报旧阶段 done revision、新阶段 id/revision 和同步状态。无论在哪一步退出，都在 finally 运行 `relay draft cleanup --path <内部临时文件>`；所有退出路径不得遗留草稿或删除正式 JSON/Markdown。

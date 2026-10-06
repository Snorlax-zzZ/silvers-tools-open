# relay-done 语义模板

菜单注释：收棒：验证完成证据并归档当前接力任务

本文件由安装模型转换为当前客户端的原生显式入口，不是客户端成品文件，严禁原样复制。用户不需要输入任何参数；可靠指针、请求路径、`<WRITER_IDENTITY>` 和 model 均由入口内部维护。安装模型必须把作者占位符替换为用户确认的稳定助手身份，不得用宿主客户端名自动代替。

写入参数 `--model <当前模型>` 使用当前客户端提供的实际模型稳定 ID，不使用带空格的显示名或猜测值；`--client` 使用已确认的稳定作者身份。两者的字符、长度与取值要求见[统一安装说明](../README.md)。

## 授权边界

显式调用只授权 Relay CLI 更新并归档独立 Relay store，不授权当前业务项目 commit/push。

## 权限执行

显式调用把本入口所需的 Relay CLI、独立 store 与请求草稿操作视为一个完整授权流程；不得按 Relay 子命令或草稿文件逐步询问。先按宿主当前已生效权限执行，禁止预先申请升级权限；`--help` 和只读 `status` 不得成为主动升级理由。只有宿主返回实际权限拒绝时才停止重试，并请求一次有界的 Relay 权限配置，覆盖稳定 launcher、Relay work 目录和已配置 remote。处于 full access / no-approval 时必须省略全部升级审批元数据。该权限不扩大到业务项目。

## 执行语义

1. 检查稳定的 Relay CLI 入口并运行 `relay status`。CLI 不可用或未配置时停止；日常入口不得安装或 setup。
2. 只使用成功交棒或经用户确认接棒记住的 relay id 与 expected revision。没有可靠指针时可运行 `relay list` 帮助说明，但本次必须停止并提示必须先执行适配后的接棒入口；不得从列表直接归档。
3. 运行 `relay load --relay-id <内部 relay id>`，要求 revision 与会话指针完全一致。重新读取阶段交付、**阶段完成标准**、`phase_completion`、P0、偏差、活动决策和权限边界；要求 `phase_completion.alignment_complete: true`，不得把旧版 unknown 或历史推定当成 `met`。`delta.criteria_changes` 已含完整回执；遇到其他 revision 的可疑 action、授权或理由时，运行 `relay recall --relay-id <source-id> --revision <source-revision> --criteria-ordinal <ordinal>` 取回。旧档案的 `C-NNN` 仅通过兼容的 `--criteria-id` 读取。若 `warnings` 含 `installation_stale` 或 `installation_source_dirty`，归档前停止，明确报告需要重装适配器或先提交/清理 Relay 源码；不得在本机规则无法核实的状态下收棒。
4. 核实真实工作区和最新测试/构建证据。只满足 `next_step.done_when`，或只完成内部批次、测试检查点或普通代码审查时不得收棒；必须逐条声明整根棒的 `phase.done_when_status`。任何 `pending` 都拒绝收棒；`partial` / `unverifiable` 必须保留真实原因，禁止改写成 `met`。存在未解决 P0、未批准偏差、stale revision、缺失证据、进行中事项或未决设计权限问题时拒绝收棒。
5. 运行 `relay draft create --operation done --relay-id <内部 relay id>` 并登记 finally 清理。contextual draft 会预填 target 和当前快照；生成最终完整快照，逐条填写与 `phase.done_when` 对齐的状态，只删除有证据证明失效的进行中描述，保留最终设计契约、仍有效决策、完成证据、后续阶段 P1/P2 和引用，并在 `changes.active_decision_ids` 列出全部仍活动 ID；不得追加收尾日志。
6. predecessor 不得改变。阶段交付、`phase.done_when`、不变量和非目标只有逐字完全相同才算保留；追加“废弃”“不适用”或例外也是改写，**任何文字变化都必须显式登记**到 `changes.criteria`。真正收紧阶段交付、完成标准或不变量时用 `strengthened`，填写精确旧文本、精确 replacement、原因和 `authorized_by: null`；删除、弱化或合并必须有用户明确授权。任何新列表项都用 `added`；新增正向判据使用 `authorized_by: null`，而**新增 `design.non_goals` 会缩小范围**，必须记录用户明确授权。禁止对 non-goal 使用 `strengthened`。遇到 `criteria_transition_required` 必须恢复精确旧文本或填写正确的显式 transition，禁止为了收棒降低验收线。若本阶段确实 retire/supersede 决策，另在 `changes.decisions` 中写显式 lifecycle transition；不得通过遗漏让约束消失。
7. 先运行 `relay validate --request <内部临时文件>`，再运行 `relay done --request <内部临时文件> --client <WRITER_IDENTITY> --model <当前模型>`；relay id 与 expected revision 已在请求 `target` 中，写命令不得再拼目标参数。
8. CLI 会把权威 canonical JSON 与派生 Markdown 导出物作为一个逻辑记录在同一 commit 中从 active 移到 done。不得手工移动、删除或编辑任一正式文件；Markdown 漂移只产生非阻断 `document_export` 诊断，canonical 才是读取真相。
9. commit 前失败保留旧指针和完整 active 文件对。若 `sync_error` 带 `details.local_committed=true`，本地已经是 details 指明的 done revision/path/canonical_path：明确报告本地已收棒、远端未同步，不得声称仍 active 或用旧 revision 重试。
10. 若用户**已经定义下一阶段**，本入口不得先单独归档：改由交棒入口执行一个 successor 事务，在同一 CAS 中完成旧阶段归档和新阶段创建，用户不需要复制交接文本或 predecessor id。只有当前没有 successor 时才继续本收棒流程；内部批次或普通审查本身不是模型自动创建 successor 的理由——**阶段只由用户开启**。模型可以建议开新阶段，但 successor 请求必须带用户授权原话，自认的新阶段写不进去。
11. 完全同步后汇报最终 revision、阶段交付、两条归档路径和同步状态，并清除会话指针。无论成功失败，都在 finally 运行 `relay draft cleanup --path <内部临时文件>`；所有退出路径不得遗留草稿。

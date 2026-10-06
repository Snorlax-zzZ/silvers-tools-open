# relay-load 语义模板

菜单注释：接棒：加载当前项目的接力任务并完成理解回执

本文件由安装模型转换为当前客户端的原生显式入口，不是客户端成品文件，严禁原样复制。用户不需要输入任何参数；候选编号和 recall 指针均由入口内部维护。

## 授权边界

显式调用只授权 Relay CLI 同步并读取独立 Relay store。当前业务项目在理解确认门之前保持只读。

## 权限执行

显式调用把本入口所需的 Relay CLI、独立 store 与请求草稿操作视为一个完整授权流程；不得按 Relay 子命令或草稿文件逐步询问。先按宿主当前已生效权限执行，禁止预先申请升级权限；`--help` 和只读 `status` 不得成为主动升级理由。只有宿主返回实际权限拒绝时才停止重试，并请求一次有界的 Relay 权限配置，覆盖稳定 launcher、Relay work 目录和已配置 remote。处于 full access / no-approval 时必须省略全部升级审批元数据。该权限不扩大到业务项目。

## 执行语义

1. 检查稳定的 Relay CLI 入口，运行 `relay status`；未配置时停止，不得在日常入口安装或 setup。
2. 运行 `relay list`。零项时报告无 active，并可在用户询问旧阶段时内部运行 `relay history`；一项时内部选择；多项时展示带编号的标题、阶段、revision、上一 client/model，只让用户回复数字。
3. 选定后统一运行 `relay load --relay-id <内部 relay id>`，记住 relay id 与 expected revision。完整 load 响应受 **128 KiB** 总硬上限约束，软预算 48 KiB；超软预算时响应里会带唯一的 `budget_advice`，交棒时需按其最厚顶层字段精炼。若出现 `installation_warnings_truncated`，说明安装警告总量已被截断，必须另跑 `relay status` 看完整安装诊断，不能当作安装正常。
4. 先读行动卡的**一句话状态**与第一步，再读阶段完成标准和结构化 `delta`；不得仅凭标题或尚未带状态的判据措辞推断要重做阶段：
   - 核对整体用户结果、阶段交付、一句话状态、阶段完成标准及其逐条状态和第一步；
   - 报告 delta 的 changed paths、决策新增/更新/退出和截断状态；
   - 逐项报告 `delta.criteria_changes`；它是上一 revision 对受保护判据所做变更的结构化审计摘要，不能只看 changed paths；
   - 核对 `source_relation`。`dirty_unverifiable` 时逐项完成 `source_verification.checklist`；`changed` 时先检查真实代码，不执行旧命令提示。
   - 若 `warnings` 含 `installation_stale`，在修改项目之前停止并明确报告需要重装的 client；若含 `installation_source_dirty`，停止并报告 Relay 源码有未提交改动，必须先提交或清理，当前不能证明装机规则与源码一致。
   - 检查 `document_export`。派生 Markdown 缺失、被改、非法 UTF-8 或过大只产生非阻断诊断；理解内容必须使用响应中由 canonical JSON 现渲染的 `document`，不得把导出物漂移误报成 canonical 损坏。
5. 要求 load 返回 `active_decisions_complete: true`，并核对 `active_decision_count` 与 `active_decisions` 数量一致；**活动决策全文已经由 CLI 一次摊平**，必须全部纳入理解回执，缺失或无法解析时停止，绝不静默继续，也**不得为了理解活动决策逐条 recall**。同时要求 `phase_completion.alignment_complete: true`，核对 criterion/status count 和每条 `met|partial|unverifiable|pending`；不得把无声明状态推定成 `met`。读取 CLI 自动生成的**前阶段收尾摘要**，确认上一阶段交付、每条完成标准的达成状态、证据计数和 done 档案指针；`status_source=legacy_inferred` 或 `completion_status_warnings` 表示旧版只有历史推定，必须按 unknown 处理，不能当成已验证真值。当前格式的 `delta.criteria_changes` 已含完整回执；需要读取其他 revision 的判据审计时，用 `relay recall --relay-id <source-id> --revision <source-revision> --criteria-ordinal <ordinal>` 精确取回。`relay recall --criteria-id <C-NNN>` 只用于旧档案兼容读取。recall 一次返回指定对象，不存在 cursor；不得无差别 recall 全部历史。 若需查询已退出决策正文，`--revision` 必须指定仍含正文的历史版本：例如在第 N 版退出，就查询仍含正文的 N−1 版；退出发生的 N 版已没有正文，CLI 不会自动回溯。判据回执仍查其变更发生的 revision 与该版 ordinal。
6. 只有需要了解已完成阶段脉络时才内部运行一次 `relay history` 读取阶段大纲；它不分页，也不替代 active snapshot，不把 done 文档或多轮 Git 历史默认灌入上下文。
7. 输出结构化理解回执：
   - 用户最终结果和为什么做；
   - 当前阶段交付、阶段完成标准、明确非目标；
   - `authority.must_not` 逐条复述，并明确它约束的是**你这一棒**：它不是阶段契约，也不传给下一个接棒的人。若其中某条与用户刚下达的指令冲突，当场说明并询问用户，**不得据此开新阶段**；
   - 不变量、冲突优先级和全部可见活动决策；
   - 可自行决定、必须升级、假设、未知项和偏差；
   - source relation 与真实代码冲突；
   - 第一动作、预期、单步完成条件、失败分支和真正的阶段停止点；明确 `next_step.done_when` 只完成第一步，不等于 `phase.done_when`。
8. 明确维护的 relay id/revision，等待用户确认。即使上文要求直接开始，本次接棒也只负责对齐；**用户确认前不得修改项目文件**、运行破坏性命令、commit 或 push。
9. 用户确认后按项目规则继续。**用户未要求换模型时，持续推进到 `phase.done_when`**；完成 `next_step.done_when`、内部批次、测试检查点或普通代码审查都不等于阶段完成，也不是模型自行设定的阶段停点。
10. 允许停止或交棒的条件是**阶段完成、真实阻塞、权限升级或用户明确要求中途换模型**。用户可在任何时候明确要求交棒，模型必须照办；不得把普通审查甩给用户，不得为了等待另一模型批准而制造审查乒乓。
11. 用户明确要求阶段中途换模型时，通过适配后的交棒入口更新同一 active Relay，让下一模型直接 load；不得要求用户复制粘贴审查文本，不得自动调用模型或外部服务。Relay 不决定用户应选择哪个模型。永远不要直接编辑正式 canonical JSON 或派生 Markdown。

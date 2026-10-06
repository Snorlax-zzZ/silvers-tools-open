from __future__ import annotations

import json
from typing import Any, Iterable


FRONTMATTER_FIELDS = (
    "relay_id",
    "project_key",
    "project_remote",
    "title",
    "status",
    "revision",
    "created_at",
    "updated_at",
    "done_at",
    "withdrawn_at",
    "withdraw_reason",
    "last_client",
    "last_model",
    "last_machine",
    "source_head",
    "source_branch",
    "source_dirty",
)


def _scalar(value: Any) -> str:
    return str(value).strip()


def _bullets(values: Iterable[Any], *, empty: str = "无") -> str:
    items = [_scalar(value) for value in values if _scalar(value)]
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def _frontmatter_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _path_bullets(values: Iterable[dict[str, Any]]) -> str:
    items = list(values)
    if not items:
        return "- 无"
    return "\n".join(
        f"- `{item['path']}`：{item['purpose']}" for item in items
    )


def _render_legacy_document(
    request: dict[str, Any],
    metadata: dict[str, Any],
    decision_registry: list[dict[str, Any]] | None = None,
    criteria_registry: list[dict[str, Any]] | None = None,
    predecessor_summary: dict[str, Any] | None = None,
) -> str:
    phase = request["phase"]
    design = request["design"]
    authority = request["authority"]
    state = request["state"]
    next_step = request["next_step"]
    remaining = request["remaining"]
    phase_id_line = ""
    if phase.get("phase_id"):
        phase_id_line = f"- **阶段标识**：`{phase['phase_id']}`\n"
    predecessor_section = ""
    if predecessor_summary is not None:
        achieved = _bullets(
            (
                f"{item['status']} · {item['criterion']}"
                for item in predecessor_summary["done_when"]
            )
        )
        predecessor_section = f"""

### 前阶段收尾摘要

- **档案指针**：`{predecessor_summary['relay_id']}` r{predecessor_summary['revision']}
- **阶段标识**：`{predecessor_summary['phase_id']}`
- **阶段交付**：{predecessor_summary['phase_outcome']}
- **完成标准达成情况**：
{achieved}
- **验证证据数**：{predecessor_summary['evidence_count']}
"""
    predecessor_insert = (
        f"\n{predecessor_section}" if predecessor_section else ""
    )

    frontmatter = "\n".join(
        f"{key}: {_frontmatter_value(value)}" for key, value in metadata.items()
    )
    decisions = []
    for decision in request["decisions"]:
        decisions.append(
            "\n".join(
                [
                    f"### {decision['id']} · {decision['status']}",
                    f"- **短标签**：{decision['label']}",
                    f"- **决策**：{decision['decision']}",
                    f"- **理由**：{decision['reason']}",
                    "- **否决方案**：\n" + _bullets(decision["rejected"]),
                    f"- **重议条件**：{decision['reopen_when']}",
                ]
            )
        )
    current_ids = {decision["id"] for decision in request["decisions"]}
    cold_decisions = [
        entry
        for entry in (decision_registry or [])
        if entry["id"] not in current_ids
    ]
    cold_index = _bullets(
        (
            f"`{entry['id']}` · {entry['status']} · {entry['label']} · "
            f"完整内容见 {entry['source_relay_id']} r{entry['source_revision']}"
        )
        for entry in cold_decisions
    )
    criteria_section = "\n"
    if criteria_registry is not None:
        criteria_index = _bullets(
            (
                f"`{entry['id']}` · {entry['action']} · "
                f"`{entry['field']}` · {entry['label']} · "
                f"{'已登记授权' if entry['authorized'] else '无需授权'} · "
                f"完整登记见 {entry['source_relay_id']} "
                f"r{entry['source_revision']}"
            )
            for entry in criteria_registry
        )
        criteria_section = f"\n\n### 判据变更冷索引\n\n{criteria_index}\n"

    deviations = _bullets(request["deviations"])
    return f"""---
{frontmatter}
---

# {request['title']}

## 1. 接棒入口

### 阶段契约
- **整体用户结果**：{design['outcome']}
{phase_id_line}- **当前阶段**：{phase['name']}
- **本阶段交付**：{phase['outcome']}
- **前序阶段**：{phase['predecessor_relay_id'] or '无'}
- **本阶段完成标准**：
{_bullets(phase['done_when'])}{predecessor_insert}

### 一句话状态
- **状态**：{request['summary']}

### 接棒后的第一步
- **目的**：{next_step['purpose']}
- **工作目录**：{next_step['cwd']}
- **前置条件**：
{_bullets(next_step['preconditions'])}
- **必读文件**：
{_path_bullets(next_step['read'])}
- **修改入口**：
{_path_bullets(next_step['modify'])}
- **起始命令提示**：`{next_step['command_hint']}`
- **预期结果**：{next_step['expected']}
- **完成标准**：{next_step['done_when']}
- **失败分支**：{next_step['failure']}

## 2. 设计契约

- **用户结果**：{design['outcome']}
- **为什么现在做**：{design['why']}
- **明确非目标**：
{_bullets(design['non_goals'])}
- **不可破坏不变量**：
{_bullets(design['invariants'])}
- **冲突优先级**：
{_bullets(design['priorities'])}

## 3. 关键决策

### 当前详细决策

{(chr(10) * 2).join(decisions) if decisions else '- 无'}

### 仍有效但未展开的决策索引

{cold_index}{criteria_section}
## 4. 权限与歧义

### 可自行决定
{_bullets(authority['may_decide'])}

### 必须升级确认
{_bullets(authority['must_escalate'])}

### 已知假设
{_bullets(authority['assumptions'])}

### 未知项
{_bullets(authority['unknowns'])}

## 5. 当前状态与证据

### 已完成
{_bullets(state['completed'])}

### 进行中
{_bullets(state['in_progress'])}

### 最新验证证据
{_bullets(state['evidence'])}

## 6. 剩余任务

### P0
{_bullets(remaining['p0'])}

### P1
{_bullets(remaining['p1'])}

### P2
{_bullets(remaining['p2'])}

## 7. 偏差与阻塞

{deviations}

## 8. 引用

{_bullets(request['references'])}
"""


def _phase_done_when_bullets(phase: dict[str, Any]) -> str:
    rendered: list[str] = []
    for criterion, state in zip(
        phase["done_when"],
        phase["done_when_status"],
        strict=True,
    ):
        reason = f" — {state['reason']}" if state["reason"] else ""
        rendered.append(f"- [{state['status']}] {criterion}{reason}")
    return "\n".join(rendered)


def _predecessor_summary_section(
    predecessor_summary: dict[str, Any] | None,
) -> str:
    if predecessor_summary is None:
        return ""
    achieved = []
    for item in predecessor_summary["done_when"]:
        source = predecessor_summary["status_source"]
        source_suffix = f"/{source}" if source != "declared" else ""
        reason = f" — {item['reason']}" if item["reason"] else ""
        achieved.append(
            f"- [{item['status']}{source_suffix}] {item['criterion']}{reason}"
        )
    status_note = ""
    if predecessor_summary["status_note"]:
        status_note = (
            f"\n- **兼容说明**：{predecessor_summary['status_note']}"
        )
    return f"""

### 前阶段收尾摘要

- **档案指针**：`{predecessor_summary['relay_id']}` r{predecessor_summary['revision']}
- **阶段标识**：`{predecessor_summary['phase_id']}`
- **阶段交付**：{predecessor_summary['phase_outcome']}
- **完成标准达成情况**：
{chr(10).join(achieved)}
{status_note}
- **验证证据数**：{predecessor_summary['evidence_count']}
"""


def _render_v5_document(
    request: dict[str, Any],
    metadata: dict[str, Any],
    decision_registry: list[dict[str, Any]] | None = None,
    criteria_registry: list[dict[str, Any]] | None = None,
    predecessor_summary: dict[str, Any] | None = None,
) -> str:
    """render_version 5 的渲染器，已冻结。

    v5 存量档案必须逐字节按这份渲染回去。不要为了少写一份模板就把它和
    v6 合成一个带 if 的函数——0.6.0 就是这么把存量棒全部渲染坏的：
    共用代码路径上任何一个空行改动都会让旧档案的字节比对失败。
    """

    phase = request["phase"]
    design = request["design"]
    authority = request["authority"]
    state = request["state"]
    next_step = request["next_step"]
    remaining = request["remaining"]
    phase_id_line = ""
    if phase.get("phase_id"):
        phase_id_line = f"- **阶段标识**：`{phase['phase_id']}`\n"

    frontmatter = "\n".join(
        f"{key}: {_frontmatter_value(value)}" for key, value in metadata.items()
    )
    # 当前决策渲染全文：决策 / 理由 / 否决方案 / 重议条件 四要素缺一不可。
    # 这四项是归档里最有判断价值的部分——三个月后 canonical JSON 没人读，
    # 只有这份 Markdown 还在被人翻。不允许退回「只留索引、全文靠 load 拉」，
    # 那样归档一旦脱离 CLI 就失去自解释能力。
    decisions = []
    for decision in request["decisions"]:
        decisions.append(
            "\n".join(
                [
                    f"#### {decision['id']} · {decision['status']}",
                    f"- **短标签**：{decision['label']}",
                    f"- **决策**：{decision['decision']}",
                    f"- **理由**：{decision['reason']}",
                    "- **否决方案**：\n" + _bullets(decision["rejected"]),
                    f"- **重议条件**：{decision['reopen_when']}",
                ]
            )
        )
    # 冷索引只收录不在本次 decisions 里的历史决策，避免和上面的全文重复。
    current_ids = {decision["id"] for decision in request["decisions"]}
    cold_decisions = [
        entry
        for entry in (decision_registry or [])
        if entry["id"] not in current_ids
    ]
    cold_index = _bullets(
        (
            f"`{entry['id']}` · {entry['status']} · {entry['label']} · "
            f"完整内容见 {entry['source_relay_id']} r{entry['source_revision']}"
        )
        for entry in cold_decisions
    )
    criteria_section = "\n"
    if criteria_registry is not None:
        criteria_index = _bullets(
            (
                f"`{entry['id']}` · {entry['action']} · "
                f"`{entry['field']}` · {entry['label']} · "
                f"{'已登记授权' if entry['authorized'] else '无需授权'} · "
                f"完整登记见 {entry['source_relay_id']} "
                f"r{entry['source_revision']}"
            )
            for entry in criteria_registry
        )
        criteria_section = f"\n\n### 判据变更冷索引\n\n{criteria_index}\n"

    deviations = _bullets(request["deviations"])
    predecessor_section = _predecessor_summary_section(predecessor_summary)
    return f"""---
{frontmatter}
---

# {request['title']}

## 1. 接棒入口

### 阶段契约
- **整体用户结果**：{design['outcome']}
{phase_id_line}- **当前阶段**：{phase['name']}
- **本阶段交付**：{phase['outcome']}
- **前序阶段**：{phase['predecessor_relay_id'] or '无'}

### 一句话状态
- **状态**：{request['summary']}

### 接棒后的第一步
- **目的**：{next_step['purpose']}
- **工作目录**：{next_step['cwd']}
- **前置条件**：
{_bullets(next_step['preconditions'])}
- **必读文件**：
{_path_bullets(next_step['read'])}
- **修改入口**：
{_path_bullets(next_step['modify'])}
- **起始命令提示**：`{next_step['command_hint']}`
- **预期结果**：{next_step['expected']}
- **完成标准**：{next_step['done_when']}
- **失败分支**：{next_step['failure']}

### 本阶段完成标准与状态
{_phase_done_when_bullets(phase)}{predecessor_section}

## 2. 设计契约

- **用户结果**：{design['outcome']}
- **为什么现在做**：{design['why']}
- **明确非目标**：
{_bullets(design['non_goals'])}
- **不可破坏不变量**：
{_bullets(design['invariants'])}
- **冲突优先级**：
{_bullets(design['priorities'])}

## 3. 关键决策

### 当前详细决策

{(chr(10) * 2).join(decisions) if decisions else '- 无'}

### 仍有效但未展开的决策索引

{cold_index}{criteria_section}
## 4. 权限与歧义

### 可自行决定
{_bullets(authority['may_decide'])}

### 必须升级确认
{_bullets(authority['must_escalate'])}

### 已知假设
{_bullets(authority['assumptions'])}

### 未知项
{_bullets(authority['unknowns'])}

## 5. 当前状态与证据

### 已完成
{_bullets(state['completed'])}

### 进行中
{_bullets(state['in_progress'])}

### 最新验证证据
{_bullets(state['evidence'])}

## 6. 剩余任务

### P0
{_bullets(remaining['p0'])}

### P1
{_bullets(remaining['p1'])}

### P2
{_bullets(remaining['p2'])}

## 7. 偏差与阻塞

{deviations}

## 8. 引用

{_bullets(request['references'])}
"""


def render_document(
    request: dict[str, Any],
    metadata: dict[str, Any],
    decision_registry: list[dict[str, Any]] | None = None,
    criteria_registry: list[dict[str, Any]] | None = None,
    predecessor_summary: dict[str, Any] | None = None,
    phase_authorization: str | None = None,
    criteria_changes: list[dict[str, Any]] | None = None,
) -> str:
    phase = request["phase"]
    design = request["design"]
    authority = request["authority"]
    state = request["state"]
    next_step = request["next_step"]
    remaining = request["remaining"]
    phase_id_line = ""
    if phase.get("phase_id"):
        phase_id_line = f"- **阶段标识**：`{phase['phase_id']}`\n"

    frontmatter = "\n".join(
        f"{key}: {_frontmatter_value(value)}" for key, value in metadata.items()
    )
    # 当前决策渲染全文：决策 / 理由 / 否决方案 / 重议条件 四要素缺一不可。
    # 这四项是归档里最有判断价值的部分——三个月后 canonical JSON 没人读，
    # 只有这份 Markdown 还在被人翻。不允许退回「只留索引、全文靠 load 拉」，
    # 那样归档一旦脱离 CLI 就失去自解释能力。
    decisions = []
    for decision in request["decisions"]:
        decisions.append(
            "\n".join(
                [
                    f"#### {decision['id']} · {decision['status']}",
                    f"- **短标签**：{decision['label']}",
                    f"- **决策**：{decision['decision']}",
                    f"- **理由**：{decision['reason']}",
                    "- **否决方案**：\n" + _bullets(decision["rejected"]),
                    f"- **重议条件**：{decision['reopen_when']}",
                ]
            )
        )
    # 冷索引只收录不在本次 decisions 里的历史决策，避免和上面的全文重复。
    current_ids = {decision["id"] for decision in request["decisions"]}
    cold_decisions = [
        entry
        for entry in (decision_registry or [])
        if entry["id"] not in current_ids
    ]
    cold_index = _bullets(
        (
            f"`{entry['id']}` · {entry['status']} · {entry['label']} · "
            f"完整内容见 {entry['source_relay_id']} r{entry['source_revision']}"
        )
        for entry in cold_decisions
    )
    criteria_section = "\n"
    if criteria_changes is not None:
        criteria_receipt = _bullets(
            (
                f"`C-{entry['ordinal']:03d}` · {entry['action']} · "
                f"`{entry['field']}` · {entry['id_or_text']} · "
                f"理由：{entry['reason']} · "
                f"授权：{entry['authorized_by'] or '无需授权'}"
                for entry in criteria_changes
            )
        )
        criteria_section = (
            "\n\n### 本 revision 判据变更回执\n\n"
            f"{criteria_receipt}\n"
        )
    elif criteria_registry is not None:
        criteria_index = _bullets(
            (
                f"`{entry['id']}` · {entry['action']} · "
                f"`{entry['field']}` · {entry['label']} · "
                f"{'已登记授权' if entry['authorized'] else '无需授权'} · "
                f"完整登记见 {entry['source_relay_id']} "
                f"r{entry['source_revision']}"
            )
            for entry in criteria_registry
        )
        criteria_section = f"\n\n### 判据变更冷索引\n\n{criteria_index}\n"

    deviations = _bullets(request["deviations"])
    predecessor_section = _predecessor_summary_section(predecessor_summary)
    # 三种情况必须分开：没有授权记录不等于没有前序阶段。schema 6 之前
    # 推进出来的棒 lineage 里没有这个字段，若和根棒共用一句文案，一根
    # "模型自己开的新阶段"升级后会被洗成"根棒"，恰好盖掉要查的东西。
    if phase_authorization:
        authorization_line = f"- **开启本阶段的授权**：{phase_authorization}\n"
    elif phase["predecessor_relay_id"]:
        authorization_line = (
            "- **开启本阶段的授权**：schema 6 之前创建，未留存授权原话\n"
        )
    else:
        authorization_line = "- **开启本阶段的授权**：根棒，无前序阶段\n"
    return f"""---
{frontmatter}
---

# {request['title']}

## 1. 接棒入口

### 阶段契约
- **整体用户结果**：{design['outcome']}
{phase_id_line}- **当前阶段**：{phase['name']}
- **本阶段交付**：{phase['outcome']}
- **前序阶段**：{phase['predecessor_relay_id'] or '无'}
{authorization_line}
### 一句话状态
- **状态**：{request['summary']}

### 接棒后的第一步
- **目的**：{next_step['purpose']}
- **工作目录**：{next_step['cwd']}
- **前置条件**：
{_bullets(next_step['preconditions'])}
- **必读文件**：
{_path_bullets(next_step['read'])}
- **修改入口**：
{_path_bullets(next_step['modify'])}
- **起始命令提示**：`{next_step['command_hint']}`
- **预期结果**：{next_step['expected']}
- **完成标准**：{next_step['done_when']}
- **失败分支**：{next_step['failure']}

### 本阶段完成标准与状态
{_phase_done_when_bullets(phase)}{predecessor_section}

## 2. 设计契约

- **用户结果**：{design['outcome']}
- **为什么现在做**：{design['why']}
- **明确非目标**：
{_bullets(design['non_goals'])}
- **不可破坏不变量**：
{_bullets(design['invariants'])}
- **冲突优先级**：
{_bullets(design['priorities'])}

## 3. 关键决策

### 当前详细决策

{(chr(10) * 2).join(decisions) if decisions else '- 无'}

### 仍有效但未展开的决策索引

{cold_index}{criteria_section}
## 4. 权限与歧义

### 这一棒不能做
{_bullets(authority['must_not'], empty='无额外限制')}

### 可自行决定
{_bullets(authority['may_decide'])}

### 必须升级确认
{_bullets(authority['must_escalate'])}

### 已知假设
{_bullets(authority['assumptions'])}

### 未知项
{_bullets(authority['unknowns'])}

## 5. 当前状态与证据

### 已完成
{_bullets(state['completed'])}

### 进行中
{_bullets(state['in_progress'])}

### 最新验证证据
{_bullets(state['evidence'])}

## 6. 剩余任务

### P0
{_bullets(remaining['p0'])}

### P1
{_bullets(remaining['p1'])}

### P2
{_bullets(remaining['p2'])}

## 7. 偏差与阻塞

{deviations}

## 8. 引用

{_bullets(request['references'])}
"""


def render_record(record: dict[str, Any]) -> str:
    metadata = {
        "relay_schema": record["relay_schema"],
        **{
            field: record["metadata"][field]
            for field in FRONTMATTER_FIELDS
            if field in record["metadata"]
        },
    }
    legacy_registry = record.get("decision_registry")
    registry = (
        legacy_registry.get("active", [])
        if isinstance(legacy_registry, dict)
        else []
    )
    if record["render_version"] == 2:
        return _render_legacy_document(record["snapshot"], metadata, registry)
    if record["render_version"] == 3:
        return _render_legacy_document(
            record["snapshot"],
            metadata,
            registry,
            record["criteria_registry"]["changes"],
        )
    if record["render_version"] == 4:
        return _render_legacy_document(
            record["snapshot"],
            metadata,
            registry,
            record["criteria_registry"]["changes"],
            record["lineage"]["predecessor_summary"],
        )
    if record["render_version"] == 5:
        return _render_v5_document(
            record["snapshot"],
            metadata,
            registry,
            record["criteria_registry"]["changes"],
            record["lineage"]["predecessor_summary"],
        )
    if isinstance(legacy_registry, dict):
        return render_document(
            record["snapshot"],
            metadata,
            registry,
            record["criteria_registry"]["changes"],
            record["lineage"]["predecessor_summary"],
            record["lineage"].get("phase_authorization"),
        )
    return render_document(
        record["snapshot"],
        metadata,
        predecessor_summary=record["lineage"]["predecessor_summary"],
        phase_authorization=record["lineage"].get("phase_authorization"),
        criteria_changes=record.get("criteria_changes", []),
    )

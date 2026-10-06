from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, InitVar
import hashlib
import json
from typing import Any, Callable, Literal, Mapping

from .errors import (
    IncompleteRelay,
    InvalidRequest,
    PhaseAuthorizationRequired,
    StaleRevision,
    UnapprovedDeviation,
    UnresolvedP0,
)
from .records import (
    request_from_snapshot,
    upgrade_legacy_request,
)


MISSING = object()
PROTOCOL_VERSION = 1
OperationName = Literal["create", "update", "successor", "done", "withdraw"]
CommandName = Literal["pass", "successor", "done", "withdraw"]
_COMPILE_TOKEN = object()


@dataclass(frozen=True)
class FieldSpec:
    kind: Literal[
        "object",
        "array",
        "string",
        "integer",
        "boolean",
        "null",
        "union",
    ]
    required: bool = True
    nullable: bool = False
    default: object = MISSING
    default_factory: Callable[[], object] | None = None
    fields: Mapping[str, "FieldSpec"] | None = None
    item: "FieldSpec" | None = None
    variants: tuple["FieldSpec", ...] = ()
    template_source: Literal[
        "constant",
        "placeholder",
        "current",
        "completion",
        "generated",
    ] = "constant"
    template_value: object = MISSING
    context_path: tuple[str, ...] | None = None
    apply: Literal[
        "replace",
        "inherit_if_null",
        "copy_from_completion_if_null",
        "clear",
        "generated",
    ] = "replace"
    normalizer: Callable[[object, str], object] | None = None

    def __post_init__(self) -> None:
        if self.default is not MISSING and self.default_factory is not None:
            raise ValueError("FieldSpec 不能同时声明 default 与 default_factory")
        if self.kind == "object" and self.fields is None:
            raise ValueError("object FieldSpec 必须声明 fields")
        if self.kind == "array" and self.item is None:
            raise ValueError("array FieldSpec 必须声明 item")
        if self.kind == "union" and not self.variants:
            raise ValueError("union FieldSpec 必须声明 variants")


@dataclass(frozen=True)
class OperationSpec:
    name: OperationName
    command: CommandName
    envelope: FieldSpec
    target_required: bool
    allowed_target_statuses: frozenset[str]
    gates: tuple[
        Literal["cas", "phase_authorization", "g1", "phase_complete"], ...
    ]


@dataclass(frozen=True)
class Target:
    relay_id: str
    expected_revision: int
    actual_revision: int


@dataclass(frozen=True)
class OperationContext:
    relay_id: str
    revision: int
    status: str
    record: Mapping[str, Any]


@dataclass(frozen=True)
class ValidatedOperation:
    operation: OperationName
    target: Target | None
    _compile_token: InitVar[object] = field(default=None, kw_only=True)
    _seal: str = field(init=False, repr=False, compare=False)

    def __post_init__(self, _compile_token: object) -> None:
        if _compile_token is not _COMPILE_TOKEN:
            raise TypeError("ValidatedOperation 只能由 compile_operation 构造")
        object.__setattr__(self, "_seal", _operation_digest(self))


@dataclass(frozen=True)
class ValidatedCreate(ValidatedOperation):
    snapshot: dict[str, Any]
    active_decision_ids: list[str]


@dataclass(frozen=True)
class ValidatedUpdate(ValidatedOperation):
    current: dict[str, Any]
    updated: dict[str, Any]
    active_decision_ids: list[str]


@dataclass(frozen=True)
class ValidatedDone(ValidatedOperation):
    current: dict[str, Any]
    completed: dict[str, Any]
    active_decision_ids: list[str]


@dataclass(frozen=True)
class ValidatedSuccessor(ValidatedOperation):
    current: dict[str, Any]
    current_status: str
    completion: dict[str, Any]
    completion_active_decision_ids: list[str]
    successor: dict[str, Any]
    successor_active_decision_ids: list[str]
    authorization: str


@dataclass(frozen=True)
class ValidatedWithdraw(ValidatedOperation):
    current: dict[str, Any]
    reason: str


def _seal_value(value: object) -> object:
    if isinstance(value, Target):
        return {
            "relay_id": value.relay_id,
            "expected_revision": value.expected_revision,
            "actual_revision": value.actual_revision,
        }
    if isinstance(value, Mapping):
        return {
            str(key): _seal_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_seal_value(item) for item in value]
    return value


def _operation_digest(operation: ValidatedOperation) -> str:
    payload = {
        key: _seal_value(value)
        for key, value in vars(operation).items()
        if key != "_seal"
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assert_validated_operation(operation: object) -> ValidatedOperation:
    if not isinstance(operation, ValidatedOperation):
        raise TypeError("executor 只接受 ValidatedOperation")
    if operation._seal != _operation_digest(operation):
        raise TypeError("ValidatedOperation 在 compile 之后被修改，拒绝执行")
    return operation


def _string(
    template: str | None = None,
    *,
    required: bool = True,
    nullable: bool = False,
    apply: str = "replace",
) -> FieldSpec:
    return FieldSpec(
        "string",
        required=required,
        nullable=nullable,
        template_source="placeholder" if template is not None else "constant",
        template_value=template if template is not None else MISSING,
        apply=apply,  # type: ignore[arg-type]
    )


def _integer(value: int) -> FieldSpec:
    return FieldSpec("integer", template_value=value)


def _object(
    fields: Mapping[str, FieldSpec],
    *,
    required: bool = True,
    nullable: bool = False,
    apply: str = "replace",
) -> FieldSpec:
    return FieldSpec(
        "object",
        required=required,
        nullable=nullable,
        fields=dict(fields),
        apply=apply,  # type: ignore[arg-type]
    )


def _array(
    item: FieldSpec,
    template: list[object] | None = None,
    *,
    required: bool = True,
) -> FieldSpec:
    return FieldSpec(
        "array",
        required=required,
        default_factory=list,
        item=item,
        template_value=template if template is not None else [],
    )


def _nullable_override(spec: FieldSpec) -> FieldSpec:
    return FieldSpec(
        spec.kind,
        required=True,
        nullable=True,
        fields=spec.fields,
        item=spec.item,
        variants=spec.variants,
        template_value=None,
        apply="inherit_if_null",
    )


TEXT_LIST = _array(_string(), [])
PATH_ITEM_SPEC = _object(
    {
        "path": _string("请填写项目相对路径"),
        "purpose": _string("请填写用途。"),
    }
)
DONE_STATUS_SPEC = _object(
    {
        "status": _string("pending"),
        "reason": _string(required=True, nullable=True),
    }
)
PHASE_SPEC = _object(
    {
        "name": _string("请填写当前阶段短名称。"),
        "outcome": _string("请填写当前阶段交付结果。"),
        "done_when": _array(
            _string(), ["请填写本阶段完成并可收棒的验收条件。"]
        ),
        "done_when_status": _array(
            DONE_STATUS_SPEC,
            [{"status": "pending", "reason": None}],
        ),
    }
)
NEW_PHASE_SPEC = _object(
    {
        "name": _string("请填写新阶段短名称。"),
        "outcome": _string("请填写新阶段交付结果。"),
        "done_when": _array(_string(), ["请填写新阶段完成标准。"]),
    }
)
DESIGN_SPEC = _object(
    {
        "outcome": _string("请填写用户最终应得到的结果。"),
        "why": _string("请填写这项工作的价值或原因。"),
        "non_goals": _array(_string(), ["请填写明确不做的事项。"]),
        "invariants": _array(_string(), ["请填写实现不得破坏的不变量。"]),
        "priorities": _array(_string(), ["请填写发生冲突时的优先级。"]),
    }
)
DECISION_SPEC = _object(
    {
        "id": _string("D-001"),
        "status": _string("tentative"),
        "label": _string("请填写决策短标签。"),
        "decision": _string("请填写仍影响实现的决策。"),
        "reason": _string("请填写理由。"),
        "rejected": TEXT_LIST,
        "reopen_when": _string("请填写重议条件。"),
    }
)
DECISION_TRANSITION_SPEC = _object(
    {
        "id": _string("D-001"),
        "action": _string("retire"),
        "reason": _string("请填写变更理由。"),
        "replacement": _string(required=True, nullable=True),
    }
)
CRITERIA_TRANSITION_SPEC = _object(
    {
        "field": _string("phase.done_when"),
        "id_or_text": _string("请填写原判据全文或新增判据全文。"),
        "action": _string("strengthened"),
        "replacement": _string(required=True, nullable=True),
        "reason": _string("请填写变更理由。"),
        "authorized_by": _string(required=True, nullable=True),
    }
)
AUTHORITY_SPEC = _object(
    {
        "may_decide": TEXT_LIST,
        "must_escalate": _array(
            _string(), ["请填写必须交回用户确认的变化。"]
        ),
        "must_not": _array(
            _string(), ["请填写接过这一棒的人明确不能做的事；没有则留空数组。"]
        ),
        "assumptions": TEXT_LIST,
        "unknowns": TEXT_LIST,
    }
)
STATE_SPEC = _object(
    {
        "completed": TEXT_LIST,
        "in_progress": _array(_string(), ["请填写当前正在推进的工作。"]),
        "evidence": TEXT_LIST,
    }
)
NEXT_STEP_SPEC = _object(
    {
        "purpose": _string("请填写下一步目的。"),
        "cwd": _string("."),
        "preconditions": _array(_string(), ["请填写前置条件。"]),
        "read": _array(
            PATH_ITEM_SPEC,
            [
                {
                    "path": "请填写项目相对路径",
                    "purpose": "请填写阅读目的。",
                }
            ],
        ),
        "modify": _array(PATH_ITEM_SPEC, []),
        "command_hint": _string("请填写起始命令提示。"),
        "expected": _string("请填写预期结果。"),
        "done_when": _string("请填写第一步完成标准。"),
        "failure": _string("请填写失败判定和下一条诊断动作。"),
    }
)
REMAINING_SPEC = _object({"p0": TEXT_LIST, "p1": TEXT_LIST, "p2": TEXT_LIST})
SNAPSHOT_SPEC = _object(
    {
        "title": _string("请填写任务标题"),
        "summary": _string("请填写当前有效状态，不写历史时间线。"),
        "phase": PHASE_SPEC,
        "design": DESIGN_SPEC,
        "decisions": _array(DECISION_SPEC, []),
        "authority": AUTHORITY_SPEC,
        "state": STATE_SPEC,
        "next_step": NEXT_STEP_SPEC,
        "remaining": REMAINING_SPEC,
        "deviations": TEXT_LIST,
        "references": _array(_string(), ["请填写相对路径、commit 或报告位置。"]),
    }
)
MATERIALIZED_PHASE_SPEC = _object(
    {
        **dict(PHASE_SPEC.fields or {}),
        "predecessor_relay_id": _string(required=True, nullable=True),
    }
)
CHANGES_SPEC = _object(
    {
        "active_decision_ids": _array(_string(), []),
        "decisions": _array(DECISION_TRANSITION_SPEC, []),
        "criteria": _array(CRITERIA_TRANSITION_SPEC, []),
    }
)
MATERIALIZED_REQUEST_SPEC = _object(
    {
        **dict(SNAPSHOT_SPEC.fields or {}),
        "phase": MATERIALIZED_PHASE_SPEC,
        "decision_transitions": _array(DECISION_TRANSITION_SPEC, []),
        "criteria_transitions": _array(CRITERIA_TRANSITION_SPEC, []),
        "authorization": _string(required=False, nullable=True),
    }
)
TARGET_SPEC = _object(
    {
        "relay_id": _string("请由 contextual draft 自动填写 Relay id。"),
        "expected_revision": _integer(1),
    },
    nullable=True,
)


def _snapshot_payload_spec() -> FieldSpec:
    return _object({"snapshot": SNAPSHOT_SPEC, "changes": CHANGES_SPEC})


SUCCESSOR_OVERRIDES_SPEC = _object(
    {
        "title": _nullable_override(_string()),
        "design": _nullable_override(DESIGN_SPEC),
        "decisions": _nullable_override(_array(DECISION_SPEC, [])),
        "authority": _object(
            {
                "may_decide": _nullable_override(TEXT_LIST),
                "must_escalate": _nullable_override(TEXT_LIST),
                "must_not": FieldSpec(
                    "array",
                    item=_string(),
                    template_value=[],
                    apply="clear",
                ),
                "assumptions": _nullable_override(TEXT_LIST),
                "unknowns": _nullable_override(TEXT_LIST),
            }
        ),
        "remaining": _nullable_override(REMAINING_SPEC),
        "references": _nullable_override(_array(_string(), [])),
    }
)
SUCCESSOR_NEXT_SPEC = _object(
    {
        "summary": _string("请填写新阶段当前状态。"),
        "phase": NEW_PHASE_SPEC,
        "next_step": NEXT_STEP_SPEC,
        "overrides": SUCCESSOR_OVERRIDES_SPEC,
        "changes": CHANGES_SPEC,
    }
)
SUCCESSOR_PAYLOAD_SPEC = _object(
    {
        "authorization": _string("请逐字填写用户授权开启下一阶段的原话。"),
        "completion": _snapshot_payload_spec(),
        "next": SUCCESSOR_NEXT_SPEC,
    }
)
WITHDRAW_PAYLOAD_SPEC = _object(
    {"reason": _string("请填写撤销错误接力棒的原因。")}
)


def _envelope_spec(operation: OperationName, payload: FieldSpec) -> FieldSpec:
    return _object(
        {
            "protocol": FieldSpec("integer", template_value=PROTOCOL_VERSION),
            "operation": FieldSpec("string", template_value=operation),
            "target": TARGET_SPEC,
            "payload": payload,
        }
    )


OPERATION_SPECS: dict[OperationName, OperationSpec] = {
    "create": OperationSpec(
        "create",
        "pass",
        _envelope_spec("create", _snapshot_payload_spec()),
        False,
        frozenset(),
        (),
    ),
    "update": OperationSpec(
        "update",
        "pass",
        _envelope_spec("update", _snapshot_payload_spec()),
        True,
        frozenset({"active"}),
        ("cas", "g1"),
    ),
    "done": OperationSpec(
        "done",
        "done",
        _envelope_spec("done", _snapshot_payload_spec()),
        True,
        frozenset({"active"}),
        ("cas", "g1", "phase_complete"),
    ),
    "successor": OperationSpec(
        "successor",
        "successor",
        _envelope_spec("successor", SUCCESSOR_PAYLOAD_SPEC),
        True,
        frozenset({"active", "done"}),
        ("cas", "phase_authorization", "g1", "phase_complete"),
    ),
    "withdraw": OperationSpec(
        "withdraw",
        "withdraw",
        _envelope_spec("withdraw", WITHDRAW_PAYLOAD_SPEC),
        True,
        frozenset({"active"}),
        ("cas",),
    ),
}


def operation_command(operation: object) -> CommandName:
    if not isinstance(operation, str) or operation not in OPERATION_SPECS:
        raise InvalidRequest(f"未知 operation：{operation}")
    return OPERATION_SPECS[operation].command  # type: ignore[index]


def _template_value(spec: FieldSpec) -> object:
    if spec.template_value is not MISSING:
        return deepcopy(spec.template_value)
    if spec.default is not MISSING:
        return deepcopy(spec.default)
    if spec.default_factory is not None:
        return spec.default_factory()
    if spec.nullable:
        return None
    if spec.kind == "object":
        return {}
    if spec.kind == "array":
        return []
    if spec.kind == "integer":
        return 0
    if spec.kind == "boolean":
        return False
    if spec.kind == "null":
        return None
    return ""


def emit_field(spec: FieldSpec, seed: object = MISSING) -> object:
    value = deepcopy(seed) if seed is not MISSING else _template_value(spec)
    if value is None:
        return None
    if spec.kind == "object":
        source = value if isinstance(value, Mapping) else {}
        return {
            name: emit_field(child, source.get(name, MISSING))
            for name, child in (spec.fields or {}).items()
        }
    if spec.kind == "array":
        if not isinstance(value, list):
            return []
        return [emit_field(spec.item or _string(), item) for item in value]
    return value


def _normalize(spec: FieldSpec, value: object, path: str) -> object:
    if value is None:
        if spec.nullable:
            return None
        raise InvalidRequest(f"{path} 不能是 null")
    if spec.kind == "object":
        if not isinstance(value, Mapping):
            raise InvalidRequest(f"{path} 必须是 object")
        fields = spec.fields or {}
        missing = sorted(
            name for name, child in fields.items() if child.required and name not in value
        )
        extra = sorted(set(value) - set(fields))
        if missing:
            raise InvalidRequest(f"{path} 缺少字段：{', '.join(missing)}")
        if extra:
            raise InvalidRequest(f"{path} 包含未知字段：{', '.join(extra)}")
        result: dict[str, object] = {}
        for name, child in fields.items():
            if name in value:
                result[name] = _normalize(child, value[name], f"{path}.{name}")
            elif child.default is not MISSING:
                result[name] = deepcopy(child.default)
            elif child.default_factory is not None:
                result[name] = child.default_factory()
        normalized: object = result
    elif spec.kind == "array":
        if not isinstance(value, list):
            raise InvalidRequest(f"{path} 必须是 array")
        normalized = [
            _normalize(spec.item or _string(), item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    elif spec.kind == "string":
        if not isinstance(value, str):
            raise InvalidRequest(f"{path} 必须是 string")
        normalized = value
    elif spec.kind == "integer":
        if type(value) is not int:
            raise InvalidRequest(f"{path} 必须是 integer")
        normalized = value
    elif spec.kind == "boolean":
        if type(value) is not bool:
            raise InvalidRequest(f"{path} 必须是 boolean")
        normalized = value
    elif spec.kind == "null":
        raise InvalidRequest(f"{path} 必须是 null")
    else:
        failures: list[Exception] = []
        for variant in spec.variants:
            try:
                return _normalize(variant, value, path)
            except InvalidRequest as error:
                failures.append(error)
        raise InvalidRequest(f"{path} 不匹配任何允许的类型") from failures[-1]
    if spec.normalizer is not None:
        return spec.normalizer(normalized, path)
    return normalized


def _public_snapshot(record: Mapping[str, Any]) -> dict[str, Any]:
    request = upgrade_legacy_request(
        request_from_snapshot(deepcopy(dict(record["snapshot"])))
    )
    request["phase"].pop("predecessor_relay_id", None)
    request.pop("decision_transitions", None)
    request.pop("criteria_transitions", None)
    return _normalize(SNAPSHOT_SPEC, request, "snapshot")  # type: ignore[return-value]


def _empty_changes() -> dict[str, list[object]]:
    return {"active_decision_ids": [], "decisions": [], "criteria": []}


def generate_draft(
    operation: OperationName | str,
    context: OperationContext | None,
) -> dict[str, Any]:
    try:
        spec = OPERATION_SPECS[operation]  # type: ignore[index]
    except KeyError as error:
        raise InvalidRequest(f"未知 operation：{operation}") from error
    if spec.target_required and context is None:
        raise InvalidRequest(f"{operation} 草稿需要活动 Relay 上下文")
    target = (
        None
        if context is None
        else {
            "relay_id": context.relay_id,
            "expected_revision": context.revision,
        }
    )
    if operation == "create":
        payload: dict[str, Any] = {
            "snapshot": emit_field(SNAPSHOT_SPEC),
            "changes": _empty_changes(),
        }
    elif operation in {"update", "done"}:
        assert context is not None
        payload = {
            "snapshot": emit_field(SNAPSHOT_SPEC, _public_snapshot(context.record)),
            "changes": _empty_changes(),
        }
    elif operation == "successor":
        assert context is not None
        payload = {
            "authorization": "请逐字填写用户授权开启下一阶段的原话。",
            "completion": {
                "snapshot": emit_field(
                    SNAPSHOT_SPEC, _public_snapshot(context.record)
                ),
                "changes": _empty_changes(),
            },
            "next": emit_field(SUCCESSOR_NEXT_SPEC),
        }
    else:
        payload = {"reason": "请填写撤销错误接力棒的原因。"}
    seed = {
        "protocol": PROTOCOL_VERSION,
        "operation": operation,
        "target": target,
        "payload": payload,
    }
    return emit_field(spec.envelope, seed)  # type: ignore[return-value]


def operation_object_paths(operation: OperationName | str) -> set[tuple[str, ...]]:
    try:
        spec = OPERATION_SPECS[operation]  # type: ignore[index]
    except KeyError as error:
        raise InvalidRequest(f"未知 operation：{operation}") from error
    paths: set[tuple[str, ...]] = set()

    def visit(field_spec: FieldSpec, prefix: tuple[str, ...]) -> None:
        if field_spec.kind != "object":
            return
        for name, child in (field_spec.fields or {}).items():
            path = (*prefix, name)
            paths.add(path)
            if child.kind == "object" and not child.nullable:
                visit(child, path)

    visit(spec.envelope, ())
    return paths


def operation_item_field_paths(
    operation: OperationName | str,
) -> set[tuple[str, ...]]:
    try:
        spec = OPERATION_SPECS[operation]  # type: ignore[index]
    except KeyError as error:
        raise InvalidRequest(f"未知 operation：{operation}") from error
    paths: set[tuple[str, ...]] = set()

    def visit(field_spec: FieldSpec, prefix: tuple[str, ...]) -> None:
        if field_spec.kind == "object":
            for name, child in (field_spec.fields or {}).items():
                visit(child, (*prefix, name))
            return
        if field_spec.kind != "array" or field_spec.item is None:
            return
        item_prefix = (*prefix, "[]")
        if field_spec.item.kind == "object":
            for name, child in (field_spec.item.fields or {}).items():
                paths.add((*item_prefix, name))
                visit(child, (*item_prefix, name))
        else:
            paths.add(item_prefix)

    visit(spec.envelope, ())
    return paths


def materialized_object_fields(path: tuple[str, ...]) -> set[str]:
    spec = MATERIALIZED_REQUEST_SPEC
    for component in path:
        if component == "[]":
            if spec.kind != "array" or spec.item is None:
                raise ValueError(f"不是 array spec 路径：{path}")
            spec = spec.item
            continue
        if spec.kind != "object" or component not in (spec.fields or {}):
            raise ValueError(f"未知 materialized request spec 路径：{path}")
        spec = (spec.fields or {})[component]
    if spec.kind != "object":
        raise ValueError(f"不是 object spec 路径：{path}")
    return set(spec.fields or {})


def validate_materialized_request_shape(request: Mapping[str, Any]) -> None:
    _normalize(MATERIALIZED_REQUEST_SPEC, request, "request")


def _target(
    spec: OperationSpec,
    envelope: Mapping[str, Any],
    context: OperationContext | None,
) -> Target | None:
    from .validation import validate_relay_id

    raw_target = envelope["target"]
    if not spec.target_required:
        if raw_target is not None:
            raise InvalidRequest("create.target 必须是 null")
        if context is not None:
            raise InvalidRequest("create operation 不能绑定现有 Relay")
        return None
    if context is None or raw_target is None:
        raise InvalidRequest(f"{spec.name}.target 需要现有 Relay 上下文")
    if context.status not in spec.allowed_target_statuses:
        raise InvalidRequest(
            f"{spec.name} 不能作用于 {context.status} Relay"
        )
    relay_id = raw_target["relay_id"]
    validate_relay_id(relay_id)
    expected_revision = raw_target["expected_revision"]
    if relay_id != context.relay_id:
        raise InvalidRequest(
            f"target.relay_id 与当前 Relay 不一致：{relay_id} != {context.relay_id}"
        )
    if expected_revision < 1:
        raise InvalidRequest("target.expected_revision 必须是正整数")
    if "cas" in spec.gates and expected_revision != context.revision:
        raise StaleRevision(
            "Relay revision 已变化："
            f"expected {expected_revision}, actual {context.revision}；请重新生成草稿",
            details={
                "relay_id": relay_id,
                "expected_revision": expected_revision,
                "actual_revision": context.revision,
            },
        )
    return Target(relay_id, expected_revision, context.revision)


def _request_from_parts(
    snapshot: Mapping[str, Any],
    changes: Mapping[str, Any],
    *,
    predecessor_relay_id: str | None,
) -> dict[str, Any]:
    from .validation import validate_request

    normalized_snapshot = _normalize(SNAPSHOT_SPEC, snapshot, "payload.snapshot")
    normalized_changes = _normalize(CHANGES_SPEC, changes, "payload.changes")
    request = deepcopy(normalized_snapshot)
    request["phase"]["predecessor_relay_id"] = predecessor_relay_id
    request["decision_transitions"] = deepcopy(normalized_changes["decisions"])
    request["criteria_transitions"] = deepcopy(normalized_changes["criteria"])
    validate_request(request)
    return request


def validate_phase_complete(request: Mapping[str, Any]) -> None:
    if request["remaining"]["p0"]:
        raise UnresolvedP0(
            "Relay 仍有未解决 P0；请在本次 completion.remaining.p0 中清理后再归档",
            details={"items": deepcopy(request["remaining"]["p0"])},
        )
    if request["deviations"]:
        raise UnapprovedDeviation("Relay 仍有未批准偏差；批准并更新后才能归档")
    state = request["state"]
    if not state["completed"]:
        raise IncompleteRelay("Relay 缺少已完成事项，不能归档")
    if not state["evidence"]:
        raise IncompleteRelay("Relay 缺少完成验证证据，不能归档")
    if state["in_progress"]:
        raise IncompleteRelay("Relay 仍有进行中事项，不能归档")
    pending = [
        index
        for index, item in enumerate(request["phase"]["done_when_status"], start=1)
        if item["status"] == "pending"
    ]
    if pending:
        raise IncompleteRelay(
            "Relay 仍有未声明完成结果的 phase.done_when："
            + ", ".join(str(index) for index in pending)
        )


def _apply_field(spec: FieldSpec, base: object, override: object) -> object:
    if spec.apply in {"inherit_if_null", "copy_from_completion_if_null"}:
        if override is None:
            return deepcopy(base)
    if spec.kind == "object" and isinstance(override, Mapping):
        base_fields = base if isinstance(base, Mapping) else {}
        return {
            name: _apply_field(
                child,
                base_fields.get(name),
                override[name],
            )
            for name, child in (spec.fields or {}).items()
        }
    return deepcopy(override)


def _materialize_successor(
    current: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    relay_id: str,
    current_status: str,
    gates: tuple[str, ...],
) -> tuple[dict[str, Any], list[str], dict[str, Any], list[str], str]:
    from .validation import (
        DESIGN_CRITERIA_FIELDS,
        validate_authorization,
        validate_criteria_transitions,
        validate_no_secrets,
        validate_request,
    )

    if "phase_authorization" in gates:
        try:
            authorization = validate_authorization(
                payload["authorization"], path="payload.authorization"
            )
        except InvalidRequest as error:
            raise PhaseAuthorizationRequired(
                str(error),
                details={"operation": "successor", "relay_id": relay_id},
            ) from error
    else:
        authorization = str(payload["authorization"])
    completion_payload = payload["completion"]
    if current_status == "done" and (
        completion_payload["snapshot"] != _public_snapshot(current)
        or completion_payload["changes"]["decisions"]
        or completion_payload["changes"]["criteria"]
    ):
        raise InvalidRequest(
            "已归档 Relay 的 completion 是只读上下文；"
            "请只填写授权原话与新阶段内容"
        )
    completion = _request_from_parts(
        completion_payload["snapshot"],
        completion_payload["changes"],
        predecessor_relay_id=current["lineage"]["predecessor_relay_id"],
    )
    if current_status == "active" and "g1" in gates:
        validate_criteria_transitions(current["snapshot"], completion)
    if current_status == "active" and "phase_complete" in gates:
        validate_phase_complete(completion)
    if current_status == "done" and "g1" in gates:
        validate_criteria_transitions(
            current["snapshot"],
            completion,
            protected_fields=DESIGN_CRITERIA_FIELDS,
        )

    next_payload = payload["next"]
    overrides = next_payload["overrides"]
    override_specs = SUCCESSOR_OVERRIDES_SPEC.fields or {}
    successor = {
        "title": _apply_field(
            override_specs["title"], completion["title"], overrides["title"]
        ),
        "summary": deepcopy(next_payload["summary"]),
        "phase": {
            **deepcopy(next_payload["phase"]),
            "done_when_status": [
                {"status": "pending", "reason": None}
                for _ in next_payload["phase"]["done_when"]
            ],
            "predecessor_relay_id": relay_id,
        },
        "design": _apply_field(
            override_specs["design"], completion["design"], overrides["design"]
        ),
        "decisions": _apply_field(
            override_specs["decisions"],
            completion["decisions"],
            overrides["decisions"],
        ),
        "decision_transitions": deepcopy(next_payload["changes"]["decisions"]),
        "criteria_transitions": deepcopy(next_payload["changes"]["criteria"]),
        "authority": _apply_field(
            override_specs["authority"],
            completion["authority"],
            overrides["authority"],
        ),
        "state": {"completed": [], "in_progress": [], "evidence": []},
        "next_step": deepcopy(next_payload["next_step"]),
        "remaining": _apply_field(
            override_specs["remaining"],
            completion["remaining"],
            overrides["remaining"],
        ),
        "deviations": [],
        "references": _apply_field(
            override_specs["references"],
            completion["references"],
            overrides["references"],
        ),
    }
    validate_request(successor)
    if "g1" in gates:
        validate_criteria_transitions(
            completion,
            successor,
            protected_fields=DESIGN_CRITERIA_FIELDS,
        )
    validate_no_secrets(payload, label="Relay successor 请求")
    return (
        completion,
        deepcopy(completion_payload["changes"]["active_decision_ids"]),
        successor,
        deepcopy(next_payload["changes"]["active_decision_ids"]),
        authorization,
    )


def compile_operation(
    raw_request: Mapping[str, object],
    context: OperationContext | None,
) -> ValidatedOperation:
    if not isinstance(raw_request, Mapping):
        raise InvalidRequest("Relay 请求必须是 JSON object")
    operation = raw_request.get("operation")
    if not isinstance(operation, str) or operation not in OPERATION_SPECS:
        raise InvalidRequest(f"未知 operation：{operation}")
    spec = OPERATION_SPECS[operation]  # type: ignore[index]
    envelope = _normalize(spec.envelope, raw_request, "request")
    assert isinstance(envelope, dict)
    if envelope["protocol"] != PROTOCOL_VERSION:
        raise InvalidRequest(
            f"request.protocol 必须是 {PROTOCOL_VERSION}"
        )
    if envelope["operation"] != spec.name:
        raise InvalidRequest("request.operation 与选择的协议不一致")
    target = _target(spec, envelope, context)
    payload = envelope["payload"]
    assert isinstance(payload, dict)

    if operation == "create":
        snapshot = _request_from_parts(
            payload["snapshot"], payload["changes"], predecessor_relay_id=None
        )
        if snapshot["criteria_transitions"]:
            raise InvalidRequest("根 Relay 不能包含 criteria_transitions")
        return ValidatedCreate(
            "create",
            target,
            snapshot,
            deepcopy(payload["changes"]["active_decision_ids"]),
            _compile_token=_COMPILE_TOKEN,
        )

    assert context is not None and target is not None
    current = deepcopy(dict(context.record))
    if operation in {"update", "done"}:
        from .validation import validate_criteria_transitions

        snapshot = _request_from_parts(
            payload["snapshot"],
            payload["changes"],
            predecessor_relay_id=current["lineage"]["predecessor_relay_id"],
        )
        if "g1" in spec.gates:
            validate_criteria_transitions(current["snapshot"], snapshot)
        if operation == "done":
            if "phase_complete" in spec.gates:
                validate_phase_complete(snapshot)
            return ValidatedDone(
                "done",
                target,
                current,
                snapshot,
                deepcopy(payload["changes"]["active_decision_ids"]),
                _compile_token=_COMPILE_TOKEN,
            )
        return ValidatedUpdate(
            "update",
            target,
            current,
            snapshot,
            deepcopy(payload["changes"]["active_decision_ids"]),
            _compile_token=_COMPILE_TOKEN,
        )
    if operation == "successor":
        (
            completion,
            completion_active_decision_ids,
            successor,
            successor_active_decision_ids,
            authorization,
        ) = _materialize_successor(
            current,
            payload,
            relay_id=context.relay_id,
            current_status=context.status,
            gates=spec.gates,
        )
        return ValidatedSuccessor(
            "successor",
            target,
            current,
            context.status,
            completion,
            completion_active_decision_ids,
            successor,
            successor_active_decision_ids,
            authorization,
            _compile_token=_COMPILE_TOKEN,
        )

    from .validation import validate_withdraw_reason

    reason = validate_withdraw_reason(payload["reason"])
    return ValidatedWithdraw(
        "withdraw",
        target,
        current,
        reason,
        _compile_token=_COMPILE_TOKEN,
    )


def request_template_from_spec() -> dict[str, Any]:
    request = emit_field(MATERIALIZED_REQUEST_SPEC)
    assert isinstance(request, dict)
    request.pop("authorization", None)
    return request


def successor_template_from_spec() -> dict[str, Any]:
    draft = generate_draft(
        "successor",
        OperationContext(
            relay_id="20260801-000000-00000000",
            revision=1,
            status="active",
            record={
                "lineage": {"predecessor_relay_id": None},
                "snapshot": {
                    **request_template_from_spec(),
                    "phase": {
                        **request_template_from_spec()["phase"],
                        "phase_id": "20260801-000000-00000000",
                    },
                },
            },
        ),
    )
    payload = draft["payload"]
    completion = deepcopy(payload["completion"]["snapshot"])
    completion["decision_transitions"] = payload["completion"]["changes"][
        "decisions"
    ]
    completion["criteria_transitions"] = payload["completion"]["changes"][
        "criteria"
    ]
    return {
        "authorization": payload["authorization"],
        "completion": completion,
        "successor": {
            "summary": payload["next"]["summary"],
            "phase": payload["next"]["phase"],
            "next_step": payload["next"]["next_step"],
        },
    }

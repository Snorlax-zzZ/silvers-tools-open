from __future__ import annotations

import json
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Iterable
import unicodedata

from .constants import (
    MAX_AUTHORIZATION_BYTES,
    MAX_REQUEST_BYTES,
)
from .errors import (
    CriteriaTransitionRequired,
    InvalidRelayId,
    InvalidRequest,
    RequestTooLarge,
    SecretDetected,
)


SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(
        r"(?i)\b(?:api[\s_-]*key|token|password|cookie)\s*[:=]\s*(?!<REDACTED>)[^\s]{12,}"
    ),
)
RELAY_ID_PATTERN = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{8}")
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}")
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MAX_FIELD_BYTES = 32 * 1024
PROTECTED_CRITERIA_FIELDS = frozenset(
    {
        "phase.outcome",
        "phase.done_when",
        "design.invariants",
        "design.non_goals",
    }
)
DESIGN_CRITERIA_FIELDS = frozenset(
    {"design.invariants", "design.non_goals"}
)


def request_template() -> dict[str, Any]:
    # 模板、operation 校验和 materialize 共用 protocol.FieldSpec；这里仅保留
    # 旧内部调用名，避免模板再维护第二份字段表。
    from .protocol import request_template_from_spec

    return request_template_from_spec()


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidRequest(f"{path} 必须是 object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise InvalidRequest(f"{path} 必须是 array")
    return value


def _require_text(value: Any, path: str, *, max_bytes: int = MAX_FIELD_BYTES) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequest(f"{path} 必须是非空字符串")
    if (
        "\r" in value
        or "\n" in value
        or CONTROL_PATTERN.search(value)
        or any(
            unicodedata.category(character) in {"Cc", "Zl", "Zp"} for character in value
        )
    ):
        raise InvalidRequest(f"{path} 必须是单行文本且不能包含控制字符")
    encoded_size = len(value.encode("utf-8"))
    if encoded_size > max_bytes:
        raise InvalidRequest(f"{path} 超过 {max_bytes} bytes：{encoded_size}")
    return value.strip()


def validate_authorization(value: Any, *, path: str) -> str:
    """校验用户授权开启下一阶段的原话。

    开不开新阶段是用户的决定，不是模型能自行判断的事：模型可以建议，但
    用户没点头就只能更新同一根棒。CLI 无法证明这段话真的出自用户，这里
    做的是强制留痕并挡掉"看起来像填了"的写法——让自行开新阶段至少要经过
    一次显式伪造，而不是顺手就能走通。
    """

    if not isinstance(value, str):
        raise InvalidRequest(f"{path} 必须是字符串")
    if not value.strip():
        raise InvalidRequest(
            f"{path} 为空：用户没有明确授权开启下一阶段时不得开启新阶段，"
            "只能用 pass 更新同一根棒"
        )
    text = _require_text(value, path, max_bytes=MAX_AUTHORIZATION_BYTES)
    # 零宽字符属于 Cf，strip() 去不掉、也不算控制字符，足够拼出一条渲染出来
    # 完全空白却能通过校验的"授权"。剥掉全部格式字符后必须仍有实际内容。
    visible = "".join(
        character
        for character in text
        if unicodedata.category(character) != "Cf"
    )
    if not visible.strip():
        raise InvalidRequest(f"{path} 不能只由不可见字符组成")
    if "请逐字填写" in text or "请填写" in text:
        raise InvalidRequest(
            f"{path} 仍是模板占位文本；必须逐字填写用户授权开启下一阶段的原话"
        )
    return text


def validate_relay_id(relay_id: str) -> str:
    if not RELAY_ID_PATTERN.fullmatch(relay_id):
        raise InvalidRelayId("Relay id 格式非法")
    return relay_id


def validate_writer_metadata(client: str, model: str) -> None:
    try:
        client_bytes = client.encode("utf-8")
    except UnicodeEncodeError:
        client_bytes = b""
    if (
        not client_bytes
        or len(client_bytes) > 64
        or not client[0].isalnum()
        or any(
            not character.isalnum() and character not in "._-"
            for character in client
        )
    ):
        raise InvalidRequest(
            "client 格式非法；仅允许 1–64 个 UTF-8 字节的 Unicode 字母、数字、点、下划线和连字符"
        )
    if not MODEL_PATTERN.fullmatch(model):
        raise InvalidRequest("model 格式非法；仅允许安全的模型标识字符且最多 128 位")


def validate_withdraw_reason(reason: Any) -> str:
    normalized = _require_text(reason, "withdraw reason", max_bytes=1024)
    validate_no_secrets(normalized, label="Relay 撤销原因")
    return normalized


def _check_keys(value: dict[str, Any], required: set[str], path: str) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required)
    if missing:
        raise InvalidRequest(f"{path} 缺少字段：{', '.join(missing)}")
    if extra:
        raise InvalidRequest(f"{path} 包含未知字段：{', '.join(extra)}")


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_strings(nested)


def validate_no_secrets(value: Any, *, label: str) -> None:
    for text in _walk_strings(value):
        scannable = text.replace("<REDACTED>", "")
        if any(pattern.search(scannable) for pattern in SECRET_PATTERNS):
            raise SecretDetected(f"{label}疑似包含密钥或凭据；请移除或改用 <REDACTED>")


def _text_list(value: Any, path: str, *, allow_empty: bool = True) -> list[str]:
    items = _require_list(value, path)
    if len(items) > 32:
        raise InvalidRequest(f"{path} 最多 32 项")
    normalized = [
        _require_text(item, f"{path}[{index}]") for index, item in enumerate(items)
    ]
    if not allow_empty and not normalized:
        raise InvalidRequest(f"{path} 不能为空")
    return normalized


def _require_relative_path(value: Any, path: str) -> str:
    normalized = _require_text(value, path, max_bytes=1024)
    windows_path = PureWindowsPath(normalized)
    posix_path = PurePosixPath(normalized)
    if (
        normalized.startswith(("/", "\\"))
        or windows_path.is_absolute()
        or windows_path.drive
        or posix_path.is_absolute()
        or ".." in windows_path.parts
        or ".." in posix_path.parts
        or "\\" in normalized
    ):
        raise InvalidRequest(f"{path} 必须是使用 / 的项目相对路径，且不能包含 ..")
    return normalized


def _path_items(value: Any, path: str, *, allow_empty: bool = False) -> None:
    from .protocol import materialized_object_fields

    items = _require_list(value, path)
    if len(items) > 32:
        raise InvalidRequest(f"{path} 最多 32 项")
    if not allow_empty and not items:
        raise InvalidRequest(f"{path} 不能为空")
    for index, raw_item in enumerate(items):
        item = _require_object(raw_item, f"{path}[{index}]")
        _check_keys(
            item,
            materialized_object_fields(("next_step", "read", "[]")),
            f"{path}[{index}]",
        )
        _require_relative_path(item["path"], f"{path}[{index}].path")
        _require_text(item["purpose"], f"{path}[{index}].purpose")


def _validate_done_when_status(
    value: Any,
    done_when: list[str],
    *,
    path: str = "phase.done_when_status",
) -> list[dict[str, Any]]:
    from .protocol import materialized_object_fields

    items = _require_list(value, path)
    if len(items) != len(done_when):
        raise InvalidRequest(
            f"{path} 必须与 phase.done_when 逐条对齐："
            f"expected {len(done_when)}, actual {len(items)}"
        )
    normalized: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        item_path = f"{path}[{index}]"
        item = _require_object(raw_item, item_path)
        _check_keys(
            item,
            materialized_object_fields(("phase", "done_when_status", "[]")),
            item_path,
        )
        status = _require_text(
            item["status"],
            f"{item_path}.status",
            max_bytes=16,
        )
        if (
            status != item["status"]
            or status
            not in {"pending", "met", "partial", "unverifiable"}
        ):
            raise InvalidRequest(
                f"{item_path}.status 必须是 pending、met、partial 或 unverifiable"
            )
        reason = item["reason"]
        if status in {"partial", "unverifiable"}:
            reason = _require_text(
                reason,
                f"{item_path}.reason",
                max_bytes=1024,
            )
        elif reason is not None:
            raise InvalidRequest(
                f"{item_path}.reason 在 {status} 时必须是 null"
            )
        normalized.append({"status": status, "reason": reason})
    return normalized


def validate_request(
    request: dict[str, Any],
    *,
    allow_legacy_phase_status: bool = False,
    allow_legacy_baton_limits: bool = False,
) -> dict[str, Any]:
    from .protocol import (
        materialized_object_fields,
        validate_materialized_request_shape,
    )

    raw_size = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
    if raw_size > MAX_REQUEST_BYTES:
        raise RequestTooLarge(
            f"请求 JSON 超过 {MAX_REQUEST_BYTES} bytes：{raw_size}",
            details={
                "request_bytes": raw_size,
                "max_request_bytes": MAX_REQUEST_BYTES,
            },
        )

    if not allow_legacy_phase_status and not allow_legacy_baton_limits:
        validate_materialized_request_shape(request)
    top_level_fields = materialized_object_fields(())
    required_top_level_fields = top_level_fields - {"authorization"}
    # authorization 是本次写入的准入证明，不进 snapshot；它在协议字段表里是
    # optional，模板、shape 校验和执行因此不会各自维护一份字段名单。
    missing = sorted(required_top_level_fields - request.keys())
    if missing:
        raise InvalidRequest(f"request 缺少字段：{', '.join(missing)}")
    extra = sorted(request.keys() - top_level_fields)
    if extra:
        raise InvalidRequest(f"request 包含未知字段：{', '.join(extra)}")
    _require_text(request["title"], "title", max_bytes=160)
    _require_text(request["summary"], "summary")

    phase = _require_object(request["phase"], "phase")
    phase_fields = materialized_object_fields(("phase",))
    if not allow_legacy_phase_status or "done_when_status" in phase:
        phase_fields.add("done_when_status")
    else:
        phase_fields.discard("done_when_status")
    _check_keys(phase, phase_fields, "phase")
    _require_text(phase["name"], "phase.name", max_bytes=96)
    _require_text(phase["outcome"], "phase.outcome", max_bytes=1024)
    done_when = _text_list(
        phase["done_when"],
        "phase.done_when",
        allow_empty=False,
    )
    if "done_when_status" in phase:
        _validate_done_when_status(phase["done_when_status"], done_when)
    predecessor = phase["predecessor_relay_id"]
    if predecessor is not None:
        if not isinstance(predecessor, str):
            raise InvalidRequest("phase.predecessor_relay_id 必须是 Relay id 或 null")
        validate_relay_id(predecessor)
    # authorization 只做格式校验。"带 predecessor 就必须有授权"是**写入准入**
    # 规则，不是数据合法性规则——放在这里会连读路径一起误伤：
    # _validate_record_pair 会把磁盘 snapshot 还原成 request 再校验，而 snapshot
    # 里从不保存 authorization，于是每一根有前序阶段的存量棒都会读不出来。
    # 新写入的准入检查由 protocol.compile_operation 按 operation 执行。
    if "authorization" in request and request["authorization"] is not None:
        validate_authorization(
            request["authorization"], path="request.authorization"
        )

    design = _require_object(request["design"], "design")
    _check_keys(design, materialized_object_fields(("design",)), "design")
    _require_text(design["outcome"], "design.outcome")
    _require_text(design["why"], "design.why")
    _text_list(design["non_goals"], "design.non_goals", allow_empty=False)
    _text_list(design["invariants"], "design.invariants", allow_empty=False)
    _text_list(design["priorities"], "design.priorities", allow_empty=False)

    decisions = _require_list(request["decisions"], "decisions")
    decision_ids: set[str] = set()
    for index, raw_decision in enumerate(decisions):
        decision = _require_object(raw_decision, f"decisions[{index}]")
        _check_keys(
            decision,
            materialized_object_fields(("decisions", "[]")),
            f"decisions[{index}]",
        )
        decision_id = _require_text(decision["id"], f"decisions[{index}].id")
        if not re.fullmatch(r"D-[0-9]{3}", decision_id):
            raise InvalidRequest(f"decisions[{index}].id 必须匹配 D-000")
        if decision_id in decision_ids:
            raise InvalidRequest(f"重复 decision id：{decision_id}")
        decision_ids.add(decision_id)
        _require_text(decision["label"], f"decisions[{index}].label")
        status = _require_text(
            decision["status"], f"decisions[{index}].status", max_bytes=16
        )
        if status != decision["status"] or status not in {
            "locked",
            "tentative",
            "reopenable",
        }:
            raise InvalidRequest(f"decisions[{index}].status 非法")
        for field in ("decision", "reason", "reopen_when"):
            _require_text(decision[field], f"decisions[{index}].{field}")
        _text_list(decision["rejected"], f"decisions[{index}].rejected")

    transitions = _require_list(
        request["decision_transitions"], "decision_transitions"
    )
    transitioned_ids: set[str] = set()
    for index, raw_transition in enumerate(transitions):
        transition = _require_object(
            raw_transition, f"decision_transitions[{index}]"
        )
        _check_keys(
            transition,
            materialized_object_fields(("decision_transitions", "[]")),
            f"decision_transitions[{index}]",
        )
        transition_id = _require_text(
            transition["id"], f"decision_transitions[{index}].id"
        )
        if not re.fullmatch(r"D-[0-9]{3}", transition_id):
            raise InvalidRequest(
                f"decision_transitions[{index}].id 必须匹配 D-000"
            )
        if transition_id in transitioned_ids:
            raise InvalidRequest(f"重复 decision transition id：{transition_id}")
        transitioned_ids.add(transition_id)
        action = _require_text(
            transition["action"],
            f"decision_transitions[{index}].action",
            max_bytes=16,
        )
        if action not in {"retire", "supersede"}:
            raise InvalidRequest(
                f"decision_transitions[{index}].action 必须是 retire 或 supersede"
            )
        _require_text(
            transition["reason"], f"decision_transitions[{index}].reason"
        )
        replacement = transition["replacement"]
        if action == "retire" and replacement is not None:
            raise InvalidRequest(
                f"decision_transitions[{index}].replacement 在 retire 时必须是 null"
            )
        if action == "supersede":
            if not isinstance(replacement, str) or not re.fullmatch(
                r"D-[0-9]{3}", replacement
            ):
                raise InvalidRequest(
                    f"decision_transitions[{index}].replacement 必须是 D-000"
                )

    criteria_transitions = _require_list(
        request["criteria_transitions"], "criteria_transitions"
    )
    if len(criteria_transitions) > 32:
        raise InvalidRequest("criteria_transitions 最多包含 32 项")
    seen_criteria: set[tuple[str, str]] = set()
    for index, raw_transition in enumerate(criteria_transitions):
        path = f"criteria_transitions[{index}]"
        transition = _require_object(raw_transition, path)
        _check_keys(
            transition,
            materialized_object_fields(("criteria_transitions", "[]")),
            path,
        )
        field = _require_text(transition["field"], f"{path}.field", max_bytes=32)
        if field not in PROTECTED_CRITERIA_FIELDS:
            raise InvalidRequest(f"{path}.field 不是受保护的阶段判据字段")
        old_text = _require_text(transition["id_or_text"], f"{path}.id_or_text")
        key = (field, old_text)
        if key in seen_criteria:
            raise InvalidRequest(f"重复 criteria transition：{field} / {old_text}")
        seen_criteria.add(key)
        action = _require_text(
            transition["action"], f"{path}.action", max_bytes=16
        )
        if action not in {
            "removed",
            "weakened",
            "merged_into",
            "strengthened",
            "added",
        }:
            raise InvalidRequest(
                f"{path}.action 必须是 removed、weakened、merged_into、"
                "strengthened 或 added"
            )
        replacement = transition["replacement"]
        if action in {"removed", "added"}:
            if replacement is not None:
                raise InvalidRequest(
                    f"{path}.replacement 在 {action} 时必须是 null"
                )
        else:
            _require_text(replacement, f"{path}.replacement")
        _require_text(transition["reason"], f"{path}.reason")
        authorized_by = transition["authorized_by"]
        requires_authorization = action in {
            "removed",
            "weakened",
            "merged_into",
        } or (action == "added" and field == "design.non_goals")
        if requires_authorization:
            _require_text(
                authorized_by,
                f"{path}.authorized_by",
                max_bytes=256,
            )
        elif authorized_by is not None:
            raise InvalidRequest(
                f"{path}.authorized_by 在 {action} 时必须是 null"
            )
        if action == "strengthened" and field == "design.non_goals":
            raise InvalidRequest(
                f"{path}.action 不能用 strengthened 改写 design.non_goals；"
                "非目标变化必须由用户明确授权"
            )
        if action == "added" and field == "phase.outcome":
            raise InvalidRequest(
                f"{path}.action 不能向单值字段 phase.outcome 添加条目"
            )

    authority_fields = materialized_object_fields(("authority",))
    if allow_legacy_baton_limits:
        # schema 6 之前的存量档案没有 must_not。读旧棒时必须放宽，否则
        # 所有历史档案会在读取阶段就被拒——写得进磁盘、后来打不开。
        authority_fields -= {"must_not"}
    object_lists = {
        "authority": authority_fields,
        "state": materialized_object_fields(("state",)),
        "remaining": materialized_object_fields(("remaining",)),
    }
    for object_name, fields in object_lists.items():
        value = _require_object(request[object_name], object_name)
        _check_keys(value, fields, object_name)
        for field in fields:
            _text_list(value[field], f"{object_name}.{field}")

    next_step = _require_object(request["next_step"], "next_step")
    next_fields = materialized_object_fields(("next_step",))
    _check_keys(next_step, next_fields, "next_step")
    for field in (
        "purpose",
        "command_hint",
        "expected",
        "done_when",
        "failure",
    ):
        _require_text(next_step[field], f"next_step.{field}")
    _require_relative_path(next_step["cwd"], "next_step.cwd")
    _text_list(next_step["preconditions"], "next_step.preconditions", allow_empty=False)
    _path_items(next_step["read"], "next_step.read")
    _path_items(next_step["modify"], "next_step.modify", allow_empty=True)

    _text_list(request["deviations"], "deviations")
    _text_list(request["references"], "references", allow_empty=False)

    validate_no_secrets(request, label="Relay 请求")
    return request


def _protected_criteria(snapshot: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "phase.outcome": [snapshot["phase"]["outcome"]],
        "phase.done_when": list(snapshot["phase"]["done_when"]),
        "design.invariants": list(snapshot["design"]["invariants"]),
        "design.non_goals": list(snapshot["design"]["non_goals"]),
    }


def validate_criteria_transitions(
    previous_snapshot: dict[str, Any],
    request: dict[str, Any],
    *,
    protected_fields: frozenset[str] = PROTECTED_CRITERIA_FIELDS,
) -> None:
    unknown = protected_fields - PROTECTED_CRITERIA_FIELDS
    if unknown:
        raise ValueError(f"未知判据保护范围：{sorted(unknown)}")
    out_of_scope = sorted(
        {
            transition["field"]
            for transition in request["criteria_transitions"]
            if transition["field"] not in protected_fields
        }
    )
    if out_of_scope:
        raise InvalidRequest(
            "本操作不接受这些 criteria transition 字段："
            + ", ".join(out_of_scope)
        )
    previous = {
        field: items
        for field, items in _protected_criteria(previous_snapshot).items()
        if field in protected_fields
    }
    current = {
        field: items
        for field, items in _protected_criteria(request).items()
        if field in protected_fields
    }
    transitions = {
        (transition["field"], transition["id_or_text"]): transition
        for transition in request["criteria_transitions"]
    }
    missing: list[dict[str, str]] = []
    used: set[tuple[str, str]] = set()
    replacement_targets: dict[str, set[str]] = {
        field: set() for field in previous
    }
    for field, old_items in previous.items():
        for old_text in old_items:
            if old_text in current[field]:
                continue
            key = (field, old_text)
            transition = transitions.get(key)
            if transition is None or transition["action"] == "added":
                missing.append(
                    {
                        "field": field,
                        "text": old_text,
                        "change": "removed_or_changed",
                    }
                )
                continue
            replacement = transition["replacement"]
            if transition["action"] != "removed" and replacement not in current[field]:
                raise InvalidRequest(
                    f"{field} 的 criteria transition replacement "
                    "必须与本次请求中的当前条目完全一致"
                )
            if replacement is not None:
                replacement_targets[field].add(replacement)
            used.add(key)

    for field, current_items in current.items():
        if field == "phase.outcome":
            continue
        for current_text in current_items:
            if (
                current_text in previous[field]
                or current_text in replacement_targets[field]
            ):
                continue
            key = (field, current_text)
            transition = transitions.get(key)
            if transition is None or transition["action"] != "added":
                missing.append(
                    {
                        "field": field,
                        "text": current_text,
                        "change": "added",
                    }
                )
                continue
            used.add(key)

    unused = sorted(set(transitions) - used)
    if unused:
        field, criterion_text = unused[0]
        raise InvalidRequest(
            "criteria transition 未对应实际判据变化："
            f"{field} / {criterion_text}"
        )
    if missing:
        raise CriteriaTransitionRequired(
            "受保护的阶段判据被删除、改写或新增；"
            "必须显式登记 criteria_transitions",
            details={
                "missing": missing,
                "fields": sorted({item["field"] for item in missing}),
                "suggested_action": (
                    "保持文本完全一致；收紧或新增正向约束时登记 "
                    "strengthened/added，删除、弱化、合并或新增 non-goal "
                    "必须先取得用户明确授权"
                ),
            },
        )

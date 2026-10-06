from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping, Sequence

from .errors import InvalidRequest
from .protocol import (
    CRITERIA_TRANSITION_SPEC,
    DECISION_SPEC,
    DECISION_TRANSITION_SPEC,
    SNAPSHOT_SPEC,
    _normalize,
)
from .validation import validate_relay_id


_DECISION_ID = re.compile(r"D-([0-9]{3})")
_DECISION_STATUSES = {"locked", "tentative", "reopenable"}
_DECISION_ACTIONS = {"retire", "supersede"}


def _decision_number(decision_id: object, path: str) -> int:
    if not isinstance(decision_id, str):
        raise InvalidRequest(f"{path} 必须是 D-000")
    matched = _DECISION_ID.fullmatch(decision_id)
    if matched is None or int(matched.group(1)) < 1:
        raise InvalidRequest(f"{path} 必须匹配 D-001 至 D-999")
    return int(matched.group(1))


def _normalized_decisions(
    decisions: Sequence[Mapping[str, Any]],
    path: str,
) -> list[dict[str, Any]]:
    if not isinstance(decisions, (list, tuple)):
        raise InvalidRequest(f"{path} 必须是 array")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, decision in enumerate(decisions):
        item = _normalize(DECISION_SPEC, decision, f"{path}[{index}]")
        assert isinstance(item, dict)
        decision_id = item["id"]
        _decision_number(decision_id, f"{path}[{index}].id")
        if decision_id in seen:
            raise InvalidRequest(f"{path} 包含重复 decision id：{decision_id}")
        if item["status"] not in _DECISION_STATUSES:
            raise InvalidRequest(f"{path}[{index}].status 非法")
        seen.add(decision_id)
        normalized.append(item)
    return normalized


def _normalized_decision_transitions(
    transitions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(transitions, (list, tuple)):
        raise InvalidRequest("decision_transitions 必须是 array")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, transition in enumerate(transitions):
        path = f"decision_transitions[{index}]"
        item = _normalize(DECISION_TRANSITION_SPEC, transition, path)
        assert isinstance(item, dict)
        decision_id = item["id"]
        _decision_number(decision_id, f"{path}.id")
        if decision_id in seen:
            raise InvalidRequest(f"重复 decision transition id：{decision_id}")
        action = item["action"]
        if action not in _DECISION_ACTIONS:
            raise InvalidRequest(f"{path}.action 必须是 retire 或 supersede")
        replacement = item["replacement"]
        if action == "retire" and replacement is not None:
            raise InvalidRequest(f"{path}.replacement 在 retire 时必须是 null")
        if action == "supersede":
            _decision_number(replacement, f"{path}.replacement")
        seen.add(decision_id)
        normalized.append(item)
    return normalized


def _normalized_active_decision_ids(active_decision_ids: Sequence[str]) -> list[str]:
    if not isinstance(active_decision_ids, (list, tuple)):
        raise InvalidRequest("active_decision_ids 必须是 array")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, decision_id in enumerate(active_decision_ids):
        _decision_number(decision_id, f"active_decision_ids[{index}]")
        assert isinstance(decision_id, str)
        if decision_id in seen:
            raise InvalidRequest(f"active_decision_ids 包含重复 ID：{decision_id}")
        seen.add(decision_id)
        normalized.append(decision_id)
    return normalized


def _require_exact_active_decision_ids(
    active_decisions: Sequence[Mapping[str, Any]],
    active_decision_ids: Sequence[str],
) -> None:
    acknowledged = _normalized_active_decision_ids(active_decision_ids)
    expected = sorted(item["id"] for item in active_decisions)
    expected_set = set(expected)
    acknowledged_set = set(acknowledged)
    missing = sorted(expected_set - acknowledged_set)
    unknown = sorted(acknowledged_set - expected_set)
    if missing or unknown:
        parts: list[str] = []
        if missing:
            parts.append(f"遗漏仍然活动的决策：{', '.join(missing)}")
        if unknown:
            parts.append(f"列入不存在或已退出的决策：{', '.join(unknown)}")
        raise InvalidRequest(
            "active_decision_ids 未准确确认本 revision 的全部活动决策；"
            + "；".join(parts),
            details={
                "expected_active_decision_ids": expected,
                "missing_active_decision_ids": missing,
                "unknown_active_decision_ids": unknown,
            },
        )


def reduce_active_decisions(
    previous_active_decisions: Sequence[Mapping[str, Any]],
    submitted_decisions: Sequence[Mapping[str, Any]],
    decision_transitions: Sequence[Mapping[str, Any]],
    *,
    decision_id_high_watermark: int,
    active_decision_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], int]:
    """把本轮变化合入完整活动决策集，不读取任何外部状态。"""

    if (
        type(decision_id_high_watermark) is not int
        or not 0 <= decision_id_high_watermark <= 999
    ):
        raise InvalidRequest("decision_id_high_watermark 必须是 0 至 999 的整数")
    previous = _normalized_decisions(
        previous_active_decisions, "previous_active_decisions"
    )
    submitted = _normalized_decisions(submitted_decisions, "submitted_decisions")
    transitions = _normalized_decision_transitions(decision_transitions)
    highest_previous = max(
        (
            _decision_number(item["id"], "previous_active_decisions.id")
            for item in previous
        ),
        default=0,
    )
    if highest_previous > decision_id_high_watermark:
        raise InvalidRequest("decision_id_high_watermark 不能小于当前活动决策的最大 ID")

    active_by_id = {item["id"]: deepcopy(item) for item in previous}
    submitted_ids = {item["id"] for item in submitted}
    replacements: list[tuple[str, str]] = []
    for transition in transitions:
        decision_id = transition["id"]
        if decision_id not in active_by_id:
            raise InvalidRequest(f"不能变更未知或已退出的决策：{decision_id}")
        if decision_id in submitted_ids:
            raise InvalidRequest(f"退出决策不能同时出现在本轮详细决策中：{decision_id}")
        if transition["action"] == "supersede":
            replacement = transition["replacement"]
            assert isinstance(replacement, str)
            if replacement == decision_id:
                raise InvalidRequest(
                    f"被替代决策 {decision_id} 的 replacement 必须是另一个活动决策"
                )
            replacements.append((decision_id, replacement))
        del active_by_id[decision_id]

    watermark = decision_id_high_watermark
    for item in submitted:
        decision_id = item["id"]
        number = _decision_number(decision_id, "submitted_decisions.id")
        if decision_id not in active_by_id and number <= decision_id_high_watermark:
            raise InvalidRequest(
                f"不能复用已经退出的决策 ID：{decision_id}；"
                f"请使用大于 D-{decision_id_high_watermark:03d} 的新 ID"
            )
        previous_item = active_by_id.get(decision_id)
        if (
            previous_item is not None
            and previous_item["status"] == "locked"
            and item != previous_item
        ):
            raise InvalidRequest(
                f"locked 决策 {decision_id} 不能原地改写；"
                "请创建新 ID 并通过 supersede 显式替代"
            )
        active_by_id[decision_id] = deepcopy(item)
        watermark = max(watermark, number)

    for decision_id, replacement in replacements:
        if replacement not in active_by_id:
            raise InvalidRequest(
                f"被替代决策 {decision_id} 的 replacement {replacement} "
                "必须在本 revision 结束时保持活动"
            )

    active = [active_by_id[key] for key in sorted(active_by_id)]
    _require_exact_active_decision_ids(active, active_decision_ids)
    return active, watermark


def _criteria_transition_receipt(
    *,
    relay_id: str,
    revision: int,
    criteria_transitions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    for index, transition in enumerate(criteria_transitions, start=1):
        normalized = _normalize(
            CRITERIA_TRANSITION_SPEC,
            transition,
            f"criteria_transitions[{index - 1}]",
        )
        assert isinstance(normalized, dict)
        changes.append({"ordinal": index, **normalized})
    return {"relay_id": relay_id, "revision": revision, "changes": changes}


def build_canonical_revision(
    *,
    relay_id: str,
    revision: int,
    snapshot: Mapping[str, Any],
    previous_active_decisions: Sequence[Mapping[str, Any]],
    decision_id_high_watermark: int,
    decision_transitions: Sequence[Mapping[str, Any]],
    criteria_transitions: Sequence[Mapping[str, Any]],
    active_decision_ids: Sequence[str],
) -> dict[str, Any]:
    """构造单个 revision 的当前真相；调用方负责元数据和持久化。"""

    validate_relay_id(relay_id)
    if type(revision) is not int or revision < 1:
        raise InvalidRequest("revision 必须是正整数")
    normalized_snapshot = _normalize(SNAPSHOT_SPEC, snapshot, "snapshot")
    assert isinstance(normalized_snapshot, dict)
    active, watermark = reduce_active_decisions(
        previous_active_decisions,
        normalized_snapshot["decisions"],
        decision_transitions,
        decision_id_high_watermark=decision_id_high_watermark,
        active_decision_ids=active_decision_ids,
    )
    normalized_snapshot["decisions"] = active
    return {
        "snapshot": normalized_snapshot,
        "decision_id_high_watermark": watermark,
        "criteria_transition_receipt": _criteria_transition_receipt(
            relay_id=relay_id,
            revision=revision,
            criteria_transitions=criteria_transitions,
        ),
    }

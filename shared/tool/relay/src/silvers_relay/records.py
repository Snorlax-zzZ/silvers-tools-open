from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from .constants import MAX_CRITERIA_LABEL_BYTES, MAX_LOAD_BYTES
from .errors import InvalidRequest


LEGACY_RELAY_SCHEMA = 2
LEGACY_RENDER_VERSION = 2
PREVIOUS_RELAY_SCHEMA = 3
PREVIOUS_RENDER_VERSION = 3
PHASE_LINEAGE_RELAY_SCHEMA = 4
PHASE_LINEAGE_RENDER_VERSION = 4
COMPLETION_STATUS_RELAY_SCHEMA = 5
COMPLETION_STATUS_RENDER_VERSION = 5
# lineage 从这一版起带 phase_authorization。单独命名而不是复用 RELAY_SCHEMA：
# 下次升到 7 时，这个"字段从哪版开始存在"的事实不能跟着当前版本号漂走。
PHASE_AUTHORIZATION_RELAY_SCHEMA = 6
PHASE_AUTHORIZATION_RENDER_VERSION = 6
RELAY_SCHEMA = 6
RENDER_VERSION = 6


def request_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Restore a writable request without exposing CLI-owned phase identity."""

    request = deepcopy(snapshot)
    request["phase"].pop("phase_id", None)
    request["decision_transitions"] = []
    request["criteria_transitions"] = []
    return request


def upgrade_legacy_request(request: dict[str, Any]) -> dict[str, Any]:
    """把 schema 6 之前的存量 request 补齐到当前 schema 能写入的形状。

    只在"拿旧 snapshot 当新写入的底稿"时调用，不能塞进
    request_from_snapshot：那个函数也服务于磁盘记录的合法性校验，
    在那条路径上补字段会让校验放过本不该通过的记录，也会让旧档案
    凭空多出字段而被判成未知字段。

    必须补两样，缺一样都会在写入时炸：
    - `authority.must_not`（schema 6 引入）；
    - `phase.done_when_status`（schema 5 引入）——withdraw 拿 schema 2/3/4
      的旧棒派生新记录时，v6 渲染器会直接读这个字段，缺了就是裸 KeyError，
      而且 CLI 只捕获 RelayError/OSError/ValueError，用户看到的是 traceback。
      旧档案从未声明过逐条状态，因此补中性的 pending 而不是编一个 met。
    """

    request["authority"].setdefault("must_not", [])
    phase = request["phase"]
    if "done_when_status" not in phase:
        phase["done_when_status"] = [
            {"status": "pending", "reason": None}
            for _ in phase["done_when"]
        ]
    return request


def snapshot_from_request(
    request: dict[str, Any],
    *,
    phase_id: str,
) -> dict[str, Any]:
    """Return only current truth; lifecycle operations are intentionally transient."""

    snapshot = deepcopy(request)
    snapshot.pop("decision_transitions", None)
    snapshot.pop("criteria_transitions", None)
    # 授权是本次写入的准入证明，跟 transitions 同类：落进 lineage，不进快照。
    snapshot.pop("authorization", None)
    snapshot["phase"]["phase_id"] = phase_id
    return snapshot


def build_record(
    request: dict[str, Any],
    metadata: dict[str, Any],
    *,
    decision_id_high_watermark: int | None = None,
    criteria_changes: list[dict[str, Any]] | None = None,
    predecessor_revision: int | None = None,
    predecessor_summary: dict[str, Any] | None = None,
    phase_authorization: str | None,
) -> dict[str, Any]:
    if decision_id_high_watermark is None:
        decision_id_high_watermark = max(
            (
                int(decision["id"].split("-", 1)[1])
                for decision in request["decisions"]
            ),
            default=0,
        )
    if criteria_changes is None:
        criteria_changes = [
            {"ordinal": ordinal, **deepcopy(transition)}
            for ordinal, transition in enumerate(
                request["criteria_transitions"], start=1
            )
        ]
    return {
        "relay_schema": RELAY_SCHEMA,
        "render_version": RENDER_VERSION,
        "metadata": deepcopy(metadata),
        "lineage": {
            "predecessor_relay_id": request["phase"]["predecessor_relay_id"],
            "predecessor_revision": predecessor_revision,
            "predecessor_summary": deepcopy(predecessor_summary),
            # 开启这个阶段时用户授权的原话；根棒为 None。参数不给默认值，
            # 漏传会直接 TypeError——这个字段一旦静默丢失，事后无法区分
            # "用户批过"和"模型自己开的"。
            "phase_authorization": phase_authorization,
        },
        "snapshot": snapshot_from_request(
            request, phase_id=str(metadata["relay_id"])
        ),
        "decision_id_high_watermark": decision_id_high_watermark,
        "criteria_changes": deepcopy(criteria_changes),
    }


def _truncate_utf8(value: str, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    suffix = "…"
    budget = max_bytes - len(suffix.encode("utf-8"))
    truncated = encoded[: max(0, budget)]
    while True:
        try:
            return truncated.decode("utf-8") + suffix, True
        except UnicodeDecodeError:
            truncated = truncated[:-1]


def criteria_transition_label(transition: dict[str, Any]) -> str:
    """按历史规则重算存量判据冷索引的 label，用于与磁盘上的冷指针全等比对。

    当前协议不再写 criteria_registry（新记录用 ordinal 而非 C-00x），
    这个函数只服务于读存量。之所以必须重算再全等比，而不能用
    "详情全文以 label 开头" 这种前缀匹配：label 是 96 字节截断值，
    超限时尾部是 …，前缀匹配对被截断的记录恒为假——存量里凡是长判据
    全部打不开；而对未截断的记录 label 就等于全文，前缀匹配又恒为真，
    等于没有校验。两头都错，且全量测试都看不见。
    """

    label, _ = _truncate_utf8(
        str(transition["id_or_text"]),
        MAX_CRITERIA_LABEL_BYTES,
    )
    return label


def serialize_record(record: dict[str, Any]) -> str:
    rendered = json.dumps(
        record,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"
    size = len(rendered.encode("utf-8"))
    if size > MAX_LOAD_BYTES:
        raise InvalidRequest(
            f"Relay canonical JSON 超过 {MAX_LOAD_BYTES} bytes 总硬上限：{size}"
        )
    return rendered


def _changed_paths(
    previous: Any,
    current: Any,
    *,
    prefix: str = "",
) -> list[str]:
    if isinstance(previous, dict) and isinstance(current, dict):
        changed: list[str] = []
        for key in sorted(previous.keys() | current.keys()):
            path = f"{prefix}.{key}" if prefix else key
            if key not in previous or key not in current:
                changed.append(path)
            else:
                changed.extend(
                    _changed_paths(previous[key], current[key], prefix=path)
                )
        return changed
    if previous != current:
        return [prefix]
    return []


def _decision_details(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    details = {
        item["id"]: item for item in record["snapshot"]["decisions"]
    }
    legacy_registry = record.get("decision_registry")
    if not isinstance(legacy_registry, dict):
        return details
    for pointer in legacy_registry.get("active", []):
        details.setdefault(
            pointer["id"],
            {
                "id": pointer["id"],
                "status": pointer["status"],
                "label": pointer["label"],
            },
        )
    return details


def build_structured_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    current_revision = current["metadata"]["revision"]
    current_criteria_changes = current.get("criteria_changes", [])
    criteria_changes = [
        {**deepcopy(change), "source_revision": current_revision}
        for change in current_criteria_changes
    ]
    current_decisions = _decision_details(current)
    if previous is None:
        return {
            "kind": "created",
            "from_revision": None,
            "to_revision": current_revision,
            "changed_paths": [],
            "decision_changes": [
                {"id": decision_id, "change": "added"}
                for decision_id in sorted(current_decisions)
            ],
            "criteria_change_count": len(current_criteria_changes),
            "criteria_changes": criteria_changes,
            "source_change": None,
            "truncated": False,
        }

    paths = _changed_paths(previous["snapshot"], current["snapshot"])
    previous_decisions = _decision_details(previous)
    decision_changes: list[dict[str, Any]] = []
    for decision_id in sorted(previous_decisions.keys() | current_decisions.keys()):
        old = previous_decisions.get(decision_id)
        new = current_decisions.get(decision_id)
        if old is None:
            decision_changes.append({"id": decision_id, "change": "added"})
        elif new is None:
            decision_changes.append({"id": decision_id, "change": "retired"})
        else:
            status_changed = old["status"] != new["status"]
            label_changed = old["label"] != new["label"]
            detail_changed = old != new
            if not (status_changed or label_changed or detail_changed):
                continue
            decision_changes.append(
                {
                    "id": decision_id,
                    "change": "updated",
                    "from_status": old["status"],
                    "to_status": new["status"],
                    "label_changed": label_changed,
                    "detail_changed": detail_changed,
                }
            )

    old_source = {
        key: previous["metadata"][key]
        for key in ("source_head", "source_branch", "source_dirty")
    }
    new_source = {
        key: current["metadata"][key]
        for key in ("source_head", "source_branch", "source_dirty")
    }
    source_change = None
    if old_source != new_source:
        source_change = {"from": old_source, "to": new_source}

    return {
        "kind": "updated",
        "from_revision": previous["metadata"]["revision"],
        "to_revision": current_revision,
        "changed_paths": paths,
        "decision_changes": decision_changes,
        "criteria_change_count": len(current_criteria_changes),
        "criteria_changes": criteria_changes,
        "source_change": source_change,
        "truncated": False,
    }

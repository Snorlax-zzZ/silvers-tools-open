from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

from . import __version__
from .constants import MAX_INSTALLATION_WARNING_BYTES
from .errors import InstallationError, SchemaUnsupported
from .project import sanitized_git_environment


CURRENT_POINTER_SCHEMA = 1
RUNTIME_RECEIPT_SCHEMA = 1
INSTALL_RECEIPT_SCHEMA = 1
ADAPTER_PROTOCOL_VERSION = 2
MAX_CURRENT_POINTER_BYTES = 4 * 1024
MAX_INSTALLATION_JSON_BYTES = 64 * 1024

_VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"
)
_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PYTHON_VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+._0-9A-Za-z]*)?$"
)
RUNTIME_SOURCE_PATHS = (
    "shared/tool/relay/src",
    "shared/tool/relay/pyproject.toml",
    "shared/tool/relay/setup.py",
    "shared/tool/relay/launcher",
)
CLIENT_SOURCE_PATHS = (
    "shared/command/relay/commands",
    "shared/command/relay/install/codex-permissions.md",
    "shared/skill/relay",
    "shared/skill/relay-load",
    "shared/skill/relay-done",
)


def _read_json_object(
    path: Path,
    *,
    label: str,
    max_bytes: int = MAX_INSTALLATION_JSON_BYTES,
) -> dict[str, Any]:
    if path.is_symlink():
        raise InstallationError(f"{label} 不允许是符号链接：{path}")
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except FileNotFoundError as error:
        raise InstallationError(f"{label} 不存在：{path}") from error
    if len(raw) > max_bytes:
        raise InstallationError(f"{label} 超过 {max_bytes} bytes：{path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise InstallationError(f"{label} 必须是 UTF-8 JSON：{path}") from error
    except json.JSONDecodeError as error:
        raise InstallationError(f"{label} JSON 格式非法：{path}") from error
    if not isinstance(payload, dict):
        raise InstallationError(f"{label} 必须是 JSON object：{path}")
    return payload


def _require_exact_fields(
    payload: dict[str, Any],
    expected: set[str],
    *,
    label: str,
) -> None:
    if set(payload) != expected:
        missing = sorted(expected - payload.keys())
        extra = sorted(payload.keys() - expected)
        descriptions: list[str] = []
        if missing:
            descriptions.append(f"缺少 {', '.join(missing)}")
        if extra:
            descriptions.append(f"未知 {', '.join(extra)}")
        raise InstallationError(f"{label} 字段非法：{'; '.join(descriptions)}")


def _require_supported_schema(
    payload: dict[str, Any],
    field: str,
    supported: int,
    *,
    component: str,
    label: str,
) -> None:
    encountered = payload.get(field)
    if type(encountered) is not int:
        raise InstallationError(f"{label} {field} 必须是 integer")
    if encountered != supported:
        raise SchemaUnsupported(
            component=component,
            cli_version=__version__,
            supported_schema=supported,
            encountered_schema=encountered,
        )


def _require_version(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _VERSION_PATTERN.fullmatch(value):
        raise InstallationError(f"{field} 必须是规范 Relay 版本号")
    return value


def _require_commit(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _COMMIT_PATTERN.fullmatch(value):
        raise InstallationError(f"{field} 必须是完整小写 Git commit id")
    return value


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise InstallationError(f"{field} 必须是小写 SHA-256")
    return value


def _require_utc_timestamp(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InstallationError(f"{field} 必须是带 Z 的 UTC ISO 8601 时间")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise InstallationError(f"{field} 必须是带 Z 的 UTC ISO 8601 时间") from error
    if parsed.tzinfo != timezone.utc:
        raise InstallationError(f"{field} 必须是带 Z 的 UTC ISO 8601 时间")
    return value


def _safe_posix_relative_path(
    value: Any,
    *,
    field: str,
    required_root: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\n" in value
        or "\r" in value
    ):
        raise InstallationError(f"{field} 必须是非空 POSIX 相对路径")
    path = PurePosixPath(value)
    parts = path.parts
    if (
        path.is_absolute()
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise InstallationError(f"{field} 必须是安全的 POSIX 相对路径")
    if value != path.as_posix():
        raise InstallationError(f"{field} 必须使用规范 POSIX 相对路径")
    if required_root is not None and parts[0] != required_root:
        raise InstallationError(f"{field} 必须位于 {required_root}/ 下")
    return value, parts


def _require_single_line(value: Any, *, field: str, max_length: int = 128) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or "\n" in value
        or "\r" in value
        or "\x00" in value
    ):
        raise InstallationError(f"{field} 必须是非空单行字符串")
    return value


def _resolve_runtime_entrypoint(home: Path, parts: tuple[str, ...]) -> Path:
    home = home.expanduser().resolve()
    runtimes = home / "runtimes"
    target = home.joinpath(*parts)
    current = target
    while current != home:
        if current.is_symlink():
            raise InstallationError(f"current entrypoint 路径不允许符号链接：{current}")
        current = current.parent
    try:
        resolved = target.resolve(strict=True)
    except FileNotFoundError as error:
        raise InstallationError(f"current entrypoint 不存在：{target}") from error
    try:
        resolved.relative_to(runtimes)
    except ValueError as error:
        raise InstallationError("current entrypoint 必须位于 runtimes/ 下") from error
    if not resolved.is_file():
        raise InstallationError(f"current entrypoint 必须是普通文件：{target}")
    return resolved


def load_current_pointer(home: Path) -> dict[str, Any]:
    resolved_home = home.expanduser().resolve()
    payload = _read_json_object(
        resolved_home / "current.json",
        label="Relay current pointer",
        max_bytes=MAX_CURRENT_POINTER_BYTES,
    )
    _require_supported_schema(
        payload,
        "current_schema",
        CURRENT_POINTER_SCHEMA,
        component="current_pointer",
        label="Relay current pointer",
    )
    _require_exact_fields(
        payload,
        {"current_schema", "entrypoint"},
        label="Relay current pointer",
    )
    entrypoint, parts = _safe_posix_relative_path(
        payload["entrypoint"],
        field="current entrypoint",
        required_root="runtimes",
    )
    if len(parts) < 3:
        raise InstallationError(
            "current entrypoint 必须包含 runtimes/<version>/<target>"
        )
    runtime_version = _require_version(parts[1], field="current runtime version")
    _resolve_runtime_entrypoint(resolved_home, parts)
    return {
        "current_schema": CURRENT_POINTER_SCHEMA,
        "entrypoint": entrypoint,
        "runtime_version": runtime_version,
    }


def _load_runtime_receipt(home: Path, runtime_version: str) -> dict[str, Any]:
    runtime_root = home / "runtimes" / runtime_version
    payload = _read_json_object(
        runtime_root / "runtime.json", label="Relay runtime receipt"
    )
    _require_supported_schema(
        payload,
        "runtime_schema",
        RUNTIME_RECEIPT_SCHEMA,
        component="runtime_receipt",
        label="Relay runtime receipt",
    )
    _require_exact_fields(
        payload,
        {
            "runtime_schema",
            "relay_version",
            "source_commit",
            "entrypoint",
            "installed_at",
            "python_version",
        },
        label="Relay runtime receipt",
    )
    relay_version = _require_version(
        payload["relay_version"], field="runtime relay_version"
    )
    source_commit = _require_commit(
        payload["source_commit"], field="runtime source_commit"
    )
    entrypoint, parts = _safe_posix_relative_path(
        payload["entrypoint"], field="runtime entrypoint"
    )
    target = runtime_root.joinpath(*parts)
    if target.is_symlink() or not target.is_file():
        raise InstallationError(
            f"runtime entrypoint 必须是已存在的普通非符号链接文件：{target}"
        )
    _require_utc_timestamp(payload["installed_at"], field="runtime installed_at")
    python_version = payload["python_version"]
    if (
        not isinstance(python_version, str)
        or not _PYTHON_VERSION_PATTERN.fullmatch(python_version)
    ):
        raise InstallationError("runtime python_version 格式非法")
    return {
        "runtime_schema": RUNTIME_RECEIPT_SCHEMA,
        "relay_version": relay_version,
        "source_commit": source_commit,
        "entrypoint": entrypoint,
        "installed_at": payload["installed_at"],
        "python_version": python_version,
    }


def _validate_file_receipts(
    value: Any,
    *,
    field: str,
    absolute_paths: bool,
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise InstallationError(f"{field} 必须是非空 array")
    items: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, raw_item in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(raw_item, dict):
            raise InstallationError(f"{item_field} 必须是 object")
        _require_exact_fields(
            raw_item, {"path", "sha256"}, label=item_field
        )
        raw_path = raw_item["path"]
        if absolute_paths:
            raw_path = _require_single_line(
                raw_path,
                field=f"{item_field}.path",
                max_length=4096,
            )
            if not Path(raw_path).is_absolute():
                raise InstallationError(f"{item_field}.path 必须是绝对路径")
            path = raw_path
        else:
            path, _ = _safe_posix_relative_path(
                raw_path, field=f"{item_field}.path", required_root="bin"
            )
        if path in seen_paths:
            raise InstallationError(f"{field} 包含重复路径：{path}")
        seen_paths.add(path)
        items.append(
            {
                "path": path,
                "sha256": _require_sha256(
                    raw_item["sha256"], field=f"{item_field}.sha256"
                ),
            }
        )
    return items


def _load_install_receipt(home: Path) -> dict[str, Any]:
    payload = _read_json_object(home / "install.json", label="Relay install receipt")
    _require_supported_schema(
        payload,
        "install_schema",
        INSTALL_RECEIPT_SCHEMA,
        component="install_receipt",
        label="Relay install receipt",
    )
    _require_exact_fields(
        payload,
        {
            "install_schema",
            "relay_home",
            "launcher_files",
            "current_runtime",
            "source_commit",
            "installed_at",
            "clients",
        },
        label="Relay install receipt",
    )
    relay_home = _require_single_line(
        payload["relay_home"], field="install relay_home", max_length=4096
    )
    if not Path(relay_home).is_absolute():
        raise InstallationError("install relay_home 必须是绝对路径")
    if Path(relay_home).resolve() != home.resolve():
        raise InstallationError(
            f"install relay_home 与当前 home 不一致：{relay_home}"
        )
    launcher_files = _validate_file_receipts(
        payload["launcher_files"],
        field="install launcher_files",
        absolute_paths=False,
    )
    current_runtime = _require_version(
        payload["current_runtime"], field="install current_runtime"
    )
    source_commit = _require_commit(
        payload["source_commit"], field="install source_commit"
    )
    _require_utc_timestamp(payload["installed_at"], field="install installed_at")

    raw_clients = payload["clients"]
    if not isinstance(raw_clients, list):
        raise InstallationError("install clients 必须是 array")
    clients: list[dict[str, Any]] = []
    seen_clients: set[str] = set()
    for index, raw_client in enumerate(raw_clients):
        label = f"install clients[{index}]"
        if not isinstance(raw_client, dict):
            raise InstallationError(f"{label} 必须是 object")
        client_fields = set(raw_client)
        legacy_fields = {"client", "adapter_protocol", "files"}
        current_fields = legacy_fields | {"source_commit"}
        if client_fields != legacy_fields and client_fields != current_fields:
            _require_exact_fields(raw_client, current_fields, label=label)
        client = _require_single_line(raw_client["client"], field=f"{label}.client")
        if client in seen_clients:
            raise InstallationError(f"install clients 包含重复客户端：{client}")
        seen_clients.add(client)
        adapter_protocol = raw_client["adapter_protocol"]
        if type(adapter_protocol) is not int:
            raise InstallationError(f"{label}.adapter_protocol 必须是 integer")
        if adapter_protocol != ADAPTER_PROTOCOL_VERSION:
            raise SchemaUnsupported(
                component="client_adapter",
                cli_version=__version__,
                supported_schema=ADAPTER_PROTOCOL_VERSION,
                encountered_schema=adapter_protocol,
            )
        normalized_client = {
            "client": client,
            "adapter_protocol": adapter_protocol,
            "files": _validate_file_receipts(
                raw_client["files"],
                field=f"{label}.files",
                absolute_paths=True,
            ),
        }
        if "source_commit" in raw_client:
            normalized_client["source_commit"] = _require_commit(
                raw_client["source_commit"],
                field=f"{label}.source_commit",
            )
        clients.append(normalized_client)

    return {
        "install_schema": INSTALL_RECEIPT_SCHEMA,
        "relay_home": str(home.resolve()),
        "launcher_files": launcher_files,
        "current_runtime": current_runtime,
        "source_commit": source_commit,
        "installed_at": payload["installed_at"],
        "clients": clients,
    }


def load_installation_state(home: Path) -> dict[str, dict[str, Any]] | None:
    resolved_home = home.expanduser().resolve()
    current_path = resolved_home / "current.json"
    install_path = resolved_home / "install.json"
    runtimes_path = resolved_home / "runtimes"
    present = {
        "current.json": current_path.exists() or current_path.is_symlink(),
        "install.json": install_path.exists() or install_path.is_symlink(),
        "runtimes/": runtimes_path.exists() or runtimes_path.is_symlink(),
    }
    if not any(present.values()):
        return None
    missing = [name for name, exists in present.items() if not exists]
    if missing:
        raise InstallationError(
            f"Relay 安装状态不完整，缺少：{', '.join(missing)}"
        )
    if runtimes_path.is_symlink() or not runtimes_path.is_dir():
        raise InstallationError("Relay runtimes/ 必须是普通目录且不能是符号链接")

    current = load_current_pointer(resolved_home)
    runtime = _load_runtime_receipt(
        resolved_home, current["runtime_version"]
    )
    install = _load_install_receipt(resolved_home)
    if runtime["relay_version"] != current["runtime_version"]:
        raise InstallationError(
            "runtime relay_version 与 current runtime version 不一致"
        )
    expected_current_entrypoint = (
        f"runtimes/{current['runtime_version']}/{runtime['entrypoint']}"
    )
    if current["entrypoint"] != expected_current_entrypoint:
        raise InstallationError(
            "runtime entrypoint 与 current entrypoint 不一致"
        )
    if install["current_runtime"] != current["runtime_version"]:
        raise InstallationError(
            "install current_runtime 与 current runtime version 不一致"
        )
    if install["source_commit"] != runtime["source_commit"]:
        raise InstallationError(
            "install source_commit 与 runtime source_commit 不一致"
        )
    return {"current": current, "runtime": runtime, "install": install}


def _latest_relay_source(
    repo: Path, source_paths: tuple[str, ...]
) -> dict[str, Any]:
    try:
        root_result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            env=sanitized_git_environment(),
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unavailable", "reason": "git_unavailable"}
    if root_result.returncode:
        return {"state": "unavailable", "reason": "not_git_repository"}
    root = Path(root_result.stdout.strip())
    if not any((root / path).exists() for path in source_paths):
        return {"state": "unavailable", "reason": "relay_paths_not_found"}
    try:
        latest = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "-1",
                "--format=%H",
                "--",
                *source_paths,
            ],
            env=sanitized_git_environment(),
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unavailable", "reason": "git_unavailable"}
    commit = latest.stdout.strip()
    if latest.returncode or not _COMMIT_PATTERN.fullmatch(commit):
        return {"state": "unavailable", "reason": "relay_commit_not_found"}
    try:
        status = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                *source_paths,
            ],
            env=sanitized_git_environment(),
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unavailable", "reason": "git_unavailable"}
    if status.returncode:
        return {
            "state": "unavailable",
            "reason": "relay_dirty_status_unavailable",
        }
    dirty_paths: set[str] = set()
    records = status.stdout.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            return {
                "state": "unavailable",
                "reason": "relay_dirty_status_unparseable",
            }
        dirty_paths.add(record[3:])
        if "R" in record[:2] or "C" in record[:2]:
            if index >= len(records) or not records[index]:
                return {
                    "state": "unavailable",
                    "reason": "relay_dirty_status_unparseable",
                }
            dirty_paths.add(records[index])
            index += 1
    return {
        "state": "available",
        "repository": str(root.resolve()),
        "latest_commit": commit,
        "dirty": bool(dirty_paths),
        "dirty_paths": sorted(dirty_paths),
    }


def _commit_relation(repo: Path, installed: str, latest: str) -> str:
    if installed == latest:
        return "current"
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "merge-base",
                "--is-ancestor",
                installed,
                latest,
            ],
            env=sanitized_git_environment(),
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if result.returncode == 0:
        return "stale"
    if result.returncode != 1:
        return "unknown"
    try:
        reverse = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "merge-base",
                "--is-ancestor",
                latest,
                installed,
            ],
            env=sanitized_git_environment(),
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if reverse.returncode == 0:
        return "current"
    if reverse.returncode == 1:
        return "diverged"
    return "unknown"


def _artifact_status(files: list[dict[str, str]]) -> dict[str, Any]:
    missing: list[str] = []
    modified: list[str] = []
    for item in files:
        path = Path(item["path"])
        if path.is_symlink() or not path.is_file():
            missing.append(item["path"])
            continue
        try:
            digest_builder = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest_builder.update(chunk)
            digest = digest_builder.hexdigest()
        except OSError:
            missing.append(item["path"])
            continue
        if digest != item["sha256"]:
            modified.append(item["path"])
    if missing:
        state = "missing"
    elif modified:
        state = "modified"
    else:
        state = "current"
    return {"state": state, "missing": missing, "modified": modified}


def assess_installation(home: Path, repo: Path) -> dict[str, Any] | None:
    state = load_installation_state(home)
    if state is None:
        return None
    install = state["install"]
    runtime_source = _latest_relay_source(repo, RUNTIME_SOURCE_PATHS)
    client_source = _latest_relay_source(repo, CLIENT_SOURCE_PATHS)
    source_status: dict[str, Any]
    if runtime_source["state"] != "available":
        source_status = runtime_source
    else:
        relation = _commit_relation(
            Path(runtime_source["repository"]),
            install["source_commit"],
            runtime_source["latest_commit"],
        )
        if runtime_source["dirty"]:
            source_status = {
                "state": "dirty_unverifiable",
                "repository": runtime_source["repository"],
                "latest_commit": runtime_source["latest_commit"],
                "commit_relation": relation,
                "dirty": True,
                "dirty_paths": runtime_source["dirty_paths"],
                "suggested_action": (
                    "先提交或清理当前仓库的 Relay 源码改动，"
                    "再判断安装是否最新"
                ),
            }
        else:
            source_status = {
                "state": relation,
                "repository": runtime_source["repository"],
                "latest_commit": runtime_source["latest_commit"],
            }
        if relation == "stale" and not runtime_source["dirty"]:
            source_status["suggested_action"] = (
                "按当前仓库 Relay 安装手册重新安装 runtime"
            )
    clients: list[dict[str, Any]] = []
    for client in install["clients"]:
        client_commit = client.get("source_commit", install["source_commit"])
        if client_source["state"] == "available":
            client_commit_relation = _commit_relation(
                Path(client_source["repository"]),
                client_commit,
                client_source["latest_commit"],
            )
            client_source_status = (
                "dirty_unverifiable"
                if client_source["dirty"]
                else client_commit_relation
            )
        else:
            client_commit_relation = None
            client_source_status = "unavailable"
        entry = {
            "client": client["client"],
            "adapter_protocol": client["adapter_protocol"],
            "file_count": len(client["files"]),
            "source_commit": client_commit,
            "source_commit_origin": (
                "client" if "source_commit" in client else "legacy_install"
            ),
            "source_status": client_source_status,
            "artifacts": _artifact_status(client["files"]),
        }
        if client_source["state"] == "available" and client_source["dirty"]:
            entry["commit_relation"] = client_commit_relation
            entry["dirty_paths"] = client_source["dirty_paths"]
        if client_source_status == "stale":
            entry["suggested_action"] = (
                f"按安装手册重装 {client['client']} 的 Relay 适配器"
            )
        clients.append(entry)
    return {
        "recorded": True,
        "current_runtime": install["current_runtime"],
        "source_commit": install["source_commit"],
        "installed_at": install["installed_at"],
        "runtime_python": state["runtime"]["python_version"],
        "source_status": source_status,
        "clients": clients,
    }


def installation_warnings(home: Path, repo: Path) -> list[dict[str, Any]]:
    assessed = assess_installation(home, repo)
    if assessed is None:
        return []
    warnings: list[dict[str, Any]] = []
    stale_clients = [
        client["client"]
        for client in assessed["clients"]
        if client["source_status"] == "stale"
        or client.get("commit_relation") == "stale"
    ]
    modified_clients = [
        client["client"]
        for client in assessed["clients"]
        if client["artifacts"]["state"] != "current"
    ]
    source_status = assessed["source_status"]
    if (
        source_status["state"] == "stale"
        or source_status.get("commit_relation") == "stale"
        or stale_clients
    ):
        warnings.append(
            {
                "code": "installation_stale",
                "message": "本机 Relay 安装落后于当前仓库的 Relay 规则。",
                "clients": stale_clients,
                "client_total": len(stale_clients),
                "clients_truncated": False,
                "suggested_action": "按当前仓库安装手册重装过期的 runtime/client。",
            }
        )
    dirty_paths = set(
        source_status.get("dirty_paths", [])
        if source_status["state"] == "dirty_unverifiable"
        else []
    )
    for client in assessed["clients"]:
        if client["source_status"] == "dirty_unverifiable":
            dirty_paths.update(client.get("dirty_paths", []))
    if dirty_paths:
        sorted_dirty_paths = sorted(dirty_paths)
        warnings.append(
            {
                "code": "installation_source_dirty",
                "message": (
                    "当前仓库的 Relay 源码有未提交改动，"
                    "无法证明本机安装与待执行规则一致。"
                ),
                "dirty_paths": sorted_dirty_paths,
                "dirty_path_total": len(sorted_dirty_paths),
                "dirty_paths_truncated": False,
                "suggested_action": (
                    "先提交或清理 Relay 源码，再按安装手册核对或重装。"
                ),
            }
        )
    if modified_clients:
        warnings.append(
            {
                "code": "installation_artifacts_changed",
                "message": "Relay client 文件与安装回执哈希不一致。",
                "clients": modified_clients,
                "client_total": len(modified_clients),
                "clients_truncated": False,
                "suggested_action": "逐文件核对差异后按安装手册更新回执或重装。",
            }
        )
    return _bound_installation_warnings(warnings)


def _bound_installation_warnings(
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """安装诊断独立限流，不占用也不改变 Relay 内容硬预算。"""

    budget = MAX_INSTALLATION_WARNING_BYTES
    if len(json.dumps(warnings, ensure_ascii=False).encode("utf-8")) <= budget:
        return warnings
    kept: list[dict[str, Any]] = []
    for warning in warnings:
        candidate = kept + [warning]
        size = len(json.dumps(candidate, ensure_ascii=False).encode("utf-8"))
        if size > budget:
            break
        kept = candidate
    # 截断本身也要如实告知，否则接棒方会以为安装完全正常。
    notice = {
        "code": "installation_warnings_truncated",
        "message": (
            f"安装警告总量超过 {MAX_INSTALLATION_WARNING_BYTES} bytes，已截断；"
            "请运行 relay status 查看完整安装诊断。"
        ),
        "warning_total": len(warnings),
        "warnings_kept": len(kept),
    }
    while kept and len(
        json.dumps(kept + [notice], ensure_ascii=False).encode("utf-8")
    ) > budget:
        kept.pop()
        notice["warnings_kept"] = len(kept)
    return kept + [notice]

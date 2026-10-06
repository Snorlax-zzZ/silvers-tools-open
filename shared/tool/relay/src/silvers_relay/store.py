from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import errno
from functools import wraps
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Concatenate, Iterator, ParamSpec, TextIO, TypeVar
import uuid

if os.name == "nt":  # pragma: no cover - exercised on Windows
    import msvcrt
else:  # pragma: no branch - platform selection
    import fcntl

from . import __version__
from .canonical import build_canonical_revision
from .constants import (
    MAX_LOAD_BYTES,
    SOFT_LOAD_BYTES,
)
from .errors import (
    InvalidRelayId,
    InvalidRequest,
    LoadTooLarge,
    MigrationFailed,
    RelayNotFound,
    SchemaUnsupported,
    SelectionRequired,
    StaleRevision,
    StoreBusy,
    StoreError,
    StoreDirty,
    SyncError,
)
from .project import (
    ProjectIdentity,
    ProjectSnapshot,
    normalize_remote,
    sanitized_git_environment,
)
from .protocol import (
    OperationContext,
    OperationName,
    ValidatedCreate,
    ValidatedDone,
    ValidatedOperation,
    ValidatedSuccessor,
    ValidatedUpdate,
    ValidatedWithdraw,
    assert_validated_operation,
    compile_operation,
    materialized_object_fields,
    operation_command,
)
from .records import (
    LEGACY_RELAY_SCHEMA,
    LEGACY_RENDER_VERSION,
    COMPLETION_STATUS_RELAY_SCHEMA,
    COMPLETION_STATUS_RENDER_VERSION,
    PHASE_AUTHORIZATION_RELAY_SCHEMA,
    PHASE_AUTHORIZATION_RENDER_VERSION,
    PHASE_LINEAGE_RELAY_SCHEMA,
    PHASE_LINEAGE_RENDER_VERSION,
    PREVIOUS_RELAY_SCHEMA,
    PREVIOUS_RENDER_VERSION,
    RELAY_SCHEMA,
    RENDER_VERSION,
    build_record,
    build_structured_delta,
    criteria_transition_label,
    request_from_snapshot,
    upgrade_legacy_request,
    serialize_record,
)
from .render import render_document, render_record
from .validation import (
    validate_authorization,
    validate_no_secrets,
    validate_relay_id,
    validate_request,
    validate_writer_metadata,
)


ACTIVE_METADATA_FIELDS = {
    "relay_schema",
    "relay_id",
    "project_key",
    "project_remote",
    "title",
    "status",
    "revision",
    "created_at",
    "updated_at",
    "last_client",
    "last_model",
    "last_machine",
    "source_head",
    "source_branch",
    "source_dirty",
}
LOCK_TIMEOUT_SECONDS = 30.0
STORE_MARKER = Path(".silvers-relay-store.json")
STORE_SCHEMA = 2
STORE_MARKER_CONTENT = (
    f'{{"purpose":"silvers-relay","relay_store_schema":{STORE_SCHEMA}}}\n'
)
ALLOWED_STORE_TOP_LEVEL = {STORE_MARKER.name, "active", "done", "withdrawn"}
_EXECUTION_TOKEN = object()
P = ParamSpec("P")
T = TypeVar("T")
_LOCK_REGISTRY_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_LOCK_STATE = threading.local()


def _thread_held_locks() -> set[str]:
    held = getattr(_LOCK_STATE, "held", None)
    if held is None:
        held = set()
        _LOCK_STATE.held = held
    return held


def _acquire_file_lock(handle: TextIO, deadline: float) -> None:
    while True:
        try:
            if os.name == "nt":  # pragma: no cover - exercised on Windows
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write("\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(  # type: ignore[attr-defined]
                    handle.fileno(), msvcrt.LK_NBLCK, 1  # type: ignore[attr-defined]
                )
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise StoreError(f"无法获取 Relay store 锁：{error}") from error
            if time.monotonic() >= deadline:
                raise StoreBusy("Relay store 正由另一个进程操作；请稍后重试") from error
            time.sleep(0.05)


def _release_file_lock(handle: TextIO) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows
        handle.seek(0)
        msvcrt.locking(  # type: ignore[attr-defined]
            handle.fileno(), msvcrt.LK_UNLCK, 1  # type: ignore[attr-defined]
        )
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def store_lock(store: Path) -> Iterator[None]:
    resolved_store = store.expanduser().resolve()
    key = str(resolved_store)
    with _LOCK_REGISTRY_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
    with thread_lock:
        held = _thread_held_locks()
        if key in held:
            yield
            return
        resolved_store.parent.mkdir(parents=True, exist_ok=True)
        lock_path = resolved_store.parent / f".{resolved_store.name}.relay.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.chmod(lock_path, 0o600)
        with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
            _acquire_file_lock(handle, time.monotonic() + LOCK_TIMEOUT_SECONDS)
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
                _release_file_lock(handle)


def _locked_store_operation(
    function: Callable[Concatenate[Path, P], T],
) -> Callable[Concatenate[Path, P], T]:
    @wraps(function)
    def wrapped(store: Path, /, *args: P.args, **kwargs: P.kwargs) -> T:
        with store_lock(store):
            return function(store, *args, **kwargs)

    return wrapped


def _locked_project_operation(
    function: Callable[Concatenate[Path, ProjectSnapshot, P], T],
) -> Callable[Concatenate[Path, ProjectSnapshot, P], T]:
    @wraps(function)
    def wrapped(
        store: Path,
        project: ProjectSnapshot,
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        remote_value = kwargs.get("remote")
        remote = remote_value if isinstance(remote_value, str) else None
        validate_store_project_boundary(store, project, remote)
        with store_lock(store):
            return function(store, project, *args, **kwargs)

    return wrapped


def _ensure_store_marker(store: Path, *, allow_initialize: bool = False) -> None:
    marker = store / STORE_MARKER
    if marker.is_symlink():
        raise StoreError("Relay store marker 不能是符号链接")
    has_head = _has_ref(store, "HEAD")
    if marker.is_file():
        try:
            content = marker.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise StoreError(f"无法读取 Relay store marker：{error}") from error
        if content != STORE_MARKER_CONTENT:
            try:
                marker_payload = json.loads(content)
            except json.JSONDecodeError:
                marker_payload = None
            if (
                isinstance(marker_payload, dict)
                and marker_payload.get("purpose") == "silvers-relay"
                and type(marker_payload.get("relay_store_schema")) is int
                and marker_payload["relay_store_schema"] != STORE_SCHEMA
            ):
                raise SchemaUnsupported(
                    component="relay_store",
                    cli_version=__version__,
                    supported_schema=STORE_SCHEMA,
                    encountered_schema=marker_payload["relay_store_schema"],
                )
            raise StoreError("Relay store marker 内容非法，拒绝接管仓库")
        tracked = _git_optional(
            store, "ls-files", "--error-unmatch", "--", str(STORE_MARKER)
        )
        if tracked.returncode:
            raise StoreError("Relay store marker 未被 Git 跟踪，拒绝接管仓库")
    else:
        if not allow_initialize:
            raise StoreError("现有 Git 仓库缺少 Relay 专用 marker，拒绝接管")
        if has_head:
            raise StoreError("Relay 远端缺少专用 marker，拒绝接管")
        refs = _git(store, "for-each-ref", "--format=%(refname)").splitlines()
        if refs:
            raise StoreError(
                "Relay 远端并非空仓库且缺少专用 marker，拒绝初始化：" + ", ".join(refs)
            )
        entries = [path for path in store.iterdir() if path.name != ".git"]
        if entries:
            raise StoreError("空 Git 仓库含有非 Relay 文件，拒绝接管")
        _atomic_write(marker, STORE_MARKER_CONTENT)
        try:
            _git(store, "add", "--", str(STORE_MARKER))
            with tempfile.TemporaryDirectory(prefix="silvers-relay-hooks-") as hooks:
                _git(
                    store,
                    "-c",
                    "user.name=Silvers Relay",
                    "-c",
                    "user.email=relay@localhost",
                    "-c",
                    f"core.hooksPath={hooks}",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "--no-verify",
                    "-qm",
                    "relay: initialize dedicated store",
                )
        except Exception as error:
            marker.unlink(missing_ok=True)
            _git_optional(
                store,
                "rm",
                "-q",
                "--cached",
                "--ignore-unmatch",
                "--",
                str(STORE_MARKER),
            )
            raise StoreError("无法初始化 Relay 专用 store marker") from error
    tracked_top_level = set(_git(store, "ls-tree", "--name-only", "HEAD").splitlines())
    unexpected = sorted(tracked_top_level - ALLOWED_STORE_TOP_LEVEL)
    if unexpected:
        raise StoreError(
            f"Relay store 含有协议外顶层路径，拒绝接管：{', '.join(unexpected)}"
        )
    tracked_files = _git(store, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    pairs: dict[tuple[str, str, str], set[str]] = {}
    for tracked in tracked_files:
        if tracked == STORE_MARKER.as_posix():
            continue
        parts = PurePosixPath(tracked).parts
        if len(parts) != 3 or parts[0] not in {"active", "done", "withdrawn"}:
            raise StoreError(f"Relay store 含有协议外嵌套路径：{tracked}")
        area, project_key, filename = parts
        if not re.fullmatch(r"[a-z0-9-]+", project_key):
            raise StoreError(f"Relay store project_key 路径非法：{tracked}")
        name = PurePosixPath(filename)
        if name.suffix not in {".json", ".md"} or not re.fullmatch(
            r"[0-9]{8}-[0-9]{6}-[0-9a-f]{8}", name.stem
        ):
            raise StoreError(f"Relay store 文件名或扩展名非法：{tracked}")
        pairs.setdefault((area, project_key, name.stem), set()).add(name.suffix)
    orphaned_exports = [
        f"{area}/{project_key}/{relay_id}"
        for (area, project_key, relay_id), suffixes in pairs.items()
        if ".json" not in suffixes
    ]
    if orphaned_exports:
        raise StoreError(
            "Relay store 存在没有 canonical JSON 的 Markdown 导出物："
            + ", ".join(sorted(orphaned_exports))
        )


def validate_store_project_boundary(
    store: Path,
    project: ProjectIdentity,
    remote: str | None,
) -> None:
    resolved_store = store.expanduser().resolve()
    project_root = project.root.resolve()
    if (
        resolved_store == project_root
        or resolved_store.is_relative_to(project_root)
        or project_root.is_relative_to(resolved_store)
    ):
        raise StoreError("Relay store 与当前业务项目路径重叠，拒绝操作")
    if remote:
        relay_remote = normalize_remote(remote, base=Path.cwd())
        if relay_remote in project.remote_urls:
            raise StoreError("Relay remote 与当前业务项目 origin 相同，拒绝操作")


def _git(store: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(store), *args],
        env=sanitized_git_environment(),
        text=True,
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise StoreError(f"Relay store Git 操作失败：{detail}")
    return result.stdout.strip()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _relay_id() -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _git_optional(store: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(store), *args],
        env=sanitized_git_environment(),
        text=True,
        capture_output=True,
    )


def _origin_urls(store: Path, *options: str) -> list[str]:
    result = _git_optional(store, "remote", "get-url", *options, "origin")
    if result.returncode:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _validate_origin_urls(store: Path, remote: str) -> None:
    expected = normalize_remote(remote, base=Path.cwd())
    fetch_urls = _origin_urls(store, "--all")
    push_urls = _origin_urls(store, "--push", "--all")
    if len(fetch_urls) != 1 or normalize_remote(fetch_urls[0], base=store) != expected:
        raise StoreError("Relay store origin fetch URL 与配置不匹配，拒绝操作")
    if len(push_urls) != 1 or normalize_remote(push_urls[0], base=store) != expected:
        raise StoreError("Relay store origin push URL 与配置不匹配，拒绝操作")


@_locked_store_operation
def ensure_store(store: Path, remote: str | None = None) -> None:
    store_existed = store.exists()
    initialized_here = False
    if not (store / ".git").is_dir():
        if store.exists() and any(store.iterdir()):
            raise StoreError(f"Relay store 目录已存在且非空，拒绝初始化或接管：{store}")
        if remote:
            store.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", "-q", "--origin", "origin", remote, str(store)],
                env=sanitized_git_environment(),
                text=True,
                capture_output=True,
            )
            if result.returncode:
                detail = result.stderr.strip() or result.stdout.strip()
                raise StoreError(f"无法克隆 Relay 远端：{detail}")
            initialized_here = True
        else:
            store.mkdir(parents=True, exist_ok=True)
            _git(store, "init", "-q", "-b", "main")
            initialized_here = True
    try:
        _ensure_store_marker(store, allow_initialize=initialized_here)
    except Exception:
        if initialized_here and store.exists():
            if store_existed:
                for child in store.iterdir():
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
            else:
                shutil.rmtree(store)
        raise
    if remote:
        if not _origin_urls(store, "--all"):
            _git(store, "remote", "add", "origin", remote)
        _validate_origin_urls(store, remote)


def _require_clean(store: Path) -> None:
    dirty = _git(
        store,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--ignored=matching",
    )
    if dirty:
        raise StoreDirty(f"Relay store 存在未提交内容，拒绝自动处理：\n{dirty}")


def _has_ref(store: Path, ref: str) -> bool:
    return _git_optional(store, "rev-parse", "--verify", "--quiet", ref).returncode == 0


@_locked_store_operation
def prepare_store(store: Path, remote: str | None = None) -> None:
    ensure_store(store, remote)
    _require_clean(store)
    if not remote:
        return
    _git(store, "fetch", "-q", "origin")
    if not _has_ref(store, "refs/remotes/origin/main"):
        remote_refs = _git(
            store,
            "for-each-ref",
            "--format=%(refname)",
            "refs/remotes/origin",
            "refs/tags",
        ).splitlines()
        if remote_refs:
            raise StoreError(
                "Relay remote 非空但缺少受支持的 main marker 分支，拒绝初始化"
            )
        if _has_ref(store, "HEAD"):
            _git(store, "push", "-q", "-u", "origin", "HEAD:main")
            _git(store, "fetch", "-q", "origin")
        _ensure_store_marker(store)
        _require_clean(store)
        return
    if not _has_ref(store, "HEAD"):
        _git(store, "checkout", "-q", "-B", "main", "origin/main")
        _ensure_store_marker(store)
        _require_clean(store)
        return
    counts = _git(store, "rev-list", "--left-right", "--count", "HEAD...origin/main")
    ahead_text, behind_text = counts.split()
    ahead, behind = int(ahead_text), int(behind_text)
    if ahead and behind:
        raise StoreError("Relay store 与远端已经分叉；禁止 merge/rebase，请人工处理")
    if ahead:
        _git(store, "push", "-q", "origin", "HEAD:main")
        _git(store, "fetch", "-q", "origin")
    elif behind:
        _git(store, "merge", "-q", "--ff-only", "origin/main")
    _ensure_store_marker(store)
    _require_clean(store)


@_locked_store_operation
def push_store(store: Path, remote: str | None) -> bool:
    if not remote:
        return False
    _validate_origin_urls(store, remote)
    _git(store, "push", "-q", "-u", "origin", "HEAD:main")
    return True


def _serialized_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _settle_result_bytes(result: dict[str, Any], field: str) -> int:
    result[field] = 0
    for _ in range(16):
        size = _serialized_bytes({"ok": True, "result": result})
        if result[field] == size:
            return size
        result[field] = size
    raise StoreError(f"Relay {field} 字节计数未收敛")


_BUDGET_BOOKKEEPING_FIELDS = {
    "budget_advice",
    "load_bytes",
    "max_load_bytes",
    "soft_load_bytes",
}


def budget_advice(
    result: dict[str, Any], response_bytes: int
) -> dict[str, Any] | None:
    """超过总软预算时点名最厚的顶层内容；只提示，不拒绝。"""

    if response_bytes <= SOFT_LOAD_BYTES:
        return None
    ranked = sorted(
        (
            (key, _serialized_bytes(value))
            for key, value in result.items()
            if key not in _BUDGET_BOOKKEEPING_FIELDS
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:3]
    return {
        "code": "load_over_soft_budget",
        "load_bytes": response_bytes,
        "soft_load_bytes": SOFT_LOAD_BYTES,
        "max_load_bytes": MAX_LOAD_BYTES,
        "overflow_bytes": response_bytes - SOFT_LOAD_BYTES,
        "heaviest_fields": [
            {
                "field": key,
                "bytes": size,
                "share": round(size * 100 / response_bytes, 1),
            }
            for key, size in ranked
        ],
        "message": (
            "Relay load 超过软预算，本次不拒绝。请先按 heaviest_fields 精炼一轮："
            "只删流水账、时间线、重复结论、日志与源码转储；"
            "决策四要素、逐条完成状态和仍有效约束不得删。"
            "若 active_decisions 过厚，只能显式 retire/supersede 已失效决策。"
        ),
    }


def settle_load_response(result: dict[str, Any]) -> int:
    """让 load_bytes 与统一软预算提示收敛到真实 CLI JSON 字节数。"""
    size = 0
    for _ in range(8):
        advice = budget_advice(result, size)
        if advice is None:
            result.pop("budget_advice", None)
        else:
            result["budget_advice"] = advice
        result["load_bytes"] = size
        encoded = len(
            json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode(
                "utf-8"
            )
        )
        if encoded == size:
            return size
        size = encoded
    result["load_bytes"] = size
    advice = budget_advice(result, size)
    if advice is None:
        result.pop("budget_advice", None)
    else:
        result["budget_advice"] = advice
    return size


def _sync_after_commit(
    store: Path, remote: str | None, local_result: dict[str, Any]
) -> bool:
    try:
        return push_store(store, remote)
    except StoreError as error:
        details = {
            **local_result,
            "local_committed": True,
            "synced": False,
        }
        raise SyncError(
            "Relay 已在本地提交，但远端同步失败；请保留返回的本地 revision，"
            "修复远端后重试同步或重新 load",
            details=details,
        ) from error


def _atomic_write(target: Path, rendered: str) -> None:
    encoded_size = len(rendered.encode("utf-8"))
    if encoded_size > MAX_LOAD_BYTES:
        raise StoreError(
            f"Relay 文件超过 {MAX_LOAD_BYTES} bytes 总硬上限：{encoded_size}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.stem}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _rollback_paths(
    store: Path,
    snapshots: dict[Path, bytes | None],
    original_error: Exception,
) -> None:
    """Restore only Relay paths touched by a failed local write/commit."""

    try:
        relatives: list[str] = []
        ordered_snapshots = sorted(
            snapshots.items(), key=lambda item: item[1] is not None
        )
        for target, previous in ordered_snapshots:
            relative = target.relative_to(store)
            relatives.append(str(relative))
            if previous is None:
                target.unlink(missing_ok=True)
                parent = target.parent
                while parent != store:
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
                result = _git_optional(
                    store,
                    "rm",
                    "-q",
                    "--cached",
                    "--ignore-unmatch",
                    "--",
                    str(relative),
                )
                if result.returncode:
                    detail = result.stderr.strip() or result.stdout.strip()
                    raise StoreError(f"Relay 回滚暂存区失败：{detail}")
            else:
                if not target.is_file() or target.read_bytes() != previous:
                    _atomic_write(target, previous.decode("utf-8"))
                _git(store, "add", "--", str(relative))
        dirty = _git_optional(
            store,
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignored=matching",
            "--",
            *relatives,
        )
        if dirty.returncode:
            detail = dirty.stderr.strip() or dirty.stdout.strip()
            raise StoreError(f"Relay 回滚状态检查失败：{detail}")
        if dirty.stdout.strip():
            raise StoreError(f"Relay 回滚后目标路径仍不干净：\n{dirty.stdout.strip()}")
    except Exception as rollback_error:
        raise StoreError(
            f"Relay 本地写入失败，且自动回滚也失败：{rollback_error}"
        ) from original_error


def _commit_with_rollback(
    store: Path,
    snapshots: dict[Path, bytes | None],
    relatives: list[Path],
    message: str,
) -> None:
    previous_head = _git(store, "rev-parse", "HEAD")
    committed = False
    try:
        _git(store, "add", "--", *(str(relative) for relative in relatives))
        with tempfile.TemporaryDirectory(prefix="silvers-relay-hooks-") as hooks:
            _git(
                store,
                "-c",
                "user.name=Silvers Relay",
                "-c",
                "user.email=relay@localhost",
                "-c",
                f"core.hooksPath={hooks}",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--no-verify",
                "-qm",
                message,
            )
        committed = True
        changed = set(
            _git(
                store,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "HEAD",
            ).splitlines()
        )
        expected = {relative.as_posix() for relative in relatives}
        if changed != expected:
            raise StoreError(
                "Relay commit 包含协议外路径，拒绝继续同步："
                f"actual {sorted(changed)}, expected {sorted(expected)}"
            )
        _ensure_store_marker(store)
        _require_clean(store)
    except Exception as error:
        if committed:
            reset = _git_optional(store, "reset", "-q", "--mixed", previous_head)
            if reset.returncode:
                detail = reset.stderr.strip() or reset.stdout.strip()
                raise StoreError(
                    f"Relay commit 复验失败，且无法恢复原 revision：{detail}"
                ) from error
        _rollback_paths(store, snapshots, error)
        raise


def _validate_expected_revision(expected_revision: int) -> None:
    if expected_revision < 1:
        raise InvalidRequest("expected revision 必须是正整数")


def validate_rendered_size(rendered: str) -> int:
    encoded_size = len(rendered.encode("utf-8"))
    if encoded_size > MAX_LOAD_BYTES:
        raise LoadTooLarge(
            f"Relay Markdown 超过 {MAX_LOAD_BYTES} bytes 总硬上限：{encoded_size}",
            details={
                "document_bytes": encoded_size,
                "max_load_bytes": MAX_LOAD_BYTES,
            },
        )
    return encoded_size


def preview_relay(request: dict[str, Any], project: ProjectSnapshot) -> dict[str, Any]:
    validate_request(request)
    now = _now()
    metadata = {
        "relay_schema": RELAY_SCHEMA,
        "relay_id": "preview",
        "project_key": project.key,
        "project_remote": project.remote,
        "title": request["title"],
        "status": "active",
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "last_client": "preview",
        "last_model": "preview",
        "last_machine": socket.gethostname(),
        "source_head": project.head,
        "source_branch": project.branch,
        "source_dirty": project.dirty,
    }
    validate_no_secrets(metadata, label="Relay 生成元数据")
    # 操作级预览会再用 planner 生成的真实派生文档覆盖 document_bytes；
    # 这里保留无存储上下文的快照预览，供根请求和独立调用使用。
    rendered = render_document(
        request,
        metadata,
        criteria_changes=[],
        phase_authorization=request.get("authorization"),
    )
    result = {
        "relay_schema": RELAY_SCHEMA,
        "document_bytes": validate_rendered_size(rendered),
        "max_load_bytes": MAX_LOAD_BYTES,
        "soft_load_bytes": SOFT_LOAD_BYTES,
    }
    return result


def _operation_target_hint(request: dict[str, Any]) -> tuple[str, str | None]:
    operation = request.get("operation")
    operation_command(operation)
    assert isinstance(operation, str)
    target = request.get("target")
    if target is None:
        return operation, None
    if not isinstance(target, dict):
        raise InvalidRequest("request.target 必须是 object 或 null")
    relay_id = target.get("relay_id")
    if not isinstance(relay_id, str):
        raise InvalidRequest("request.target.relay_id 必须是 string")
    validate_relay_id(relay_id)
    return operation, relay_id


def _resolve_operation_context_prepared(
    store: Path,
    project: ProjectSnapshot,
    *,
    operation: str,
    relay_id: str | None,
) -> OperationContext | None:
    if operation == "create":
        if relay_id is not None:
            raise InvalidRequest("create operation 不能选择现有 Relay")
        return None

    selected_status = "active"
    selected_path: Path | None = None
    if relay_id is not None:
        active_path = store / "active" / project.key / f"{relay_id}.json"
        if active_path.is_file():
            selected_path = active_path
        elif operation == "successor":
            done_path = store / "done" / project.key / f"{relay_id}.json"
            if done_path.is_file():
                selected_path = done_path
                selected_status = "done"
        if selected_path is None:
            raise RelayNotFound(f"找不到当前项目可用于 {operation} 的 Relay：{relay_id}")
    else:
        active = store / "active" / project.key
        _reject_symlink_path(store, active)
        items = sorted(active.glob("*.json")) if active.is_dir() else []
        if not items:
            raise RelayNotFound(f"当前项目没有活动 Relay：{project.key}")
        if len(items) > 1:
            raise SelectionRequired(
                "当前项目有多个活动 Relay；请从 relay list 选择 relay id"
            )
        selected_path = items[0]

    _, record, metadata = _validate_record_pair(
        store,
        selected_path,
        project,
        expected_status=selected_status,
    )
    return OperationContext(
        relay_id=metadata["relay_id"],
        revision=metadata["revision"],
        status=selected_status,
        record=record,
    )


def _prepare_store_for_preview(store: Path, remote: str | None) -> None:
    """Refresh remote refs without changing HEAD or any Relay document."""

    if not (store / ".git").is_dir():
        raise RelayNotFound("本机还没有可供 validate 读取的 Relay store")
    _ensure_store_marker(store)
    _require_clean(store)
    if remote is None:
        return
    _validate_origin_urls(store, remote)
    _git(store, "fetch", "-q", "origin")
    if not _has_ref(store, "refs/remotes/origin/main"):
        raise StoreError("Relay remote 缺少 main marker 分支")
    counts = _git(store, "rev-list", "--left-right", "--count", "HEAD...origin/main")
    ahead_text, behind_text = counts.split()
    if int(behind_text):
        raise StoreError(
            "本机 Relay store 落后或已分叉；validate 不会改写 canonical，"
            "请先重新生成 contextual draft 后再验证"
        )


@_locked_project_operation
def operation_context(
    store: Path,
    project: ProjectSnapshot,
    *,
    operation: OperationName | str,
    relay_id: str | None = None,
    remote: str | None = None,
) -> OperationContext | None:
    operation_command(operation)
    validate_store_project_boundary(store, project, remote)
    prepare_store(store, remote)
    return _resolve_operation_context_prepared(
        store,
        project,
        operation=operation,
        relay_id=relay_id,
    )


@_locked_project_operation
def preview_operation(
    store: Path,
    project: ProjectSnapshot,
    request: dict[str, Any],
    *,
    remote: str | None = None,
) -> dict[str, Any]:
    validate_store_project_boundary(store, project, remote)
    operation, relay_id = _operation_target_hint(request)
    if operation != "create":
        _prepare_store_for_preview(store, remote)
    context = _resolve_operation_context_prepared(
        store,
        project,
        operation=operation,
        relay_id=relay_id,
    )
    compiled = compile_operation(request, context)
    plan = _plan_operation(
        store,
        project,
        compiled,
        # validate 没有 client/model 参数，但实际写入会把它们渲染进正文和 load。
        # 用协议允许的最大长度做保守规划，保证 validate 通过后不会只因 writer
        # metadata 更长而在 apply 阶段撞同一道字节门。
        client=(None if isinstance(compiled, ValidatedWithdraw) else "p" * 64),
        model=(None if isinstance(compiled, ValidatedWithdraw) else "p" * 128),
    )
    preview: dict[str, Any]
    if isinstance(compiled, ValidatedCreate):
        preview = preview_relay(compiled.snapshot, project)
    elif isinstance(compiled, ValidatedUpdate):
        preview = preview_relay(compiled.updated, project)
    elif isinstance(compiled, ValidatedDone):
        preview = {
            **preview_relay(compiled.completed, project),
            "completion_status": "done",
        }
    elif isinstance(compiled, ValidatedSuccessor):
        preview = {
            "completion_status": "done",
            "successor_status": "active",
            "completion": preview_relay(compiled.completion, project),
            "successor": preview_relay(compiled.successor, project),
        }
    else:
        preview = {"status": "withdrawn", "reason": compiled.reason}
    if plan.load_preview is not None:
        load_preview = {
            key: deepcopy(plan.load_preview[key])
            for key in (
                "load_bytes",
                "max_load_bytes",
                "soft_load_bytes",
                "budget_advice",
            )
            if key in plan.load_preview
        }
        load_preview["document_bytes"] = len(
            plan.load_preview["document"].encode("utf-8")
        )
        load_preview["load_bytes_is_upper_bound"] = True
        if isinstance(compiled, ValidatedSuccessor):
            preview["successor"].update(load_preview)
        else:
            preview.update(load_preview)
    return {
        "valid": True,
        "operation": compiled.operation,
        "target": (
            None
            if compiled.target is None
            else {
                "relay_id": compiled.target.relay_id,
                "expected_revision": compiled.target.expected_revision,
            }
        ),
        "preview": preview,
    }


def execute_validated_operation(
    operation: ValidatedOperation,
    *,
    store: Path,
    project: ProjectSnapshot,
    client: str | None,
    model: str | None,
    remote: str | None,
    _execution_token: object | None = None,
) -> dict[str, Any]:
    operation = assert_validated_operation(operation)
    if _execution_token is not _EXECUTION_TOKEN:
        raise TypeError(
            "ValidatedOperation 只能由持有项目锁且刚完成 compile 的 apply_operation 执行"
        )
    if not isinstance(operation, ValidatedWithdraw) and (
        client is None or model is None
    ):
        raise InvalidRequest(f"{operation.operation} 需要 client 与 model")
    result = _run_transaction(
        store,
        project,
        operation,
        client=(None if isinstance(operation, ValidatedWithdraw) else client),
        model=(None if isinstance(operation, ValidatedWithdraw) else model),
        remote=remote,
        _execution_token=_EXECUTION_TOKEN,
    )
    result["operation"] = operation.operation
    result["commit"] = _git(store, "rev-parse", "HEAD")
    if isinstance(operation, ValidatedSuccessor):
        if operation.current_status == "active":
            predecessor = result["predecessor"]
            result["completed"] = {
                "relay_id": predecessor["relay_id"],
                "revision": predecessor["revision"],
                "status": predecessor["status"],
            }
        else:
            result["completed"] = {
                "relay_id": operation.target.relay_id,
                "revision": operation.target.actual_revision,
                "status": "done",
            }
        result["created"] = {
            "relay_id": result["relay_id"],
            "revision": result["revision"],
            "status": result["status"],
            "predecessor_relay_id": operation.target.relay_id,
        }
    return result


@_locked_project_operation
def apply_operation(
    store: Path,
    project: ProjectSnapshot,
    request: dict[str, Any],
    *,
    client: str | None,
    model: str | None,
    remote: str | None = None,
) -> dict[str, Any]:
    validate_store_project_boundary(store, project, remote)
    operation, relay_id = _operation_target_hint(request)
    prepare_store(store, remote)
    context = _resolve_operation_context_prepared(
        store,
        project,
        operation=operation,
        relay_id=relay_id,
    )
    # validate 之后仍可能有并发写入，因此执行必须在项目锁内重新读取并编译；
    # executor 永远不复用先前 validate 产生的对象。
    compiled = compile_operation(request, context)
    return execute_validated_operation(
        compiled,
        store=store,
        project=project,
        client=client,
        model=model,
        remote=remote,
        _execution_token=_EXECUTION_TOKEN,
    )


def _current_document_export() -> dict[str, Any]:
    return {
        "authoritative": False,
        "status": "current",
        "diagnostics": [],
    }


def _inspect_document_export(
    path: Path,
    expected_document: str,
) -> dict[str, Any]:
    expected_bytes = len(expected_document.encode("utf-8"))

    def issue(
        status: str,
        code: str,
        message: str,
        *,
        actual_bytes: int | None = None,
    ) -> dict[str, Any]:
        diagnostic: dict[str, Any] = {
            "code": code,
            "message": message,
            "expected_bytes": expected_bytes,
        }
        if actual_bytes is not None:
            diagnostic["actual_bytes"] = actual_bytes
        return {
            "authoritative": False,
            "status": status,
            "diagnostics": [diagnostic],
        }

    if not path.exists():
        return issue(
            "missing",
            "markdown_export_missing",
            "派生 Markdown 导出物缺失；load 已从 canonical JSON 现渲染。",
        )
    if not path.is_file():
        return issue(
            "unreadable",
            "markdown_export_unreadable",
            "派生 Markdown 导出物不是普通文件。",
        )
    try:
        actual_size = path.stat().st_size
    except OSError as error:
        return issue(
            "unreadable",
            "markdown_export_unreadable",
            f"无法读取派生 Markdown 导出物状态：{error}",
        )
    if actual_size > MAX_LOAD_BYTES:
        return issue(
            "modified",
            "markdown_export_too_large",
            "派生 Markdown 导出物超过文档上限；load 已从 canonical JSON 现渲染。",
            actual_bytes=actual_size,
        )
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_LOAD_BYTES + 1)
    except OSError as error:
        return issue(
            "unreadable",
            "markdown_export_unreadable",
            f"无法读取派生 Markdown 导出物：{error}",
        )
    if len(raw) > MAX_LOAD_BYTES:
        return issue(
            "modified",
            "markdown_export_too_large",
            "派生 Markdown 导出物超过文档上限；load 已从 canonical JSON 现渲染。",
            actual_bytes=len(raw),
        )
    try:
        actual_document = raw.decode("utf-8")
    except UnicodeDecodeError:
        return issue(
            "modified",
            "markdown_export_invalid_utf8",
            "派生 Markdown 导出物不是合法 UTF-8；load 已从 canonical JSON 现渲染。",
            actual_bytes=len(raw),
        )
    if actual_document != expected_document:
        return issue(
            "modified",
            "markdown_export_modified",
            "派生 Markdown 导出物与 canonical JSON 现渲染不同；load 已采用 canonical JSON。",
            actual_bytes=len(raw),
        )
    return _current_document_export()


def _read_bounded_canonical(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        raw_size = path.stat().st_size
    except OSError as error:
        raise StoreError(f"无法读取 Relay canonical JSON 状态：{path}：{error}") from error
    if raw_size > MAX_LOAD_BYTES:
        raise StoreError(
            f"Relay canonical JSON 超过 {MAX_LOAD_BYTES} bytes 总硬上限：{raw_size}"
        )
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_LOAD_BYTES + 1)
    except OSError as error:
        raise StoreError(f"无法读取 Relay canonical JSON：{path}：{error}") from error
    if len(raw) > MAX_LOAD_BYTES:
        raise StoreError(
            f"Relay canonical JSON 超过 {MAX_LOAD_BYTES} bytes 总硬上限：至少 {len(raw)}"
        )
    try:
        content = raw.decode("utf-8")
        parsed = json.loads(content)
    except UnicodeDecodeError as error:
        raise StoreError(f"Relay canonical JSON 不是合法 UTF-8：{path}") from error
    except json.JSONDecodeError as error:
        raise StoreError(f"Relay canonical JSON 格式非法：{path}") from error
    if not isinstance(parsed, dict):
        raise StoreError(f"Relay canonical JSON 必须是 object：{path}")
    return content, parsed


def _reject_symlink_path(store: Path, path: Path) -> None:
    current = path
    while current != store:
        if current.is_symlink():
            raise StoreError(f"Relay store 不允许符号链接路径：{current}")
        current = current.parent


def _require_record_versions(record: dict[str, Any]) -> None:
    relay_schema = record.get("relay_schema")
    if type(relay_schema) is not int:
        raise StoreError("Relay canonical relay_schema 必须是 integer")
    supported_pairs = {
        LEGACY_RELAY_SCHEMA: LEGACY_RENDER_VERSION,
        PREVIOUS_RELAY_SCHEMA: PREVIOUS_RENDER_VERSION,
        PHASE_LINEAGE_RELAY_SCHEMA: PHASE_LINEAGE_RENDER_VERSION,
        COMPLETION_STATUS_RELAY_SCHEMA: COMPLETION_STATUS_RENDER_VERSION,
        # 每个历史版本都用自己的固定常量入表。写 RELAY_SCHEMA: RENDER_VERSION
        # 的那一项会随版本号移动：下次升到 7，6/6 就静默从支持表里消失，
        # 所有 v6 档案当场变 schema_unsupported。
        PHASE_AUTHORIZATION_RELAY_SCHEMA: PHASE_AUTHORIZATION_RENDER_VERSION,
        RELAY_SCHEMA: RENDER_VERSION,
    }
    if relay_schema not in supported_pairs:
        raise SchemaUnsupported(
            component="relay_record",
            cli_version=__version__,
            supported_schema=RELAY_SCHEMA,
            encountered_schema=relay_schema,
        )
    render_version = record.get("render_version")
    if type(render_version) is not int:
        raise StoreError("Relay canonical render_version 必须是 integer")
    if render_version > RENDER_VERSION:
        raise SchemaUnsupported(
            component="relay_render",
            cli_version=__version__,
            supported_schema=RENDER_VERSION,
            encountered_schema=render_version,
        )
    expected_render_version = supported_pairs[relay_schema]
    if render_version != expected_render_version:
        raise StoreError(
            "Relay canonical schema/render 组合非法："
            f"relay_schema {relay_schema} 必须配 render_version "
            f"{expected_render_version}"
        )


def _validate_record_pair(
    store: Path,
    canonical_path: Path,
    project: ProjectSnapshot,
    *,
    expected_status: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    document_path = canonical_path.with_suffix(".md")
    _reject_symlink_path(store, canonical_path)
    _reject_symlink_path(store, document_path)
    if not canonical_path.is_file():
        raise StoreError(f"Relay 缺少 canonical JSON：{canonical_path.relative_to(store)}")

    canonical_text, record = _read_bounded_canonical(canonical_path)
    _require_record_versions(record)
    current_shape = "decision_id_high_watermark" in record
    if current_shape:
        expected_record_fields = {
            "relay_schema",
            "render_version",
            "metadata",
            "lineage",
            "snapshot",
            "decision_id_high_watermark",
            "criteria_changes",
        }
    else:
        expected_record_fields = {
            "relay_schema",
            "render_version",
            "metadata",
            "lineage",
            "snapshot",
            "decision_registry",
        }
        if record["relay_schema"] >= PREVIOUS_RELAY_SCHEMA:
            expected_record_fields.update({"criteria_registry", "criteria_changes"})
    if set(record) != expected_record_fields:
        raise StoreError("Relay canonical JSON 顶层字段非法")
    metadata = record["metadata"]
    if not isinstance(metadata, dict):
        raise StoreError("Relay canonical metadata 必须是 object")
    expected_metadata_fields = set(ACTIVE_METADATA_FIELDS) - {"relay_schema"}
    if expected_status == "done":
        expected_metadata_fields.add("done_at")
    elif expected_status == "withdrawn":
        expected_metadata_fields.update({"withdrawn_at", "withdraw_reason"})
    missing_metadata = sorted(expected_metadata_fields - metadata.keys())
    extra_metadata = sorted(metadata.keys() - expected_metadata_fields)
    if missing_metadata:
        raise StoreError(
            f"Relay canonical metadata 缺少字段：{', '.join(missing_metadata)}"
        )
    if extra_metadata:
        raise StoreError(
            f"Relay canonical metadata 包含未知字段：{', '.join(extra_metadata)}"
        )
    if type(metadata["revision"]) is not int or metadata["revision"] < 1:
        raise StoreError("Relay revision 必须是正整数")
    if type(metadata["source_dirty"]) is not bool:
        raise StoreError("Relay source_dirty 必须是 boolean")
    string_metadata = expected_metadata_fields - {"revision", "source_dirty"}
    for field in string_metadata:
        value = metadata[field]
        if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
            raise StoreError(f"Relay canonical metadata {field} 必须是非空单行字符串")
    if metadata["status"] != expected_status:
        raise StoreError(
            f"Relay status 不匹配：actual {metadata['status']}, expected {expected_status}"
        )
    if metadata["project_key"] != project.key:
        raise StoreError("Relay project_key 与当前项目不一致")
    if metadata["project_remote"] != project.remote:
        raise StoreError("Relay project_remote 与当前项目不一致")
    if metadata["relay_id"] != canonical_path.stem:
        raise StoreError("Relay canonical id 与文件名不一致")
    try:
        validate_relay_id(metadata["relay_id"])
    except InvalidRelayId as error:
        raise StoreError("Relay canonical 包含非法 relay id") from error

    snapshot = record["snapshot"]
    if not isinstance(snapshot, dict):
        raise StoreError("Relay canonical snapshot 必须是 object")
    phase = snapshot.get("phase")
    if not isinstance(phase, dict):
        raise StoreError("Relay canonical phase 必须是 object")
    if record["relay_schema"] >= PHASE_LINEAGE_RELAY_SCHEMA:
        if phase.get("phase_id") != metadata["relay_id"]:
            raise StoreError("Relay phase_id 必须与 relay_id 完全一致")
    elif "phase_id" in phase:
        raise StoreError("旧 Relay schema 不允许包含 phase_id")
    # 判据逐条状态是 schema 5 引入的，必须钉死在 COMPLETION_STATUS_RELAY_SCHEMA。
    # 写成 `< RELAY_SCHEMA` 会随当前版本号漂移：升到 6 的那一刻，合法的 v5
    # 档案就会被判成"旧 schema 不允许包含 done_when_status"。
    if (
        record["relay_schema"] < COMPLETION_STATUS_RELAY_SCHEMA
        and "done_when_status" in phase
    ):
        raise StoreError("旧 Relay schema 不允许包含 done_when_status")
    expected_snapshot_fields = materialized_object_fields(()) - {
        "decision_transitions",
        "criteria_transitions",
        "authorization",
    }
    if set(snapshot) != expected_snapshot_fields:
        missing = sorted(expected_snapshot_fields - snapshot.keys())
        extra = sorted(snapshot.keys() - expected_snapshot_fields)
        detail = []
        if missing:
            detail.append("缺少 " + ", ".join(missing))
        if extra:
            detail.append("多出 " + ", ".join(extra))
        raise StoreError("Relay canonical snapshot 字段非法：" + "；".join(detail))
    try:
        validate_request(
            request_from_snapshot(snapshot),
            allow_legacy_phase_status=(
                record["relay_schema"] < COMPLETION_STATUS_RELAY_SCHEMA
            ),
            allow_legacy_baton_limits=(
                record["relay_schema"] < PHASE_AUTHORIZATION_RELAY_SCHEMA
            ),
        )
    except InvalidRequest as error:
        raise StoreError(f"Relay canonical snapshot 非法：{error}") from error
    if metadata["title"] != snapshot["title"]:
        raise StoreError("Relay metadata title 与 snapshot title 不一致")

    lineage = record["lineage"]
    expected_lineage_fields = {
        "predecessor_relay_id",
        "predecessor_revision",
    }
    if record["relay_schema"] >= PHASE_LINEAGE_RELAY_SCHEMA:
        expected_lineage_fields.add("predecessor_summary")
    if record["relay_schema"] >= PHASE_AUTHORIZATION_RELAY_SCHEMA:
        expected_lineage_fields.add("phase_authorization")
    # 结构校验必须排在任何字段读取之前。lineage 损坏成 null 或 {} 时先读字段，
    # 抛出的是裸 AttributeError / KeyError——它们不在 CLI 的捕获范围内，用户
    # 看到的会是 Python traceback 而不是结构化 store_error。
    if not isinstance(lineage, dict) or set(lineage) != expected_lineage_fields:
        raise StoreError("Relay lineage 字段非法")
    if record["relay_schema"] >= PHASE_AUTHORIZATION_RELAY_SCHEMA:
        authorization = lineage.get("phase_authorization")
        # 只校验"字段在"是不够的：整数 0 之类的非法值会被渲染成"根棒，无前序
        # 阶段"，正好把一根推进出来的棒伪装成根棒，掩盖它真实的来历。
        if authorization is not None:
            try:
                validate_authorization(
                    authorization, path="lineage.phase_authorization"
                )
            except InvalidRequest as error:
                raise StoreError(
                    f"Relay lineage.phase_authorization 非法：{error}"
                ) from error
        if lineage["predecessor_relay_id"] is None and authorization is not None:
            raise StoreError("根 Relay 的 phase_authorization 必须为 null")
    predecessor = snapshot["phase"]["predecessor_relay_id"]
    if lineage["predecessor_relay_id"] != predecessor:
        raise StoreError("Relay lineage 与 phase.predecessor_relay_id 不一致")
    predecessor_revision = lineage["predecessor_revision"]
    if predecessor is None:
        if predecessor_revision is not None:
            raise StoreError("无前序 Relay 时 predecessor_revision 必须是 null")
    elif type(predecessor_revision) is not int or predecessor_revision < 1:
        raise StoreError("有前序 Relay 时 predecessor_revision 必须是正整数")
    if record["relay_schema"] >= PHASE_LINEAGE_RELAY_SCHEMA:
        predecessor_summary = lineage["predecessor_summary"]
        if predecessor is None:
            if predecessor_summary is not None:
                raise StoreError("无前序 Relay 时 predecessor_summary 必须是 null")
        else:
            expected_summary_fields = {
                "relay_id",
                "revision",
                "phase_id",
                "phase_outcome",
                "done_when",
                "evidence_count",
            }
            # status_source / status_note 自 schema 5 起存在。这里必须钉死
            # 引入版本并用 >=，写 `== RELAY_SCHEMA` 会在每次升版时把上一版
            # 记录挡在门外。
            if (
                record["relay_schema"]
                >= COMPLETION_STATUS_RELAY_SCHEMA
            ):
                expected_summary_fields.update(
                    {"status_source", "status_note"}
                )
            if not isinstance(predecessor_summary, dict) or set(
                predecessor_summary
            ) != expected_summary_fields:
                raise StoreError("Relay predecessor_summary 字段非法")
            if (
                predecessor_summary["relay_id"] != predecessor
                or predecessor_summary["revision"] != predecessor_revision
                or predecessor_summary["phase_id"] != predecessor
            ):
                raise StoreError("Relay predecessor_summary 档案指针不一致")
            if (
                not isinstance(predecessor_summary["phase_outcome"], str)
                or not predecessor_summary["phase_outcome"].strip()
            ):
                raise StoreError("Relay predecessor_summary 阶段交付非法")
            summary_done_when = predecessor_summary["done_when"]
            if not isinstance(summary_done_when, list) or not summary_done_when:
                raise StoreError("Relay predecessor_summary 完成标准非法")
            for item in summary_done_when:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("criterion"), str)
                    or not item["criterion"].strip()
                ):
                    raise StoreError("Relay predecessor_summary 达成情况非法")
                if record["relay_schema"] == PHASE_LINEAGE_RELAY_SCHEMA:
                    if (
                        set(item) != {"criterion", "status"}
                        or item["status"] != "met"
                    ):
                        raise StoreError("Relay predecessor_summary 达成情况非法")
                    continue
                if set(item) != {
                    "criterion",
                    "status",
                    "reason",
                }:
                    raise StoreError("Relay predecessor_summary 达成情况非法")
                status = item["status"]
                reason = item["reason"]
                source = predecessor_summary["status_source"]
                note = predecessor_summary["status_note"]
                if source == "declared":
                    if note is not None:
                        raise StoreError("Relay predecessor_summary 声明来源备注必须为空")
                    if status not in {"met", "partial", "unverifiable"}:
                        raise StoreError("Relay predecessor_summary 达成状态非法")
                    if status == "met" and reason is not None:
                        raise StoreError("Relay predecessor_summary met 原因必须为空")
                    if status != "met" and (
                        not isinstance(reason, str) or not reason.strip()
                    ):
                        raise StoreError("Relay predecessor_summary 非完成状态缺少原因")
                elif source == "legacy_inferred":
                    if (
                        status != "unknown"
                        or reason is not None
                        or not isinstance(note, str)
                        or not note.strip()
                    ):
                        raise StoreError("Relay predecessor_summary 历史推定非法")
                else:
                    raise StoreError("Relay predecessor_summary 来源非法")
            if (
                type(predecessor_summary["evidence_count"]) is not int
                or predecessor_summary["evidence_count"] < 1
            ):
                raise StoreError("Relay predecessor_summary 证据计数非法")

    if current_shape:
        watermark = record["decision_id_high_watermark"]
        if type(watermark) is not int or not 0 <= watermark <= 999:
            raise StoreError("Relay decision_id_high_watermark 非法")
        highest_decision = max(
            (
                int(decision["id"].split("-", 1)[1])
                for decision in snapshot["decisions"]
            ),
            default=0,
        )
        if watermark < highest_decision:
            raise StoreError(
                "Relay decision_id_high_watermark 不能小于活动决策最大 ID"
            )
        criteria_changes = record["criteria_changes"]
        if not isinstance(criteria_changes, list):
            raise StoreError("Relay criteria_changes 必须是 array")
        transition_fields = {
            "ordinal",
            "field",
            "id_or_text",
            "action",
            "replacement",
            "reason",
            "authorized_by",
        }
        for index, change in enumerate(criteria_changes, start=1):
            if not isinstance(change, dict) or set(change) != transition_fields:
                raise StoreError(f"Relay criteria_changes[{index - 1}] 字段非法")
            if change["ordinal"] != index:
                raise StoreError("Relay criteria_changes.ordinal 必须从 1 连续递增")
        try:
            criteria_request = request_from_snapshot(snapshot)
            criteria_request["criteria_transitions"] = [
                {key: value for key, value in change.items() if key != "ordinal"}
                for change in criteria_changes
            ]
            validate_request(criteria_request)
        except InvalidRequest as error:
            raise StoreError(f"Relay criteria_changes 非法：{error}") from error
        validate_no_secrets(record, label="Relay canonical JSON")
        expected_document = render_record(record)
        validate_rendered_size(expected_document)
        if canonical_text != serialize_record(record):
            raise StoreError("Relay canonical JSON 不是协议规定的确定性序列化格式")
        return expected_document, record, metadata

    registry = record["decision_registry"]
    if not isinstance(registry, dict) or set(registry) != {"next_id", "active"}:
        raise StoreError("Relay decision_registry 字段非法")
    if type(registry["next_id"]) is not int or not 1 <= registry["next_id"] <= 1000:
        raise StoreError("Relay decision_registry.next_id 非法")
    active = registry["active"]
    if not isinstance(active, list):
        raise StoreError("Relay 活动决策注册表数量非法")
    registry_by_id: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(active):
        if not isinstance(entry, dict) or set(entry) != {
            "id",
            "status",
            "label",
            "source_relay_id",
            "source_revision",
        }:
            raise StoreError(f"Relay decision_registry.active[{index}] 字段非法")
        decision_id = entry["id"]
        if not isinstance(decision_id, str) or not re.fullmatch(
            r"D-[0-9]{3}", decision_id
        ):
            raise StoreError(f"Relay decision_registry.active[{index}].id 非法")
        if decision_id in registry_by_id:
            raise StoreError(f"Relay 活动决策 ID 重复：{decision_id}")
        if entry["status"] not in {"locked", "tentative", "reopenable"}:
            raise StoreError(f"Relay 活动决策状态非法：{decision_id}")
        if (
            not isinstance(entry["label"], str)
            or not entry["label"]
            or "\n" in entry["label"]
            or "\r" in entry["label"]
        ):
            raise StoreError(f"Relay 活动决策短标签非法：{decision_id}")
        try:
            validate_relay_id(entry["source_relay_id"])
        except (InvalidRelayId, TypeError) as error:
            raise StoreError(f"Relay 活动决策来源 id 非法：{decision_id}") from error
        if type(entry["source_revision"]) is not int or entry["source_revision"] < 1:
            raise StoreError(f"Relay 活动决策来源 revision 非法：{decision_id}")
        registry_by_id[decision_id] = entry
    if list(registry_by_id) != sorted(registry_by_id):
        raise StoreError("Relay 活动决策注册表必须按 ID 排序")
    highest_id = max(
        (int(decision_id.split("-", 1)[1]) for decision_id in registry_by_id),
        default=0,
    )
    if registry["next_id"] <= highest_id:
        raise StoreError("Relay decision_registry.next_id 必须大于所有已分配 ID")
    for decision in snapshot["decisions"]:
        entry = registry_by_id.get(decision["id"])
        if entry is None:
            raise StoreError(f"当前详细决策未登记为活动决策：{decision['id']}")
        if entry["status"] != decision["status"] or entry["label"] != decision["label"]:
            raise StoreError(f"当前详细决策与活动索引不一致：{decision['id']}")
        if (
            entry["source_relay_id"] != metadata["relay_id"]
            or entry["source_revision"] != metadata["revision"]
        ):
            raise StoreError(f"当前详细决策来源指针必须指向当前 revision：{decision['id']}")

    if record["relay_schema"] >= PREVIOUS_RELAY_SCHEMA:
        criteria_registry = record["criteria_registry"]
        if not isinstance(criteria_registry, dict) or set(criteria_registry) != {
            "next_id",
            "changes",
        }:
            raise StoreError("Relay criteria_registry 字段非法")
        criteria_next_id = criteria_registry["next_id"]
        if (
            type(criteria_next_id) is not int
            or not 1 <= criteria_next_id <= 1000
        ):
            raise StoreError("Relay criteria_registry.next_id 非法")
        criteria_pointers = criteria_registry["changes"]
        if not isinstance(criteria_pointers, list):
            raise StoreError("Relay 判据变更注册表数量非法")
        pointer_by_id: dict[str, dict[str, Any]] = {}
        protected_fields = {
            "phase.outcome",
            "phase.done_when",
            "design.invariants",
            "design.non_goals",
        }
        criteria_actions = {
            "removed",
            "weakened",
            "merged_into",
            "strengthened",
            "added",
        }
        for index, entry in enumerate(criteria_pointers):
            if not isinstance(entry, dict) or set(entry) != {
                "id",
                "field",
                "action",
                "label",
                "authorized",
                "source_relay_id",
                "source_revision",
            }:
                raise StoreError(
                    f"Relay criteria_registry.changes[{index}] 字段非法"
                )
            change_id = entry["id"]
            if not isinstance(change_id, str) or not re.fullmatch(
                r"C-[0-9]{3}", change_id
            ):
                raise StoreError(
                    f"Relay criteria_registry.changes[{index}].id 非法"
                )
            if change_id in pointer_by_id:
                raise StoreError(f"Relay 判据变更 ID 重复：{change_id}")
            if entry["field"] not in protected_fields:
                raise StoreError(f"Relay 判据变更字段非法：{change_id}")
            if entry["action"] not in criteria_actions:
                raise StoreError(f"Relay 判据变更 action 非法：{change_id}")
            if (
                not isinstance(entry["label"], str)
                or not entry["label"]
                or "\n" in entry["label"]
                or "\r" in entry["label"]
            ):
                raise StoreError(f"Relay 判据变更短标签非法：{change_id}")
            if type(entry["authorized"]) is not bool:
                raise StoreError(f"Relay 判据变更授权标记非法：{change_id}")
            if entry["source_relay_id"] != metadata["relay_id"]:
                raise StoreError(f"Relay 判据变更来源 baton 非法：{change_id}")
            source_revision = entry["source_revision"]
            if (
                type(source_revision) is not int
                or not 1 <= source_revision <= metadata["revision"]
            ):
                raise StoreError(
                    f"Relay 判据变更来源 revision 非法：{change_id}"
                )
            pointer_by_id[change_id] = entry
        if list(pointer_by_id) != sorted(pointer_by_id):
            raise StoreError("Relay 判据变更注册表必须按 ID 排序")
        highest_criteria_id = max(
            (
                int(change_id.split("-", 1)[1])
                for change_id in pointer_by_id
            ),
            default=0,
        )
        if criteria_next_id <= highest_criteria_id:
            raise StoreError(
                "Relay criteria_registry.next_id 必须大于所有已分配 ID"
            )

        criteria_changes = record["criteria_changes"]
        if not isinstance(criteria_changes, list) or len(criteria_changes) > 32:
            raise StoreError("Relay 当前 revision 判据变更数量非法")
        change_by_id: dict[str, dict[str, Any]] = {}
        transition_fields = {
            "field",
            "id_or_text",
            "action",
            "replacement",
            "reason",
            "authorized_by",
        }
        for index, change in enumerate(criteria_changes):
            if not isinstance(change, dict) or set(change) != {
                "id",
                *transition_fields,
            }:
                raise StoreError(f"Relay criteria_changes[{index}] 字段非法")
            change_id = change["id"]
            if not isinstance(change_id, str) or not re.fullmatch(
                r"C-[0-9]{3}", change_id
            ):
                raise StoreError(f"Relay criteria_changes[{index}].id 非法")
            if change_id in change_by_id:
                raise StoreError(f"Relay 当前判据变更 ID 重复：{change_id}")
            change_by_id[change_id] = change
        if list(change_by_id) != sorted(change_by_id):
            raise StoreError("Relay 当前判据变更必须按 ID 排序")
        try:
            criteria_request = request_from_snapshot(snapshot)
            criteria_request["criteria_transitions"] = [
                {
                    key: value
                    for key, value in change.items()
                    if key != "id"
                }
                for change in criteria_changes
            ]
            validate_request(
                criteria_request,
                allow_legacy_phase_status=(
                    record["relay_schema"] < COMPLETION_STATUS_RELAY_SCHEMA
                ),
                allow_legacy_baton_limits=(
                    record["relay_schema"] < PHASE_AUTHORIZATION_RELAY_SCHEMA
                ),
            )
        except InvalidRequest as error:
            raise StoreError(f"Relay criteria_changes 非法：{error}") from error
        current_pointer_ids = {
            change_id
            for change_id, entry in pointer_by_id.items()
            if entry["source_revision"] == metadata["revision"]
        }
        if set(change_by_id) != current_pointer_ids:
            raise StoreError(
                "Relay criteria_changes 与当前 revision 冷索引指针不一致"
            )
        for change_id, change in change_by_id.items():
            pointer = pointer_by_id[change_id]
            if (
                pointer["field"] != change["field"]
                or pointer["action"] != change["action"]
                or pointer["label"] != criteria_transition_label(change)
                or pointer["authorized"]
                != (change["authorized_by"] is not None)
            ):
                raise StoreError(
                    f"Relay 判据变更详情与冷索引不一致：{change_id}"
                )

    validate_no_secrets(record, label="Relay canonical JSON")
    expected_document = render_record(record)
    validate_rendered_size(expected_document)
    if canonical_text != serialize_record(record):
        raise StoreError("Relay canonical JSON 不是协议规定的确定性序列化格式")
    return expected_document, record, metadata


def _previous_record_for_path(
    store: Path,
    canonical_path: Path,
) -> dict[str, Any] | None:
    relative = canonical_path.relative_to(store).as_posix()
    commits = _git(
        store,
        "log",
        "--format=%H",
        "--",
        relative,
    ).splitlines()
    if len(commits) < 2:
        return None
    content = _git(store, "show", f"{commits[1]}:{relative}")
    try:
        previous = json.loads(content)
    except json.JSONDecodeError as error:
        raise StoreError("Relay 上一 revision 的 canonical JSON 已损坏") from error
    if not isinstance(previous, dict):
        raise StoreError("Relay 上一 revision 的 canonical JSON schema 非法")
    _require_record_versions(previous)
    return previous


def _record_at_revision(
    store: Path,
    project: ProjectSnapshot,
    *,
    relay_id: str,
    revision: int,
) -> dict[str, Any]:
    active_relative = (
        Path("active") / project.key / f"{relay_id}.json"
    ).as_posix()
    done_relative = (Path("done") / project.key / f"{relay_id}.json").as_posix()
    commits = _git(
        store,
        "log",
        "--format=%H",
        "--",
        active_relative,
        done_relative,
    ).splitlines()
    for commit in commits:
        for relative in (done_relative, active_relative):
            shown = _git_optional(store, "show", f"{commit}:{relative}")
            if shown.returncode:
                continue
            try:
                record = json.loads(shown.stdout)
            except json.JSONDecodeError as error:
                raise StoreError(
                    f"Relay 历史 revision {revision} 的 canonical JSON 已损坏"
                ) from error
            if not isinstance(record, dict):
                raise StoreError("Relay 历史 canonical JSON 必须是 object")
            _require_record_versions(record)
            metadata = record.get("metadata")
            if (
                isinstance(metadata, dict)
                and metadata.get("relay_id") == relay_id
                and metadata.get("revision") == revision
            ):
                if metadata.get("project_key") != project.key or metadata.get(
                    "project_remote"
                ) != project.remote:
                    raise StoreError("Relay 历史记录与当前项目身份不一致")
                return record
    raise RelayNotFound(f"找不到 Relay {relay_id} 的 revision {revision}")


LEGACY_COMPLETION_STATUS_REASON = (
    "Relay v4 及更早版本未保存逐条完成声明；旧版 met 是历史推定，"
    "不能当作已验证真值。"
)


def _completion_summary(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record["metadata"]
    phase = record["snapshot"]["phase"]
    declared = phase.get("done_when_status")
    if declared is None:
        done_when = [
            {
                "criterion": criterion,
                "status": "unknown",
                "reason": None,
            }
            for criterion in phase["done_when"]
        ]
        status_source = "legacy_inferred"
        status_note = LEGACY_COMPLETION_STATUS_REASON
    else:
        done_when = [
            {
                "criterion": criterion,
                "status": status["status"],
                "reason": status["reason"],
            }
            for criterion, status in zip(
                phase["done_when"],
                declared,
                strict=True,
            )
        ]
        status_source = "declared"
        status_note = None
    return {
        "relay_id": metadata["relay_id"],
        "revision": metadata["revision"],
        "phase_id": phase.get("phase_id", metadata["relay_id"]),
        "phase_outcome": phase["outcome"],
        "done_when": done_when,
        "status_source": status_source,
        "status_note": status_note,
        "evidence_count": len(record["snapshot"]["state"]["evidence"]),
    }


def _normalize_predecessor_summary(
    summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if summary is None:
        return None
    normalized = deepcopy(summary)
    if all(
        key in normalized for key in ("status_source", "status_note")
    ):
        return normalized
    normalized["done_when"] = [
        {
            "criterion": item["criterion"],
            "status": "unknown",
            "reason": None,
        }
        for item in normalized["done_when"]
    ]
    normalized["status_source"] = "legacy_inferred"
    normalized["status_note"] = LEGACY_COMPLETION_STATUS_REASON
    return normalized


def _phase_completion_for_record(record: dict[str, Any]) -> dict[str, Any]:
    phase = record["snapshot"]["phase"]
    declared = phase.get("done_when_status")
    if declared is None:
        return {
            "criterion_count": len(phase["done_when"]),
            "status_count": len(phase["done_when"]),
            "alignment_complete": True,
            "source": "legacy_missing",
            "items": [
                {"index": index, "status": "unknown", "reason": None}
                for index in range(1, len(phase["done_when"]) + 1)
            ],
            "note": LEGACY_COMPLETION_STATUS_REASON,
        }
    return {
        "criterion_count": len(phase["done_when"]),
        "status_count": len(declared),
        "alignment_complete": len(phase["done_when"]) == len(declared),
        "source": "declared",
        "items": [
            {
                "index": index,
                "status": item["status"],
                "reason": item["reason"],
            }
            for index, item in enumerate(declared, start=1)
        ],
    }


def _predecessor_summary_for_record(
    store: Path,
    project: ProjectSnapshot,
    record: dict[str, Any],
) -> dict[str, Any] | None:
    lineage = record["lineage"]
    if "predecessor_summary" in lineage:
        return _normalize_predecessor_summary(lineage["predecessor_summary"])
    predecessor_id = lineage["predecessor_relay_id"]
    predecessor_revision = lineage["predecessor_revision"]
    if predecessor_id is None:
        return None
    predecessor = _record_at_revision(
        store,
        project,
        relay_id=predecessor_id,
        revision=predecessor_revision,
    )
    return _completion_summary(predecessor)


@dataclass(frozen=True)
class _StoredTransactionTarget:
    record: dict[str, Any]
    metadata: dict[str, Any]
    canonical_relative: Path
    document_relative: Path
    canonical_path: Path
    document_path: Path


@dataclass(frozen=True)
class _TransactionPlan:
    writes: tuple[tuple[Path, str], ...]
    deletes: tuple[Path, ...]
    create_paths: tuple[Path, ...]
    message: str
    result: dict[str, Any]
    failure_message: str
    load_preview: dict[str, Any] | None = None


@dataclass(frozen=True)
class _RecordArtifact:
    record: dict[str, Any]
    canonical: str
    document: str


def _record_metadata(
    project: ProjectSnapshot,
    *,
    relay_id: str,
    title: str,
    status: str,
    revision: int,
    created_at: str,
    updated_at: str,
    client: str,
    model: str,
    status_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "relay_id": relay_id,
        "project_key": project.key,
        "project_remote": project.remote,
        "title": title,
        "status": status,
        "revision": revision,
        "created_at": created_at,
        "updated_at": updated_at,
        **(status_fields or {}),
        "last_client": client,
        "last_model": model,
        "last_machine": socket.gethostname(),
        "source_head": project.head,
        "source_branch": project.branch,
        "source_dirty": project.dirty,
    }


def _build_record_artifact(
    request: dict[str, Any],
    metadata: dict[str, Any],
    *,
    decision_id_high_watermark: int,
    criteria_changes: list[dict[str, Any]],
    predecessor_revision: int | None,
    predecessor_summary: dict[str, Any] | None,
    phase_authorization: str | None,
) -> _RecordArtifact:
    record = build_record(
        request,
        metadata,
        decision_id_high_watermark=decision_id_high_watermark,
        criteria_changes=criteria_changes,
        predecessor_revision=predecessor_revision,
        predecessor_summary=predecessor_summary,
        phase_authorization=phase_authorization,
    )
    document = render_record(record)
    validate_rendered_size(document)
    return _RecordArtifact(
        record=record,
        canonical=serialize_record(record),
        document=document,
    )


def _load_transaction_target(
    store: Path,
    project: ProjectSnapshot,
    operation: ValidatedOperation,
) -> _StoredTransactionTarget | None:
    target = operation.target
    if target is None:
        return None
    status = (
        operation.current_status
        if isinstance(operation, ValidatedSuccessor)
        else "active"
    )
    area = "done" if status == "done" else "active"
    canonical_relative = Path(area) / project.key / f"{target.relay_id}.json"
    document_relative = Path(area) / project.key / f"{target.relay_id}.md"
    canonical_path = store / canonical_relative
    document_path = store / document_relative
    if not canonical_path.is_file():
        label = "已完成" if status == "done" else "活动"
        raise RelayNotFound(f"找不到{label} Relay：{target.relay_id}")
    _, record, metadata = _validate_record_pair(
        store,
        canonical_path,
        project,
        expected_status=status,
    )
    actual_revision = metadata["revision"]
    if actual_revision != target.actual_revision:
        raise StaleRevision(
            "Relay revision 已变化："
            f"expected {target.expected_revision}, actual {actual_revision}；"
            "请重新生成草稿",
            details={
                "relay_id": target.relay_id,
                "expected_revision": target.expected_revision,
                "actual_revision": actual_revision,
            },
        )
    if metadata.get("project_remote") != project.remote:
        raise StoreError("Relay 项目身份与当前项目不一致")
    return _StoredTransactionTarget(
        record=record,
        metadata=metadata,
        canonical_relative=canonical_relative,
        document_relative=document_relative,
        canonical_path=canonical_path,
        document_path=document_path,
    )


def _canonicalize_request(
    request: dict[str, Any],
    *,
    relay_id: str,
    revision: int,
    previous_active_decisions: list[dict[str, Any]],
    decision_id_high_watermark: int,
    active_decision_ids: list[str],
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    snapshot = deepcopy(request)
    decision_transitions = snapshot.pop("decision_transitions")
    criteria_transitions = snapshot.pop("criteria_transitions")
    snapshot.pop("authorization", None)
    snapshot["phase"].pop("predecessor_relay_id", None)
    canonical = build_canonical_revision(
        relay_id=relay_id,
        revision=revision,
        snapshot=snapshot,
        previous_active_decisions=previous_active_decisions,
        decision_id_high_watermark=decision_id_high_watermark,
        decision_transitions=decision_transitions,
        criteria_transitions=criteria_transitions,
        active_decision_ids=active_decision_ids,
    )
    materialized = deepcopy(request)
    materialized["decisions"] = canonical["snapshot"]["decisions"]
    return (
        materialized,
        canonical["decision_id_high_watermark"],
        canonical["criteria_transition_receipt"]["changes"],
    )


def _record_active_decisions(
    store: Path,
    project: ProjectSnapshot,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    if "decision_registry" not in record:
        return deepcopy(record["snapshot"]["decisions"])
    return _resolve_legacy_active_decisions(store, project, record)


def _record_decision_high_watermark(record: dict[str, Any]) -> int:
    if "decision_id_high_watermark" in record:
        return int(record["decision_id_high_watermark"])
    return max(0, int(record["decision_registry"]["next_id"]) - 1)


def _materialize_canonical_request(
    store: Path,
    project: ProjectSnapshot,
    request: dict[str, Any],
    *,
    relay_id: str,
    revision: int,
    previous_record: dict[str, Any] | None,
    active_decision_ids: list[str],
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    if previous_record is None:
        previous_active: list[dict[str, Any]] = []
        watermark = 0
    else:
        previous_active = _record_active_decisions(store, project, previous_record)
        watermark = _record_decision_high_watermark(previous_record)
    return _canonicalize_request(
        request,
        relay_id=relay_id,
        revision=revision,
        previous_active_decisions=previous_active,
        decision_id_high_watermark=watermark,
        active_decision_ids=active_decision_ids,
    )


def _run_transaction(
    store: Path,
    project: ProjectSnapshot,
    operation: ValidatedOperation,
    *,
    client: str | None,
    model: str | None,
    remote: str | None,
    _execution_token: object | None,
) -> dict[str, Any]:
    operation = assert_validated_operation(operation)
    if _execution_token is not _EXECUTION_TOKEN:
        raise TypeError("transaction runner 只能由 executor 调用")
    validate_store_project_boundary(store, project, remote)
    if client is not None or model is not None:
        if client is None or model is None:
            raise InvalidRequest("写入 Relay 需要 client 与 model")
        validate_writer_metadata(client, model)
    plan = _plan_operation(
        store,
        project,
        operation,
        client=client,
        model=model,
    )
    return _apply_transaction_plan(store, plan, remote=remote)


def _apply_transaction_plan(
    store: Path,
    plan: _TransactionPlan,
    *,
    remote: str | None,
) -> dict[str, Any]:
    """执行一份完整事务计划，并统一承担本地回滚与远端同步。"""

    write_paths = tuple(path for path, _ in plan.writes)
    if set(write_paths) & set(plan.deletes):
        raise StoreError("Relay 事务不能同时写入并删除同一路径")
    # create_paths 是 planner 声明的事务后置条件，不只是一组覆盖保护。
    # 即使某次重构误删了对应 write，它仍须进入 git pathspec；否则“旧棒已归档、
    # 新棒没写出”的半事务会被当作一笔合法 commit。
    touched = tuple(
        dict.fromkeys((*write_paths, *plan.deletes, *plan.create_paths))
    )
    for path in touched:
        _reject_symlink_path(store, path)
    for path in plan.create_paths:
        if path.exists():
            raise StoreError(
                f"Relay 事务目标已经存在：{path.relative_to(store)}"
            )
    for path in plan.deletes:
        if not path.is_file():
            raise StoreError(
                f"Relay 事务删除目标不存在：{path.relative_to(store)}"
            )
    snapshots = {
        path: path.read_bytes() if path.is_file() else None for path in touched
    }
    try:
        for path, content in plan.writes:
            _atomic_write(path, content)
        for path in plan.deletes:
            path.unlink()
    except Exception as error:
        _rollback_paths(store, snapshots, error)
        raise StoreError(plan.failure_message) from error
    relatives = [path.relative_to(store) for path in touched]
    _commit_with_rollback(store, snapshots, relatives, plan.message)
    result = deepcopy(plan.result)
    if plan.load_preview is not None and "budget_advice" in plan.load_preview:
        result["budget_advice"] = deepcopy(plan.load_preview["budget_advice"])
    result["synced"] = _sync_after_commit(store, remote, result)
    return result


def _migration_tip_paths(
    store: Path,
    project: ProjectSnapshot,
) -> list[tuple[str, Path]]:
    tips: list[tuple[str, Path]] = []
    for status in ("active", "done", "withdrawn"):
        directory = store / status / project.key
        _reject_symlink_path(store, directory)
        if not directory.is_dir():
            continue
        tips.extend((status, path) for path in sorted(directory.glob("*.json")))
    return tips


def _legacy_criteria_changes(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            **{
                key: deepcopy(value)
                for key, value in change.items()
                if key != "id"
            },
        }
        for ordinal, change in enumerate(record.get("criteria_changes", []), start=1)
    ]


def _migrate_record_artifact(
    store: Path,
    project: ProjectSnapshot,
    record: dict[str, Any],
) -> _RecordArtifact:
    request = upgrade_legacy_request(
        request_from_snapshot(record["snapshot"])
    )
    request["decisions"] = _resolve_legacy_active_decisions(
        store,
        project,
        record,
    )
    criteria_changes = _legacy_criteria_changes(record)
    request["criteria_transitions"] = [
        {key: deepcopy(value) for key, value in change.items() if key != "ordinal"}
        for change in criteria_changes
    ]
    validate_request(request)
    artifact = _build_record_artifact(
        request,
        record["metadata"],
        decision_id_high_watermark=_record_decision_high_watermark(record),
        criteria_changes=criteria_changes,
        predecessor_revision=record["lineage"]["predecessor_revision"],
        predecessor_summary=_predecessor_summary_for_record(store, project, record),
        phase_authorization=record["lineage"].get("phase_authorization"),
    )
    validate_no_secrets(artifact.record, label="迁移后的 Relay canonical JSON")
    return artifact


def _changed_migration_writes(
    canonical_path: Path,
    artifact: _RecordArtifact,
) -> tuple[tuple[Path, str], ...]:
    candidates = (
        (canonical_path, artifact.canonical),
        (canonical_path.with_suffix(".md"), artifact.document),
    )
    changed: list[tuple[Path, str]] = []
    for path, content in candidates:
        try:
            current = path.read_bytes()
        except FileNotFoundError:
            current = None
        if current != content.encode("utf-8"):
            changed.append((path, content))
    return tuple(changed)


def _prepare_tip_migrations(
    store: Path,
    project: ProjectSnapshot,
) -> tuple[list[tuple[Path, str]], list[str], int]:
    writes: list[tuple[Path, str]] = []
    migrated_relay_ids: list[str] = []
    inspected_count = 0
    for conversion_index, (tip_status, canonical_path) in enumerate(
        _migration_tip_paths(store, project),
        start=1,
    ):
        relay_id = canonical_path.stem
        try:
            _, record, _ = _validate_record_pair(
                store,
                canonical_path,
                project,
                expected_status=tip_status,
            )
            if "decision_id_high_watermark" not in record:
                artifact = _migrate_record_artifact(store, project, record)
                writes.extend(_changed_migration_writes(canonical_path, artifact))
                migrated_relay_ids.append(relay_id)
            inspected_count += 1
        except Exception as error:
            raise MigrationFailed(
                "Relay tip 迁移预演失败："
                f"{relay_id}（第 {conversion_index} 根）：{error}",
                details={
                    "failed_relay_id": relay_id,
                    "conversion_index": conversion_index,
                    "converted_count": inspected_count,
                },
            ) from error
    return writes, migrated_relay_ids, inspected_count


@_locked_project_operation
def migrate_store(
    store: Path,
    project: ProjectSnapshot,
    *,
    remote: str | None = None,
) -> dict[str, Any]:
    """用一笔 Git 事务迁移当前项目的全部 tip。"""

    validate_store_project_boundary(store, project, remote)
    # 先做一次纯读取预演，让不可读 tip 被准确归因到迁移序号；随后仍要
    # prepare_store，并在它可能 fast-forward 后重新预演，绝不能拿旧
    # HEAD 的产物覆盖刚同步下来的新 tip。
    _prepare_tip_migrations(store, project)
    prepare_store(store, remote)
    writes, migrated_relay_ids, inspected_count = _prepare_tip_migrations(
        store,
        project,
    )

    if not migrated_relay_ids:
        return {
            "project_key": project.key,
            "migrated_count": 0,
            "migrated_relay_ids": [],
            "inspected_count": inspected_count,
            "idempotent": True,
            "synced": remote is not None,
            "commit": _git(store, "rev-parse", "HEAD"),
        }

    plan = _TransactionPlan(
        writes=tuple(writes),
        deletes=(),
        create_paths=(),
        message=f"relay({project.key}): migrate {len(migrated_relay_ids)} tips",
        result={
            "project_key": project.key,
            "migrated_count": len(migrated_relay_ids),
            "migrated_relay_ids": migrated_relay_ids,
            "inspected_count": inspected_count,
            "idempotent": False,
        },
        failure_message="Relay tip 迁移写入失败；已恢复迁移前文件",
    )
    result = _apply_transaction_plan(store, plan, remote=remote)
    result["commit"] = _git(store, "rev-parse", "HEAD")
    return result


def _plan_update_transaction(
    store: Path,
    project: ProjectSnapshot,
    operation: ValidatedOperation,
    target: _StoredTransactionTarget | None,
    client: str | None,
    model: str | None,
) -> _TransactionPlan:
    if not isinstance(operation, ValidatedUpdate) or target is None:
        raise TypeError("update planner 收到不匹配的 ValidatedOperation")
    assert client is not None and model is not None
    relay_target = operation.target
    assert relay_target is not None
    revision = relay_target.actual_revision + 1
    request, watermark, criteria_changes = _materialize_canonical_request(
        store,
        project,
        deepcopy(operation.updated),
        relay_id=relay_target.relay_id,
        revision=revision,
        previous_record=target.record,
        active_decision_ids=operation.active_decision_ids,
    )
    now = _now()
    metadata = _record_metadata(
        project,
        relay_id=relay_target.relay_id,
        title=request["title"],
        status="active",
        revision=revision,
        created_at=target.metadata["created_at"],
        updated_at=now,
        client=client,
        model=model,
    )
    validate_no_secrets(metadata, label="Relay 生成元数据")
    artifact = _build_record_artifact(
        request,
        metadata,
        decision_id_high_watermark=watermark,
        criteria_changes=criteria_changes,
        predecessor_revision=target.record["lineage"]["predecessor_revision"],
        predecessor_summary=_predecessor_summary_for_record(
            store,
            project,
            target.record,
        ),
        phase_authorization=target.record["lineage"].get("phase_authorization"),
    )
    load_preview = _preflight_active_load(
        store,
        project,
        artifact.record,
        artifact.document,
        document_path=target.document_path,
        canonical_path=target.canonical_path,
        previous_record=target.record,
    )
    return _TransactionPlan(
        writes=(
            (target.canonical_path, artifact.canonical),
            (target.document_path, artifact.document),
        ),
        deletes=(),
        create_paths=(),
        message=(
            f"relay({project.key}): r{revision} {request['title']}"
        ),
        result={
            "relay_id": relay_target.relay_id,
            "phase_id": relay_target.relay_id,
            "revision": revision,
            "project_key": project.key,
            "path": str(target.document_path.resolve()),
            "canonical_path": str(target.canonical_path.resolve()),
            "status": "active",
        },
        failure_message="Relay update 事务写入失败，已恢复原状态",
        load_preview=load_preview,
    )


def _plan_withdraw_transaction(
    store: Path,
    project: ProjectSnapshot,
    operation: ValidatedOperation,
    target: _StoredTransactionTarget | None,
    client: str | None,
    model: str | None,
) -> _TransactionPlan:
    if not isinstance(operation, ValidatedWithdraw) or target is None:
        raise TypeError("withdraw planner 收到不匹配的 ValidatedOperation")
    relay_target = operation.target
    assert relay_target is not None
    revision = relay_target.actual_revision + 1
    request = upgrade_legacy_request(
        request_from_snapshot(target.record["snapshot"])
    )
    active_decisions = _record_active_decisions(store, project, target.record)
    request["decisions"] = active_decisions
    now = _now()
    metadata = _record_metadata(
        project,
        relay_id=relay_target.relay_id,
        title=target.metadata["title"],
        status="withdrawn",
        revision=revision,
        created_at=target.metadata["created_at"],
        updated_at=now,
        client=target.metadata["last_client"],
        model=target.metadata["last_model"],
        status_fields={
            "withdrawn_at": now,
            "withdraw_reason": operation.reason,
        },
    )
    artifact = _build_record_artifact(
        request,
        metadata,
        decision_id_high_watermark=_record_decision_high_watermark(target.record),
        criteria_changes=[],
        predecessor_revision=target.record["lineage"]["predecessor_revision"],
        predecessor_summary=_predecessor_summary_for_record(
            store,
            project,
            target.record,
        ),
        phase_authorization=target.record["lineage"].get("phase_authorization"),
    )
    withdrawn_canonical = (
        store
        / "withdrawn"
        / project.key
        / f"{relay_target.relay_id}.json"
    )
    withdrawn_document = withdrawn_canonical.with_suffix(".md")
    return _TransactionPlan(
        writes=(
            (withdrawn_canonical, artifact.canonical),
            (withdrawn_document, artifact.document),
        ),
        deletes=(target.canonical_path, target.document_path),
        create_paths=(withdrawn_canonical, withdrawn_document),
        message=(
            f"relay({project.key}): withdraw r{revision} "
            f"{target.metadata['title']}"
        ),
        result={
            "relay_id": relay_target.relay_id,
            "phase_id": relay_target.relay_id,
            "revision": revision,
            "project_key": project.key,
            "path": str(withdrawn_document.resolve()),
            "canonical_path": str(withdrawn_canonical.resolve()),
            "status": "withdrawn",
            "reason": operation.reason,
        },
        failure_message="Relay withdraw 事务写入失败，已恢复原状态",
    )


def _plan_done_transaction(
    store: Path,
    project: ProjectSnapshot,
    operation: ValidatedOperation,
    target: _StoredTransactionTarget | None,
    client: str | None,
    model: str | None,
) -> _TransactionPlan:
    if not isinstance(operation, ValidatedDone) or target is None:
        raise TypeError("done planner 收到不匹配的 ValidatedOperation")
    assert client is not None and model is not None
    relay_target = operation.target
    assert relay_target is not None
    revision = relay_target.actual_revision + 1
    request, watermark, criteria_changes = _materialize_canonical_request(
        store,
        project,
        deepcopy(operation.completed),
        relay_id=relay_target.relay_id,
        revision=revision,
        previous_record=target.record,
        active_decision_ids=operation.active_decision_ids,
    )
    now = _now()
    metadata = _record_metadata(
        project,
        relay_id=relay_target.relay_id,
        title=request["title"],
        status="done",
        revision=revision,
        created_at=target.metadata["created_at"],
        updated_at=now,
        client=client,
        model=model,
        status_fields={"done_at": now},
    )
    validate_no_secrets(metadata, label="Relay 生成元数据")
    artifact = _build_record_artifact(
        request,
        metadata,
        decision_id_high_watermark=watermark,
        criteria_changes=criteria_changes,
        predecessor_revision=target.record["lineage"]["predecessor_revision"],
        predecessor_summary=_predecessor_summary_for_record(
            store,
            project,
            target.record,
        ),
        phase_authorization=target.record["lineage"].get("phase_authorization"),
    )
    done_canonical = (
        store / "done" / project.key / f"{relay_target.relay_id}.json"
    )
    done_document = done_canonical.with_suffix(".md")
    return _TransactionPlan(
        writes=(
            (done_canonical, artifact.canonical),
            (done_document, artifact.document),
        ),
        deletes=(target.canonical_path, target.document_path),
        create_paths=(done_canonical, done_document),
        message=(
            f"relay({project.key}): done r{revision} {request['title']}"
        ),
        result={
            "relay_id": relay_target.relay_id,
            "phase_id": relay_target.relay_id,
            "revision": revision,
            "project_key": project.key,
            "path": str(done_document.resolve()),
            "canonical_path": str(done_canonical.resolve()),
            "status": "done",
        },
        failure_message="Relay done 事务写入失败，已恢复原状态",
    )


def _plan_successor_transaction(
    store: Path,
    project: ProjectSnapshot,
    operation: ValidatedOperation,
    target: _StoredTransactionTarget | None,
    client: str | None,
    model: str | None,
) -> _TransactionPlan:
    if not isinstance(operation, ValidatedSuccessor) or target is None:
        raise TypeError("successor planner 收到不匹配的 ValidatedOperation")
    assert client is not None and model is not None
    relay_target = operation.target
    assert relay_target is not None
    predecessor_id = relay_target.relay_id
    predecessor_revision = relay_target.actual_revision
    previous_active = _record_active_decisions(store, project, target.record)
    previous_watermark = _record_decision_high_watermark(target.record)
    completion_revision = (
        predecessor_revision + 1
        if operation.current_status == "active"
        else predecessor_revision
    )
    completion, completion_watermark, completion_criteria_changes = _canonicalize_request(
        deepcopy(operation.completion),
        relay_id=predecessor_id,
        revision=completion_revision,
        previous_active_decisions=previous_active,
        decision_id_high_watermark=previous_watermark,
        active_decision_ids=operation.completion_active_decision_ids,
    )
    successor_id = _relay_id()
    successor, successor_watermark, successor_criteria_changes = _canonicalize_request(
        deepcopy(operation.successor),
        relay_id=successor_id,
        revision=1,
        previous_active_decisions=completion["decisions"],
        decision_id_high_watermark=completion_watermark,
        active_decision_ids=operation.successor_active_decision_ids,
    )
    now = _now()
    writes: list[tuple[Path, str]] = []
    deletes: list[Path] = []
    create_paths: list[Path] = []
    if operation.current_status == "active":
        done_metadata = _record_metadata(
            project,
            relay_id=predecessor_id,
            title=completion["title"],
            status="done",
            revision=completion_revision,
            created_at=target.metadata["created_at"],
            updated_at=now,
            client=client,
            model=model,
            status_fields={"done_at": now},
        )
        validate_no_secrets(done_metadata, label="Relay 生成元数据")
        done_artifact = _build_record_artifact(
            completion,
            done_metadata,
            decision_id_high_watermark=completion_watermark,
            criteria_changes=completion_criteria_changes,
            predecessor_revision=target.record["lineage"]["predecessor_revision"],
            predecessor_summary=_predecessor_summary_for_record(
                store,
                project,
                target.record,
            ),
            phase_authorization=target.record["lineage"].get(
                "phase_authorization"
            ),
        )
        done_record = done_artifact.record
        predecessor_summary = _completion_summary(done_record)
        done_canonical = (
            store / "done" / project.key / f"{predecessor_id}.json"
        )
        done_document = done_canonical.with_suffix(".md")
        writes.extend(
            (
                (done_canonical, done_artifact.canonical),
                (done_document, done_artifact.document),
            )
        )
        deletes.extend((target.canonical_path, target.document_path))
        create_paths.extend((done_canonical, done_document))
    else:
        predecessor_summary = _completion_summary(target.record)

    successor_metadata = _record_metadata(
        project,
        relay_id=successor_id,
        title=successor["title"],
        status="active",
        revision=1,
        created_at=now,
        updated_at=now,
        client=client,
        model=model,
    )
    validate_no_secrets(successor_metadata, label="Relay 生成元数据")
    successor_artifact = _build_record_artifact(
        successor,
        successor_metadata,
        decision_id_high_watermark=successor_watermark,
        criteria_changes=successor_criteria_changes,
        predecessor_revision=completion_revision,
        predecessor_summary=predecessor_summary,
        phase_authorization=operation.authorization,
    )
    successor_record = successor_artifact.record
    successor_canonical = (
        store / "active" / project.key / f"{successor_id}.json"
    )
    successor_document = successor_canonical.with_suffix(".md")
    writes.extend(
        (
            (successor_canonical, successor_artifact.canonical),
            (successor_document, successor_artifact.document),
        )
    )
    create_paths.extend((successor_canonical, successor_document))
    load_preview = _preflight_active_load(
        store,
        project,
        successor_record,
        successor_artifact.document,
        document_path=successor_document,
        canonical_path=successor_canonical,
        previous_record=None,
    )
    result = {
        "relay_id": successor_id,
        "phase_id": successor_id,
        "revision": 1,
        "project_key": project.key,
        "path": str(successor_document.resolve()),
        "canonical_path": str(successor_canonical.resolve()),
        "status": "active",
    }
    if operation.current_status == "active":
        done_canonical = store / "done" / project.key / f"{predecessor_id}.json"
        result["predecessor"] = {
            "relay_id": predecessor_id,
            "phase_id": predecessor_id,
            "revision": completion_revision,
            "status": "done",
            "path": str(done_canonical.with_suffix(".md").resolve()),
            "canonical_path": str(done_canonical.resolve()),
        }
        message = (
            f"relay({project.key}): done {predecessor_id} "
            f"r{completion_revision}; successor {successor_id} r1"
        )
    else:
        message = f"relay({project.key}): r1 {successor['title']}"
    return _TransactionPlan(
        writes=tuple(writes),
        deletes=tuple(deletes),
        create_paths=tuple(create_paths),
        message=message,
        result=result,
        failure_message="Relay successor 事务写入失败，已恢复原状态",
        load_preview=load_preview,
    )


def _plan_create_transaction(
    store: Path,
    project: ProjectSnapshot,
    operation: ValidatedOperation,
    target: _StoredTransactionTarget | None,
    client: str | None,
    model: str | None,
) -> _TransactionPlan:
    if not isinstance(operation, ValidatedCreate) or target is not None:
        raise TypeError("create planner 收到不匹配的 ValidatedOperation")
    assert client is not None and model is not None
    relay_id = _relay_id()
    request, watermark, criteria_changes = _materialize_canonical_request(
        store,
        project,
        deepcopy(operation.snapshot),
        relay_id=relay_id,
        revision=1,
        previous_record=None,
        active_decision_ids=operation.active_decision_ids,
    )
    now = _now()
    document_relative = Path("active") / project.key / f"{relay_id}.md"
    canonical_relative = Path("active") / project.key / f"{relay_id}.json"
    document_path = store / document_relative
    canonical_path = store / canonical_relative
    metadata = _record_metadata(
        project,
        relay_id=relay_id,
        title=request["title"],
        status="active",
        revision=1,
        created_at=now,
        updated_at=now,
        client=client,
        model=model,
    )
    validate_no_secrets(metadata, label="Relay 生成元数据")
    artifact = _build_record_artifact(
        request,
        metadata,
        decision_id_high_watermark=watermark,
        criteria_changes=criteria_changes,
        predecessor_revision=None,
        predecessor_summary=None,
        phase_authorization=None,
    )
    load_preview = _preflight_active_load(
        store,
        project,
        artifact.record,
        artifact.document,
        document_path=document_path,
        canonical_path=canonical_path,
        previous_record=None,
    )
    return _TransactionPlan(
        writes=(
            (canonical_path, artifact.canonical),
            (document_path, artifact.document),
        ),
        deletes=(),
        create_paths=(canonical_path, document_path),
        message=f"relay({project.key}): r1 {request['title']}",
        result={
            "relay_id": relay_id,
            "phase_id": relay_id,
            "revision": 1,
            "project_key": project.key,
            "path": str(document_path.resolve()),
            "canonical_path": str(canonical_path.resolve()),
            "status": "active",
        },
        failure_message="Relay create 事务写入失败，已恢复原状态",
        load_preview=load_preview,
    )


def _plan_operation(
    store: Path,
    project: ProjectSnapshot,
    operation: ValidatedOperation,
    *,
    client: str | None,
    model: str | None,
) -> _TransactionPlan:
    target = _load_transaction_target(store, project, operation)
    if isinstance(operation, ValidatedCreate):
        planner = _plan_create_transaction
    elif isinstance(operation, ValidatedUpdate):
        planner = _plan_update_transaction
    elif isinstance(operation, ValidatedDone):
        planner = _plan_done_transaction
    elif isinstance(operation, ValidatedSuccessor):
        planner = _plan_successor_transaction
    elif isinstance(operation, ValidatedWithdraw):
        planner = _plan_withdraw_transaction
    else:  # pragma: no cover - sealed by assert_validated_operation
        raise TypeError(f"未知 ValidatedOperation：{type(operation).__name__}")
    return planner(store, project, operation, target, client, model)


@_locked_project_operation
def list_relays(
    store: Path, project: ProjectSnapshot, *, remote: str | None = None
) -> list[dict[str, Any]]:
    validate_store_project_boundary(store, project, remote)
    prepare_store(store, remote)
    active = store / "active" / project.key
    _reject_symlink_path(store, active)
    if not active.is_dir():
        return []
    commit_order = {
        commit: index
        for index, commit in enumerate(
            _git(store, "log", "--format=%H").splitlines()
        )
    }
    items: list[dict[str, Any]] = []
    for canonical_path in sorted(active.glob("*.json")):
        _, record, metadata = _validate_record_pair(
            store, canonical_path, project, expected_status="active"
        )
        document_path = canonical_path.with_suffix(".md")
        relative = canonical_path.relative_to(store).as_posix()
        commit = _git(store, "log", "-1", "--format=%H", "--", relative)
        items.append(
            {
                "relay_id": metadata.get("relay_id"),
                "phase_id": record["snapshot"]["phase"].get(
                    "phase_id", metadata["relay_id"]
                ),
                "revision": metadata.get("revision"),
                "title": metadata.get("title", canonical_path.stem),
                "phase": record["snapshot"]["phase"]["name"],
                "phase_outcome": record["snapshot"]["phase"]["outcome"],
                "updated_at": metadata.get("updated_at"),
                "last_client": metadata.get("last_client"),
                "last_model": metadata.get("last_model"),
                "commit": commit,
                "committed_at": _git(
                    store, "log", "-1", "--format=%cI", "--", relative
                ),
                "path": str(document_path.resolve()),
                "canonical_path": str(canonical_path.resolve()),
                "_commit_order": commit_order.get(commit, len(commit_order)),
            }
        )
    items.sort(key=lambda item: (item["_commit_order"], item["relay_id"]))
    for item in items:
        item.pop("_commit_order", None)
    return items


@_locked_project_operation
def history_relays(
    store: Path,
    project: ProjectSnapshot,
    *,
    remote: str | None = None,
) -> dict[str, Any]:
    validate_store_project_boundary(store, project, remote)
    prepare_store(store, remote)
    done = store / "done" / project.key
    _reject_symlink_path(store, done)
    if not done.is_dir():
        result = {
            "project_key": project.key,
            "items": [],
            "max_load_bytes": MAX_LOAD_BYTES,
            "history_bytes": 0,
        }
        _settle_result_bytes(result, "history_bytes")
        return result

    commit_order = {
        commit: index
        for index, commit in enumerate(
            _git(store, "log", "--format=%H").splitlines()
        )
    }
    items: list[dict[str, Any]] = []
    for canonical_path in sorted(done.glob("*.json")):
        _, record, metadata = _validate_record_pair(
            store, canonical_path, project, expected_status="done"
        )
        relative = canonical_path.relative_to(store).as_posix()
        commit = _git(store, "log", "-1", "--format=%H", "--", relative)
        committed_at = _git(store, "log", "-1", "--format=%cI", "--", relative)
        phase = record["snapshot"]["phase"]
        items.append(
            {
                "relay_id": metadata["relay_id"],
                "phase_id": phase.get("phase_id", metadata["relay_id"]),
                "revision": metadata["revision"],
                "title": metadata["title"],
                "phase": phase["name"],
                "phase_outcome": phase["outcome"],
                "phase_done_when_count": len(phase["done_when"]),
                "predecessor_relay_id": record["lineage"][
                    "predecessor_relay_id"
                ],
                "done_at": metadata["done_at"],
                "commit": commit,
                "committed_at": committed_at,
                "_commit_order": commit_order.get(commit, len(commit_order)),
            }
        )
    items.sort(key=lambda item: (item["_commit_order"], item["relay_id"]))
    for item in items:
        item.pop("_commit_order", None)
    result = {
        "project_key": project.key,
        "items": items,
        "max_load_bytes": MAX_LOAD_BYTES,
        "history_bytes": 0,
    }
    _settle_result_bytes(result, "history_bytes")
    if result["history_bytes"] > MAX_LOAD_BYTES:
        raise LoadTooLarge(
            "Relay history 超过总输出硬上限",
            details={
                "history_bytes": result["history_bytes"],
                "max_load_bytes": MAX_LOAD_BYTES,
            },
        )
    return result


@_locked_project_operation
def recall_decision(
    store: Path,
    project: ProjectSnapshot,
    *,
    relay_id: str,
    revision: int,
    decision_id: str,
    remote: str | None = None,
) -> dict[str, Any]:
    validate_relay_id(relay_id)
    _validate_expected_revision(revision)
    if not re.fullmatch(r"D-[0-9]{3}", decision_id):
        raise InvalidRequest("decision id 必须匹配 D-000")
    validate_store_project_boundary(store, project, remote)
    prepare_store(store, remote)
    record = _record_at_revision(
        store,
        project,
        relay_id=relay_id,
        revision=revision,
    )
    decision = next(
        (
            item
            for item in record["snapshot"]["decisions"]
            if item["id"] == decision_id
        ),
        None,
    )
    if decision is None:
        raise RelayNotFound(
            f"Relay {relay_id} r{revision} 不包含详细决策 {decision_id}"
        )
    result: dict[str, Any] = {
        "relay_id": relay_id,
        "revision": revision,
        "decision_id": decision_id,
        "decision": decision,
        "max_load_bytes": MAX_LOAD_BYTES,
        "recall_bytes": 0,
    }
    _settle_result_bytes(result, "recall_bytes")
    if result["recall_bytes"] > MAX_LOAD_BYTES:
        raise LoadTooLarge(
            "Relay decision 超过总输出硬上限",
            details={
                "recall_bytes": result["recall_bytes"],
                "max_load_bytes": MAX_LOAD_BYTES,
            },
        )
    return result


@_locked_project_operation
def recall_criteria_change(
    store: Path,
    project: ProjectSnapshot,
    *,
    relay_id: str,
    revision: int,
    criteria_id: str | None = None,
    criteria_ordinal: int | None = None,
    remote: str | None = None,
) -> dict[str, Any]:
    validate_relay_id(relay_id)
    _validate_expected_revision(revision)
    if (criteria_id is None) == (criteria_ordinal is None):
        raise InvalidRequest("criteria_id 与 criteria_ordinal 必须且只能提供一个")
    if criteria_id is not None and not re.fullmatch(r"C-[0-9]{3}", criteria_id):
        raise InvalidRequest("criteria id 必须匹配 C-000")
    if criteria_ordinal is not None and criteria_ordinal < 1:
        raise InvalidRequest("criteria ordinal 必须是正整数")
    validate_store_project_boundary(store, project, remote)
    prepare_store(store, remote)
    record = _record_at_revision(
        store,
        project,
        relay_id=relay_id,
        revision=revision,
    )
    changes = record.get("criteria_changes", [])
    if criteria_ordinal is not None:
        criteria_change = next(
            (item for item in changes if item.get("ordinal") == criteria_ordinal),
            None,
        )
    else:
        criteria_change = next(
            (item for item in changes if item.get("id") == criteria_id),
            None,
        )
    if criteria_change is None:
        raise RelayNotFound(
            f"Relay {relay_id} r{revision} 不包含指定判据变更"
        )
    result: dict[str, Any] = {
        "relay_id": relay_id,
        "revision": revision,
        "criteria_id": criteria_id,
        "criteria_ordinal": criteria_ordinal,
        "criteria_change": criteria_change,
        "max_load_bytes": MAX_LOAD_BYTES,
        "recall_bytes": 0,
    }
    _settle_result_bytes(result, "recall_bytes")
    if result["recall_bytes"] > MAX_LOAD_BYTES:
        raise LoadTooLarge(
            "Relay criteria change 超过总输出硬上限",
            details={
                "recall_bytes": result["recall_bytes"],
                "max_load_bytes": MAX_LOAD_BYTES,
            },
        )
    return result


def _resolve_legacy_active_decisions(
    store: Path,
    project: ProjectSnapshot,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    metadata = record["metadata"]
    resolved: list[dict[str, Any]] = []
    for pointer in record["decision_registry"]["active"]:
        source_key = (
            pointer["source_relay_id"],
            pointer["source_revision"],
        )
        if source_key == (metadata["relay_id"], metadata["revision"]):
            source = record
        else:
            source = _record_at_revision(
                store,
                project,
                relay_id=source_key[0],
                revision=source_key[1],
            )
        decision = next(
            (
                item
                for item in source["snapshot"]["decisions"]
                if item["id"] == pointer["id"]
            ),
            None,
        )
        if decision is None:
            raise StoreError(
                f"活动决策指针无法解析完整内容：{pointer['id']} "
                f"@ {source_key[0]} r{source_key[1]}"
            )
        if (
            decision["status"] != pointer["status"]
            or decision["label"] != pointer["label"]
        ):
            raise StoreError(
                f"活动决策全文与当前指针不一致：{pointer['id']}"
            )
        resolved.append(deepcopy(decision))
    return resolved


def _build_load_result(
    store: Path,
    project: ProjectSnapshot,
    *,
    selected: dict[str, Any],
    document: str,
    document_export: dict[str, Any],
    record: dict[str, Any],
    metadata: dict[str, Any],
    previous_record: dict[str, Any] | None,
) -> dict[str, Any]:
    source_relation = "exact"
    if metadata["source_head"] != project.head:
        source_relation = "changed"
    elif metadata["source_dirty"] or project.dirty:
        source_relation = "dirty_unverifiable"
    delta = build_structured_delta(previous_record, record)
    active_decisions = _record_active_decisions(store, project, record)
    predecessor_summary = _predecessor_summary_for_record(
        store,
        project,
        record,
    )
    phase_completion = _phase_completion_for_record(record)
    completion_status_warnings: list[dict[str, str]] = []
    if phase_completion["source"] == "legacy_missing":
        completion_status_warnings.append(
            {
                "code": "legacy_phase_completion_unknown",
                "message": LEGACY_COMPLETION_STATUS_REASON,
            }
        )
    result = {
        **selected,
        "phase_id": record["snapshot"]["phase"].get(
            "phase_id", metadata["relay_id"]
        ),
        "expected_revision": selected["revision"],
        "project_key": project.key,
        "project_remote": project.remote,
        "source_head": metadata.get("source_head"),
        "source_branch": metadata.get("source_branch"),
        "source_dirty": metadata.get("source_dirty"),
        "current_source": {
            "head": project.head,
            "branch": project.branch,
            "dirty": project.dirty,
        },
        "source_relation": source_relation,
        "delta": delta,
        "delta_bytes": len(
            json.dumps(
                delta,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ),
        "predecessor_summary": predecessor_summary,
        "phase_completion": phase_completion,
        "completion_status_warnings": completion_status_warnings,
        "active_decisions": active_decisions,
        "active_decision_count": len(active_decisions),
        "active_decisions_complete": True,
        "requires_confirmation": True,
        "confirmation_fields": [
            "task_outcome",
            "phase_outcome",
            "predecessor_summary",
            "non_goals",
            "invariants",
            "active_decisions",
            "unknowns",
            "source_relation",
            "first_step",
            "phase_done_when",
            "phase_completion",
        ],
        "document": document,
        "document_export": document_export,
    }
    if source_relation == "dirty_unverifiable":
        result["source_verification"] = {
            "required": True,
            "reason": (
                "记录与当前工作树至少一侧含未提交内容，Git commit 无法证明交付一致"
            ),
            "checklist": [
                {
                    "id": "status",
                    "action": "核对 git status，确认所有未提交与未跟踪文件的归属。",
                },
                {
                    "id": "diff",
                    "action": "阅读 staged、unstaged 与未跟踪内容，不得只看 HEAD。",
                },
                {
                    "id": "paths",
                    "action": "逐项核对 Relay references、read、modify 指向的实际文件。",
                },
                {
                    "id": "tests",
                    "action": "按 Relay evidence 复跑关键验证，不能沿用“应该通过”。",
                },
            ],
        }
    result["max_load_bytes"] = MAX_LOAD_BYTES
    result["soft_load_bytes"] = SOFT_LOAD_BYTES
    settle_load_response(result)
    if result["load_bytes"] > MAX_LOAD_BYTES:
        raise LoadTooLarge(
            f"Relay load 响应超过 {MAX_LOAD_BYTES} bytes：{result['load_bytes']}",
            details={
                "load_bytes": result["load_bytes"],
                "max_load_bytes": MAX_LOAD_BYTES,
                "document_bytes": len(document.encode("utf-8")),
                "active_decision_count": len(active_decisions),
            },
        )
    return result


def _preflight_active_load(
    store: Path,
    project: ProjectSnapshot,
    record: dict[str, Any],
    document: str,
    *,
    document_path: Path,
    canonical_path: Path,
    previous_record: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata = record["metadata"]
    phase = record["snapshot"]["phase"]
    selected = {
        "relay_id": metadata["relay_id"],
        "phase_id": phase.get("phase_id", metadata["relay_id"]),
        "revision": metadata["revision"],
        "title": metadata["title"],
        "phase": phase["name"],
        "phase_outcome": phase["outcome"],
        "updated_at": metadata["updated_at"],
        "last_client": metadata["last_client"],
        "last_model": metadata["last_model"],
        "commit": "0" * 64,
        "committed_at": metadata["updated_at"],
        "path": str(document_path.resolve()),
        "canonical_path": str(canonical_path.resolve()),
    }
    return _build_load_result(
        store,
        project,
        selected=selected,
        document=document,
        document_export=_current_document_export(),
        record=record,
        metadata=metadata,
        previous_record=previous_record,
    )


@_locked_project_operation
def load_relay(
    store: Path,
    project: ProjectSnapshot,
    *,
    relay_id: str | None = None,
    remote: str | None = None,
) -> dict[str, Any]:
    if relay_id is not None:
        validate_relay_id(relay_id)
    validate_store_project_boundary(store, project, remote)
    items = list_relays(store, project, remote=remote)
    selected: dict[str, Any] | None
    if relay_id is None:
        if not items:
            raise RelayNotFound(f"当前项目没有活动 Relay：{project.key}")
        if len(items) > 1:
            raise SelectionRequired(
                "当前项目有多个活动 Relay；请从 relay list 的编号中选择"
            )
        selected = items[0]
    else:
        selected = None
        for item in items:
            if item["relay_id"] == relay_id:
                selected = item
                break
        if selected is None:
            raise RelayNotFound(f"找不到当前项目的活动 Relay：{relay_id}")
    canonical_path = Path(str(selected["canonical_path"]))
    document, record, metadata = _validate_record_pair(
        store, canonical_path, project, expected_status="active"
    )
    document_export = _inspect_document_export(
        canonical_path.with_suffix(".md"),
        document,
    )
    previous_record = _previous_record_for_path(store, canonical_path)
    return _build_load_result(
        store,
        project,
        selected=selected,
        document=document,
        document_export=document_export,
        record=record,
        metadata=metadata,
        previous_record=previous_record,
    )

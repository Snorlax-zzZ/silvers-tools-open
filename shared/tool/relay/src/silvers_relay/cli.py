from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Sequence
from urllib.parse import urlsplit

from . import __version__
from .constants import MAX_REQUEST_BYTES
from .drafts import cleanup_request_draft, create_request_draft
from .errors import (
    InvalidRequest,
    InternalError,
    NotConfigured,
    NotGitProject,
    RelayError,
    RequestTooLarge,
    SchemaUnsupported,
)
from .installation import assess_installation, installation_warnings
from .project import (
    inspect_project,
    inspect_project_identity,
    normalize_remote,
    stabilize_remote,
)
from .protocol import operation_command
from .store import (
    apply_operation,
    history_relays,
    list_relays,
    load_relay,
    migrate_store,
    operation_context,
    prepare_store,
    preview_operation,
    recall_criteria_change,
    recall_decision,
    validate_store_project_boundary,
)
from .runtime import default_relay_home


CONFIG_SCHEMA = 1


class RelayArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InvalidRequest(f"命令参数非法：{message}")


def _parser() -> argparse.ArgumentParser:
    parser = RelayArgumentParser(
        prog="relay", description="确定性的跨模型任务接力工具"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument("--home", type=Path, default=default_relay_home())
    parser.add_argument("--store", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--remote", dest="remote_override", help="覆盖独立 Relay Git 远端"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    setup_parser = commands.add_parser("setup", help="一次性配置独立 Relay store")
    setup_parser.add_argument("--remote", dest="setup_remote", required=True)
    commands.add_parser("status", help="查看 Relay 配置和 store 状态")
    draft_parser = commands.add_parser("draft", help="创建或清理安全请求草稿")
    draft_commands = draft_parser.add_subparsers(dest="draft_command", required=True)
    draft_create_parser = draft_commands.add_parser(
        "create", help="创建唯一的结构化请求草稿"
    )
    draft_create_parser.add_argument(
        "--operation",
        choices=("create", "update", "successor", "done", "withdraw"),
        required=True,
    )
    draft_create_parser.add_argument("--relay-id")
    cleanup_parser = draft_commands.add_parser("cleanup", help="清理 Relay 请求草稿")
    cleanup_parser.add_argument("--path", type=Path, required=True)
    validate_parser = commands.add_parser("validate", help="只读验证一份 Relay 请求")
    validate_parser.add_argument("--request", type=Path, required=True)
    pass_parser = commands.add_parser("pass", help="创建或更新当前真相快照")
    pass_parser.add_argument("--request", type=Path, required=True)
    pass_parser.add_argument("--client", required=True)
    pass_parser.add_argument("--model", required=True)
    successor_parser = commands.add_parser(
        "successor",
        help="原子完成旧阶段并创建 successor",
    )
    successor_parser.add_argument("--request", type=Path, required=True)
    successor_parser.add_argument("--client", required=True)
    successor_parser.add_argument("--model", required=True)
    commands.add_parser("list", help="列出当前项目的活动 Relay")
    commands.add_parser("history", help="列出全部已完成阶段大纲")
    commands.add_parser("migrate", help="原子迁移当前项目的全部 Relay tip")
    recall_parser = commands.add_parser(
        "recall", help="读取一个历史决策或判据变更"
    )
    recall_parser.add_argument("--relay-id", required=True)
    recall_parser.add_argument("--revision", required=True, type=int)
    recall_target = recall_parser.add_mutually_exclusive_group(required=True)
    recall_target.add_argument("--decision-id")
    recall_target.add_argument("--criteria-id")
    recall_target.add_argument("--criteria-ordinal", type=int)
    load_parser = commands.add_parser("load", help="加载一份当前真相快照")
    load_parser.add_argument("--relay-id")
    done_parser = commands.add_parser("done", help="验证完成并归档 Relay")
    done_parser.add_argument("--request", type=Path, required=True)
    done_parser.add_argument("--client", required=True)
    done_parser.add_argument("--model", required=True)
    withdraw_parser = commands.add_parser(
        "withdraw", help="撤销错误创建的活动 Relay"
    )
    withdraw_parser.add_argument("--request", type=Path, required=True)
    return parser


def _config_path(home: Path) -> Path:
    return home / "config.json"


def _read_config(home: Path) -> dict[str, Any] | None:
    path = _config_path(home)
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        raw_config: Any = json.load(handle)
    if not isinstance(raw_config, dict):
        raise InvalidRequest(f"Relay 配置必须是 JSON object：{path}")
    config: dict[str, Any] = raw_config
    config_schema = config.get("config_schema")
    if type(config_schema) is int and config_schema != CONFIG_SCHEMA:
        raise SchemaUnsupported(
            component="relay_config",
            cli_version=__version__,
            supported_schema=CONFIG_SCHEMA,
            encountered_schema=config_schema,
        )
    if config_schema != CONFIG_SCHEMA or set(config) != {"config_schema", "remote"}:
        raise InvalidRequest(f"Relay 配置格式非法：{path}")
    if config["remote"] is not None and not isinstance(config["remote"], str):
        raise InvalidRequest(f"Relay remote 必须是 string 或 null：{path}")
    return config


def _write_config(home: Path, remote: str) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    target = _config_path(home)
    fd, temporary_name = tempfile.mkstemp(prefix=".config.", dir=home)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {"config_schema": CONFIG_SCHEMA, "remote": remote},
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return target


def _load_request(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise InvalidRequest("Relay 请求必须是普通 JSON 文件")
        raw = handle.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise RequestTooLarge(
            f"请求文件超过 {MAX_REQUEST_BYTES} bytes：至少 {len(raw)}",
            details={
                "request_bytes": len(raw),
                "max_request_bytes": MAX_REQUEST_BYTES,
            },
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise InvalidRequest("Relay 请求必须是 UTF-8 JSON 文件") from error
    if not isinstance(payload, dict):
        raise InvalidRequest("Relay 请求必须是 JSON object")
    return payload


def _validate_remote_input(remote: str | None) -> None:
    if remote is None:
        return
    if not remote.strip():
        raise InvalidRequest("Relay remote 不能为空")
    parsed = urlsplit(remote)
    if (
        bool(parsed.query)
        or bool(parsed.fragment)
        or (
            parsed.scheme
            and (parsed.username is not None or parsed.password is not None)
        )
    ):
        raise InvalidRequest(
            "Relay remote URL 不得内嵌用户凭据、query 或 fragment；请使用 credential helper 或 SSH"
        )


def _safe_remote_display(remote: str | None) -> str | None:
    if remote is None:
        return None
    without_suffix = remote.split("#", 1)[0].split("?", 1)[0]
    return normalize_remote(without_suffix, base=Path.cwd())


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        home = args.home.expanduser().resolve()
        store = (args.store or (home / "store")).expanduser().resolve()
        config = _read_config(home)
        configured_remote = config["remote"] if config else None
        remote = args.remote_override or configured_remote
        _validate_remote_input(remote)
        if remote is not None:
            remote = stabilize_remote(remote, base=Path.cwd())
        if args.command == "status":
            installation = assess_installation(home, args.repo.resolve())
            if installation is None:
                installation: dict[str, Any] = {"recorded": False}
            result = {
                "configured": remote is not None,
                "config_present": config is not None,
                "home": str(home),
                "store": str(store),
                "store_exists": (store / ".git").is_dir(),
                "remote": _safe_remote_display(remote),
                "installation": installation,
            }
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
            return 0
        if args.command == "setup":
            remote = args.setup_remote
            _validate_remote_input(remote)
            remote = stabilize_remote(remote, base=Path.cwd())
            try:
                setup_project = inspect_project_identity(args.repo.resolve())
            except NotGitProject:
                setup_project = None
            if setup_project is not None:
                validate_store_project_boundary(home, setup_project, None)
                validate_store_project_boundary(store, setup_project, remote)
            prepare_store(store, remote)
            config_path = _write_config(home, remote)
            result = {
                "configured": True,
                "config": str(config_path),
                "store": str(store),
                "remote": _safe_remote_display(remote),
            }
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
            return 0
        if args.command == "draft" and args.draft_command == "cleanup":
            result = cleanup_request_draft(home, args.path)
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
            return 0
        if args.command == "draft" and args.draft_command == "create":
            if remote is None:
                raise NotConfigured(
                    "Relay 尚未配置独立 remote；请先由安装流程执行 relay setup --remote ..."
                )
            project = inspect_project(args.repo.resolve())
            context = operation_context(
                store,
                project,
                operation=args.operation,
                relay_id=args.relay_id,
                remote=remote,
            )
            result = create_request_draft(
                home,
                operation=args.operation,
                context=context,
            )
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
            return 0
        project = inspect_project(args.repo.resolve())
        if args.command == "validate":
            result = preview_operation(
                store,
                project,
                _load_request(args.request),
                remote=remote,
            )
        else:
            if remote is None:
                raise NotConfigured(
                    "Relay 尚未配置独立 remote；请先由安装流程执行 relay setup --remote ..."
                )
            if args.command == "pass":
                request = _load_request(args.request)
                if operation_command(request.get("operation")) != "pass":
                    raise InvalidRequest("pass 与 request.operation 不匹配")
                result = apply_operation(
                    store,
                    project,
                    request,
                    client=args.client,
                    model=args.model,
                    remote=remote,
                )
            elif args.command == "successor":
                warnings = installation_warnings(home, args.repo.resolve())
                request = _load_request(args.request)
                if operation_command(request.get("operation")) != "successor":
                    raise InvalidRequest("successor 与 request.operation 不匹配")
                result = apply_operation(
                    store,
                    project,
                    request,
                    client=args.client,
                    model=args.model,
                    remote=remote,
                )
                if warnings:
                    result["warnings"] = warnings
            elif args.command == "list":
                result = {
                    "project_key": project.key,
                    "items": list_relays(store, project, remote=remote),
                }
            elif args.command == "history":
                result = history_relays(
                    store,
                    project,
                    remote=remote,
                )
            elif args.command == "migrate":
                result = migrate_store(store, project, remote=remote)
            elif args.command == "recall":
                if args.decision_id is not None:
                    result = recall_decision(
                        store,
                        project,
                        relay_id=args.relay_id,
                        revision=args.revision,
                        decision_id=args.decision_id,
                        remote=remote,
                    )
                else:
                    result = recall_criteria_change(
                        store,
                        project,
                        relay_id=args.relay_id,
                        revision=args.revision,
                        criteria_id=args.criteria_id,
                        criteria_ordinal=args.criteria_ordinal,
                        remote=remote,
                    )
            elif args.command == "load":
                result = load_relay(
                    store, project, relay_id=args.relay_id, remote=remote
                )
                warnings = installation_warnings(home, args.repo.resolve())
                if warnings:
                    result["warnings"] = warnings
            elif args.command == "done":
                warnings = installation_warnings(home, args.repo.resolve())
                request = _load_request(args.request)
                if operation_command(request.get("operation")) != "done":
                    raise InvalidRequest("done 与 request.operation 不匹配")
                result = apply_operation(
                    store,
                    project,
                    request,
                    client=args.client,
                    model=args.model,
                    remote=remote,
                )
                if warnings:
                    result["warnings"] = warnings
            elif args.command == "withdraw":
                request = _load_request(args.request)
                if operation_command(request.get("operation")) != "withdraw":
                    raise InvalidRequest("withdraw 与 request.operation 不匹配")
                result = apply_operation(
                    store,
                    project,
                    request,
                    client=None,
                    model=None,
                    remote=remote,
                )
            else:
                parser.error(f"unsupported command: {args.command}")
                return 2
    except (RelayError, OSError, ValueError, json.JSONDecodeError) as error:
        code = error.code if isinstance(error, RelayError) else "invalid_input"
        payload: dict[str, Any] = {"code": code, "message": str(error)}
        if isinstance(error, RelayError) and error.details:
            payload["details"] = error.details
        print(
            json.dumps({"ok": False, "error": payload}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    except Exception as error:  # pragma: no cover - guarded by CLI contract tests
        internal = InternalError(
            "Relay 遇到未处理的内部错误；请保留请求与错误现场后报告",
            details={"exception_type": type(error).__name__},
        )
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": internal.code,
                        "message": str(internal),
                        "details": internal.details,
                    },
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0

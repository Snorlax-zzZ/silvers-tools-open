#!/usr/bin/env python3
"""稳定的 Relay runtime 指针启动器；本文件不得加入业务逻辑。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any


CURRENT_SCHEMA = 1
MAX_CURRENT_BYTES = 4096
LAUNCH_ERROR_EXIT = 127


class LauncherError(Exception):
    pass


def _default_relay_home(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    user_home: Path | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    override = environment.get("SILVERS_RELAY_HOME", "").strip()
    if override:
        return Path(override).expanduser()

    current_platform = sys.platform if platform is None else platform
    home = Path.home() if user_home is None else user_home
    if current_platform == "win32":
        local_app_data = environment.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
        return base / "Silvers" / "Relay"
    return home / ".silvers" / "relay"


def _read_pointer(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise LauncherError(f"current.json 不允许是符号链接：{path}")
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_CURRENT_BYTES + 1)
    except FileNotFoundError as error:
        raise LauncherError(f"找不到 current.json：{path}") from error
    if len(raw) > MAX_CURRENT_BYTES:
        raise LauncherError(f"current.json 超过 {MAX_CURRENT_BYTES} bytes")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LauncherError(f"current.json 不是合法 UTF-8 JSON：{path}") from error
    if not isinstance(payload, dict):
        raise LauncherError("current.json 必须是 JSON object")
    schema = payload.get("current_schema")
    if type(schema) is not int:
        raise LauncherError("current schema 必须是 integer")
    if schema != CURRENT_SCHEMA:
        raise LauncherError(
            f"current schema {schema} 不受支持；当前 launcher 支持 {CURRENT_SCHEMA}"
        )
    if set(payload) != {"current_schema", "entrypoint"}:
        raise LauncherError("current.json 字段非法")
    return payload


def _resolve_target(home: Path, entrypoint: Any) -> Path:
    if (
        not isinstance(entrypoint, str)
        or not entrypoint
        or "\\" in entrypoint
        or "\n" in entrypoint
        or "\r" in entrypoint
    ):
        raise LauncherError("current entrypoint 必须是非空 POSIX 相对路径")
    pointer = PurePosixPath(entrypoint)
    parts = pointer.parts
    if entrypoint != pointer.as_posix():
        raise LauncherError("current entrypoint 必须使用规范 POSIX 相对路径")
    if (
        pointer.is_absolute()
        or len(parts) < 3
        or parts[0] != "runtimes"
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise LauncherError(
            "current entrypoint 必须是 runtimes/<version>/ 下的安全相对路径"
        )

    resolved_home = home.expanduser().resolve()
    runtimes = resolved_home / "runtimes"
    target = resolved_home.joinpath(*parts)
    current = target
    while current != resolved_home:
        if current.is_symlink():
            raise LauncherError(f"current entrypoint 路径不允许符号链接：{current}")
        current = current.parent
    try:
        resolved_target = target.resolve(strict=True)
    except FileNotFoundError as error:
        raise LauncherError(f"current entrypoint 不存在：{target}") from error
    try:
        resolved_target.relative_to(runtimes)
    except ValueError as error:
        raise LauncherError("current entrypoint 逃逸出 runtimes/") from error
    if not resolved_target.is_file():
        raise LauncherError(f"current entrypoint 不是普通文件：{target}")
    if os.name != "nt" and not os.access(resolved_target, os.X_OK):
        raise LauncherError(f"current entrypoint 不可执行：{target}")
    return resolved_target


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        home = _default_relay_home().expanduser().resolve()
        pointer = _read_pointer(home / "current.json")
        target = _resolve_target(home, pointer["entrypoint"])
        completed = subprocess.run([str(target), *arguments], check=False)
    except (LauncherError, OSError) as error:
        print(f"relay launcher error: {error}", file=sys.stderr)
        return LAUNCH_ERROR_EXIT
    if completed.returncode < 0:
        return 128 + abs(completed.returncode)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

from .errors import InvalidRequest
from .protocol import OperationContext, OperationName, generate_draft


_DRAFT_NAME = re.compile(r"relay-request-[A-Za-z0-9_-]{6,}\.json\Z")


def _work_directory(home: Path, *, create: bool) -> Path:
    work = home / "work"
    try:
        metadata = work.lstat()
    except FileNotFoundError:
        if not create:
            return work
        home.mkdir(parents=True, exist_ok=True)
        try:
            work.mkdir(mode=0o700)
        except FileExistsError:
            # A concurrent draft creator may have won this exact mkdir race.
            pass
        metadata = work.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise InvalidRequest("Relay work 路径必须是非符号链接目录")
    if os.name == "posix":
        work.chmod(0o700)
    return work


def create_request_draft(
    home: Path,
    *,
    operation: OperationName | str,
    context: OperationContext | None,
) -> dict[str, Any]:
    """Create one private, uniquely named request draft owned by Relay."""

    work = _work_directory(home, create=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="relay-request-", suffix=".json", dir=work
    )
    path = Path(temporary_name)
    try:
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            template = generate_draft(operation, context)
            json.dump(template, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise
    return {"path": str(path.resolve())}


def _candidate_name(home: Path, path: Path) -> tuple[Path, str]:
    work = _work_directory(home, create=False)
    work_absolute = Path(os.path.abspath(work))
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    candidate = Path(os.path.abspath(expanded))
    if (
        candidate.parent != work_absolute
        or _DRAFT_NAME.fullmatch(candidate.name) is None
    ):
        raise InvalidRequest("只能清理 Relay work 目录内由 Relay 创建的请求草稿")
    return work_absolute, candidate.name


def cleanup_request_draft(home: Path, path: Path) -> dict[str, Any]:
    """Remove one Relay-owned regular draft without following symbolic links."""

    work, name = _candidate_name(home, path)
    if not work.exists():
        return {"path": str(work / name), "removed": False}

    if os.name == "posix":
        flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        directory = os.open(work, flags)
        try:
            try:
                metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                return {"path": str(work / name), "removed": False}
            if not stat.S_ISREG(metadata.st_mode):
                raise InvalidRequest("Relay 请求草稿必须是普通文件，不能是符号链接")
            os.unlink(name, dir_fd=directory)
        finally:
            os.close(directory)
    else:
        candidate = work / name
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            return {"path": str(candidate), "removed": False}
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise InvalidRequest("Relay 请求草稿必须是普通文件，不能是符号链接")
        candidate.unlink()
    return {"path": str(work / name), "removed": True}

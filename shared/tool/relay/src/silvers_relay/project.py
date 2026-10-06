from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

from .errors import NotGitProject, ProjectError


GIT_REPOSITORY_ENVIRONMENT = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_QUARANTINE_PATH",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
}


@dataclass(frozen=True)
class ProjectIdentity:
    root: Path
    remote: str
    remote_urls: tuple[str, ...]


@dataclass(frozen=True)
class ProjectSnapshot(ProjectIdentity):
    key: str
    head: str
    branch: str
    dirty: bool


def sanitized_git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in GIT_REPOSITORY_ENVIRONMENT:
        environment.pop(name, None)
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def _git(repo: Path, *args: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        env=sanitized_git_environment(),
        text=True,
        capture_output=True,
    )
    if result.returncode and not allow_failure:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ProjectError(f"Git 项目探测失败：{detail}")
    return result.stdout.strip() if result.returncode == 0 else ""


def _strip_repo_suffix(value: str) -> str:
    normalized = value.rstrip("/")
    return normalized[:-4] if normalized.endswith(".git") else normalized


def stabilize_remote(remote: str, *, base: Path) -> str:
    value = remote.strip()
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "file":
            return value
        if parsed.hostname not in {None, "", "localhost"}:
            local_text = f"//{parsed.hostname}{unquote(parsed.path)}"
        else:
            local_text = unquote(parsed.path)
        local = Path(local_text).expanduser()
        if not local.is_absolute():
            local = base / local
        return str(local.resolve())
    if not re.match(r"^[A-Za-z]:[\\/]", value):
        if re.match(r"^(?:[^@/]+@)?([^:/]+):(.+)$", value):
            return value
    local = Path(value).expanduser()
    if not local.is_absolute():
        local = base / local
    return str(local.resolve())


def normalize_remote(remote: str, *, base: Path | None = None) -> str:
    value = remote.strip()
    if not value:
        return "none"
    if "://" in value:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme == "file":
            if parsed.hostname not in {None, "", "localhost"}:
                local_text = f"//{parsed.hostname}{unquote(parsed.path)}"
            else:
                local_text = unquote(parsed.path)
            local = Path(local_text).expanduser()
            if not local.is_absolute():
                local = (base or Path.cwd()) / local
            return _strip_repo_suffix(os.path.normcase(str(local.resolve())))
        host = (parsed.hostname or "").lower()
        try:
            port = parsed.port
        except ValueError:
            port = None
        default_ports = {"http": 80, "https": 443, "ssh": 22, "git": 9418}
        authority = host
        if port is not None and port != default_ports.get(scheme):
            authority = f"{authority}:{port}"
        path = _strip_repo_suffix(unquote(parsed.path))
        if scheme == "ssh":
            return f"ssh://{authority}/{path.lstrip('/')}"
        return f"{scheme}://{authority}{path}"
    if not re.match(r"^[A-Za-z]:[\\/]", value):
        scp = re.match(r"^(?:[^@/]+@)?([^:/]+):(.+)$", value)
        if scp:
            host, path = scp.groups()
            return f"ssh://{host.lower()}/{_strip_repo_suffix(path).lstrip('/')}"
    local = Path(value).expanduser()
    if not local.is_absolute():
        local = (base or Path.cwd()) / local
    return _strip_repo_suffix(os.path.normcase(str(local.resolve())))


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "project"


def inspect_project_identity(path: Path) -> ProjectIdentity:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        env=sanitized_git_environment(),
        text=True,
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise NotGitProject(f"当前路径不是可识别的 Git 项目：{detail}")
    root_text = result.stdout.strip()
    root = Path(root_text).resolve()
    fetch_urls = _git(
        root, "remote", "get-url", "--all", "origin", allow_failure=True
    ).splitlines()
    push_urls = _git(
        root,
        "remote",
        "get-url",
        "--push",
        "--all",
        "origin",
        allow_failure=True,
    ).splitlines()
    normalized_fetch = [
        normalize_remote(value, base=root) for value in fetch_urls if value
    ]
    normalized_urls = tuple(
        dict.fromkeys(
            normalize_remote(value, base=root)
            for value in (*fetch_urls, *push_urls)
            if value
        )
    )
    remote = normalized_fetch[0] if normalized_fetch else "none"
    return ProjectIdentity(root=root, remote=remote, remote_urls=normalized_urls)


def inspect_project(path: Path) -> ProjectSnapshot:
    identity_snapshot = inspect_project_identity(path)
    root = identity_snapshot.root
    remote = identity_snapshot.remote
    identity = remote if remote != "none" else str(root)
    project_name = remote.rsplit("/", 1)[-1] if remote != "none" else root.name
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    return ProjectSnapshot(
        root=root,
        remote=remote,
        remote_urls=identity_snapshot.remote_urls,
        key=f"{slug(project_name)}-{digest}",
        head=_git(root, "rev-parse", "HEAD"),
        branch=_git(root, "branch", "--show-current") or "detached",
        dirty=bool(_git(root, "status", "--porcelain", "--untracked-files=all")),
    )

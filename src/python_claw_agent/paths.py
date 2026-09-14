from __future__ import annotations

from pathlib import Path
import re
import sys


class PathEscapeError(ValueError):
    """Raised when a tool path would leave the workspace."""


def resolve_in_workdir(work_dir: str | Path, user_path: str) -> Path:
    """Join and resolve a user path, rejecting traversal outside work_dir."""
    base = Path(work_dir).resolve()
    target = (base / user_path).resolve()
    if not _is_inside(base, target):
        raise PathEscapeError(f"路径越界，拒绝访问工作区之外: {user_path}")
    return target


def assert_command_stays_in_workspace(command: str, work_dir: str | Path) -> None:
    """Heuristic jail: reject '..', ~, and absolute paths outside work_dir."""
    if not command or not command.strip():
        return
    base = Path(work_dir).resolve()
    if _DOTDOT.search(command):
        raise PathEscapeError("路径越界，shell 命令不得使用 '..' 离开工作区")
    if _HOME.search(command):
        raise PathEscapeError("路径越界，shell 命令不得使用 ~ 或用户主目录变量离开工作区")
    for raw in iter_abs_path_candidates(command):
        candidate = Path(raw)
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            raise PathEscapeError(f"路径越界，无法解析工作区外路径: {raw}") from exc
        if not _is_inside(base, resolved):
            raise PathEscapeError(f"路径越界，拒绝访问工作区之外: {raw}")


def iter_abs_path_candidates(command: str) -> list[str]:
    found: list[str] = []
    found.extend(re.findall(r'["\']([A-Za-z]:[\\/][^"\']+)["\']', command))
    found.extend(re.findall(r'(?<![A-Za-z])([A-Za-z]:[\\/][^\s;&|<>"\']+)', command))
    found.extend(re.findall(r'(\\\\[^\s;&|<>"\']+)', command))
    if sys.platform == "win32":
        for unix in re.findall(r'(?:^|[\s="\'])(/[a-zA-Z]/[^\s;&|<>"\']*)', command):
            drive = unix[1]
            rest = unix[3:].replace("/", "\\")
            found.append(f"{drive}:\\{rest}")
    else:
        found.extend(re.findall(r'(?:^|[\s="\'])(/[^\s;&|<>"\']*)', command))
    return found


def _is_inside(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


_DOTDOT = re.compile(r'(?:^|[/\\=\s"\'])\.\.(?:[/\\=\s"\']|$)')
_HOME = re.compile(
    r'(?:^|[\s="\'])(?:~(?:[/\\]|$)|%USERPROFILE%|%HOMEPATH%|\$HOME\b|\$env:USERPROFILE\b)',
    re.IGNORECASE,
)

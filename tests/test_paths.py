from pathlib import Path

import pytest

from python_claw_agent.paths import (
    PathEscapeError,
    assert_command_stays_in_workspace,
    resolve_in_workdir,
)


def test_resolve_keeps_inside(tmp_path: Path) -> None:
    target = resolve_in_workdir(tmp_path, "a/b.txt")
    assert target == (tmp_path / "a" / "b.txt").resolve()


def test_resolve_blocks_traversal(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError):
        resolve_in_workdir(tmp_path, "../secret.txt")


def test_command_allows_simple_echo(tmp_path: Path) -> None:
    assert_command_stays_in_workspace("echo hello-claw", tmp_path)


def test_command_allows_dotdot_in_filename(tmp_path: Path) -> None:
    assert_command_stays_in_workspace("echo hello..txt", tmp_path)


def test_command_blocks_cd_dotdot(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError, match="路径越界"):
        assert_command_stays_in_workspace("cd ..", tmp_path)


def test_command_blocks_home(tmp_path: Path) -> None:
    with pytest.raises(PathEscapeError, match="路径越界"):
        assert_command_stays_in_workspace("ls ~", tmp_path)


def test_command_blocks_outside_absolute(tmp_path: Path) -> None:
    outside = (tmp_path.parent / "secret.txt").resolve()
    with pytest.raises(PathEscapeError, match="路径越界"):
        assert_command_stays_in_workspace(f"type {outside}", tmp_path)


def test_command_allows_absolute_inside_workdir(tmp_path: Path) -> None:
    target = (tmp_path / "a.txt").resolve()
    assert_command_stays_in_workspace(f'echo x > "{target}"', tmp_path)

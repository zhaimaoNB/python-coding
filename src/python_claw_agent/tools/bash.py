from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys

from python_claw_agent.paths import PathEscapeError, assert_command_stays_in_workspace
from python_claw_agent.schema import ToolDefinition
from python_claw_agent.tools.registry import BaseTool, parse_args

_PS_UTF8_PREFIX = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$OutputEncoding = [System.Text.Encoding]::UTF8; "
)

_UNIX_LS = {
    "ls",
    "ls -l",
    "ls -la",
    "ls -al",
    "ls -lah",
    "ls -alh",
    "ls -a",
}


class BashTool(BaseTool):
    def __init__(self, work_dir: str, timeout: float = 30.0) -> None:
        self.work_dir = work_dir
        self.timeout = timeout

    def name(self) -> str:
        return "bash"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description=(
                "在当前工作区执行 shell 命令，返回 stdout 与 stderr。"
                "命令不得使用 '..'、~，也不得带工作区外的绝对路径。"
                "列目录请优先使用 list_dir；搜文件内容请使用 grep。"
                "Windows 无 Git Bash 时走 PowerShell；ls / pwd 会改写成等价命令。"
                "不要使用 2>/dev/null、||、&& 等 bash 专用语法。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"}
                },
                "required": ["command"],
            },
        )

    def execute(self, args: str) -> str:
        data = parse_args(args)
        command = data.get("command", "")
        try:
            assert_command_stays_in_workspace(command, self.work_dir)
        except PathEscapeError as exc:
            raise RuntimeError(str(exc)) from exc
        argv = _shell_argv(command)
        try:
            completed = subprocess.run(
                argv,
                cwd=self.work_dir,
                capture_output=True,
                timeout=self.timeout,
                check=False,
                env=_shell_env(),
            )
        except subprocess.TimeoutExpired as exc:
            partial = decode_stream(exc.stdout) + decode_stream(exc.stderr)
            return f"{partial}\n[警告: 命令执行超时({int(self.timeout)}s)，已被系统强制终止。]"

        output = decode_stream(completed.stdout) + decode_stream(completed.stderr)
        if completed.returncode != 0:
            return f"执行报错: exit {completed.returncode}\n输出:\n{output}"
        if not output.strip():
            return "命令执行成功，无终端输出。"
        max_len = 8000
        if len(output) > max_len:
            return f"{output[:max_len]}\n\n...[终端输出过长，已截断至前 {max_len} 字节]..."
        return output


def decode_stream(data: bytes | str | None) -> str:
    """Decode subprocess output without using the locale codec (GBK on Chinese Windows)."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _shell_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    return env


def _normalize_win_command(command: str) -> str:
    stripped = command.strip()
    if stripped in _UNIX_LS:
        return "Get-ChildItem -Force | ForEach-Object { $_.Name }"
    if stripped == "pwd":
        return "(Get-Location).Path"
    return command


def _shell_argv(command: str) -> list[str]:
    if sys.platform == "win32":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.is_file():
            return [str(git_bash), "-c", command]
        body = _PS_UTF8_PREFIX + _normalize_win_command(command)
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", body]
    if shutil.which("bash"):
        return ["bash", "-c", command]
    return ["sh", "-c", command]

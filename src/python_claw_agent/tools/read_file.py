from __future__ import annotations

from python_claw_agent.paths import PathEscapeError, resolve_in_workdir
from python_claw_agent.schema import ToolDefinition
from python_claw_agent.tools.registry import BaseTool, parse_args


class ReadFileTool(BaseTool):
    def __init__(self, work_dir: str) -> None:
        self.work_dir = work_dir

    def name(self) -> str:
        return "read_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="读取指定路径的文件内容。请提供相对工作区的路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径，如 src/python_claw_agent/cli.py",
                    }
                },
                "required": ["path"],
            },
        )

    def execute(self, args: str) -> str:
        data = parse_args(args)
        path = data.get("path", "")
        try:
            full = resolve_in_workdir(self.work_dir, path)
        except PathEscapeError as exc:
            raise RuntimeError(str(exc)) from exc
        try:
            content = full.read_bytes()
        except FileNotFoundError as exc:
            raise RuntimeError(f"打开文件失败: {exc}") from exc
        max_len = 8000
        if len(content) > max_len:
            return (
                content[:max_len].decode("utf-8", errors="replace")
                + f"\n\n...[由于内容过长，已被系统截断至前 {max_len} 字节]..."
            )
        return content.decode("utf-8", errors="replace")

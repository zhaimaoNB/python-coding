from __future__ import annotations

from python_claw_agent.paths import PathEscapeError, resolve_in_workdir
from python_claw_agent.schema import ToolDefinition
from python_claw_agent.tools.registry import BaseTool, parse_args

MAX_ENTRIES = 400


class ListDirTool(BaseTool):
    def __init__(self, work_dir: str) -> None:
        self.work_dir = work_dir

    def name(self) -> str:
        return "list_dir"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="列出工作区内某个目录的文件和子目录。path 相对于工作区，默认当前工作区根目录。不要对目录使用 read_file。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的相对路径，默认 .",
                    }
                },
            },
        )

    def execute(self, args: str) -> str:
        data = parse_args(args)
        path = data.get("path") or "."
        try:
            full = resolve_in_workdir(self.work_dir, path)
        except PathEscapeError as exc:
            raise RuntimeError(str(exc)) from exc
        if not full.exists():
            raise RuntimeError(f"目录不存在: {path}")
        if not full.is_dir():
            raise RuntimeError(f"不是目录: {path}")
        entries = sorted(full.iterdir(), key=lambda p: p.name.lower())
        lines: list[str] = []
        for item in entries[:MAX_ENTRIES]:
            mark = "/" if item.is_dir() else ""
            lines.append(f"{item.name}{mark}")
        if not lines:
            return "(空目录)"
        extra = len(entries) - MAX_ENTRIES
        text = "\n".join(lines)
        if extra > 0:
            text += f"\n\n...[仅显示前 {MAX_ENTRIES} 项，其余 {extra} 项已省略]"
        return text

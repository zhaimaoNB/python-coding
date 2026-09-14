from __future__ import annotations

from python_claw_agent.paths import PathEscapeError, resolve_in_workdir
from python_claw_agent.schema import ToolDefinition
from python_claw_agent.tools.registry import BaseTool, parse_args


class WriteFileTool(BaseTool):
    def __init__(self, work_dir: str) -> None:
        self.work_dir = work_dir

    def name(self) -> str:
        return "write_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="创建或覆盖写入一个文件。如果目录不存在会自动创建。请提供相对于工作区的相对路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要写入的文件路径"},
                    "content": {"type": "string", "description": "要写入的完整文件内容"},
                },
                "required": ["path", "content"],
            },
        )

    def execute(self, args: str) -> str:
        data = parse_args(args)
        path = data.get("path", "")
        content = data.get("content", "")
        try:
            full = resolve_in_workdir(self.work_dir, path)
        except PathEscapeError as exc:
            raise RuntimeError(str(exc)) from exc
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return f"成功将内容写入到文件: {path}"

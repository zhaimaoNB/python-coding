from __future__ import annotations

from typing import TYPE_CHECKING, Any

from python_claw_agent.observability.log import vprint
from python_claw_agent.schema import ToolDefinition
from python_claw_agent.tools.registry import BaseTool, Registry, parse_args

if TYPE_CHECKING:
    from python_claw_agent.engine.loop import AgentEngine
    from python_claw_agent.engine.reporter import Reporter


class SubagentTool(BaseTool):
    def __init__(
        self,
        runner: AgentEngine,
        read_only_registry: Registry,
        reporter: Reporter | None = None,
    ) -> None:
        self.runner = runner
        self.read_only_registry = read_only_registry
        self.reporter = reporter

    def name(self) -> str:
        return "spawn_subagent"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="派出一个专门用于深度探索的子智能体。需要跨文件查找逻辑时调用。完成后返回精炼摘要。",
            input_schema={
                "type": "object",
                "properties": {
                    "task_prompt": {
                        "type": "string",
                        "description": "给子智能体下达的明确探索指令。",
                    }
                },
                "required": ["task_prompt"],
            },
        )

    def execute(self, args: str) -> str:
        data = parse_args(args)
        task_prompt = data.get("task_prompt", "")
        vprint(f"[Subagent] 主 Agent 发起委派: [{task_prompt}]...")
        try:
            summary = self.runner.run_sub(
                task_prompt, self.read_only_registry, self.reporter
            )
        except Exception as exc:
            return f"子智能体执行失败: {exc}"
        vprint("[Subagent] 子智能体任务结束。")
        return f"【子智能体探索报告】:\n{summary}"

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from python_claw_agent.observability.log import vprint
from python_claw_agent.observability.trace import pop_span, start_span
from python_claw_agent.schema import ToolCall, ToolDefinition, ToolResult


class BaseTool(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def definition(self) -> ToolDefinition: ...

    @abstractmethod
    def execute(self, args: str) -> str: ...


MiddlewareFunc = Callable[[ToolCall], tuple[bool, str]]


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._middlewares: list[MiddlewareFunc] = []

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name()] = tool
        vprint(f"[Registry] 成功挂载工具: {tool.name()}")

    def use(self, mw: MiddlewareFunc) -> None:
        self._middlewares.append(mw)

    def get_available_tools(self) -> list[ToolDefinition]:
        return [t.definition() for t in self._tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        _, span = start_span("Tool.Execute")
        span.add_attribute("tool_name", call.name)
        span.add_attribute("arguments", call.arguments)
        try:
            tool = self._tools.get(call.name)
            if tool is None:
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"Error: 系统中不存在名为 '{call.name}' 的工具。",
                    is_error=True,
                )
            for mw in self._middlewares:
                allowed, reason = mw(call)
                if not allowed:
                    span.add_attribute("intercepted", True)
                    return ToolResult(
                        tool_call_id=call.id,
                        output=f"执行被系统拦截。原因: {reason}",
                        is_error=True,
                    )
            try:
                output = tool.execute(call.arguments)
            except Exception as exc:
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"Error executing {call.name}: {exc}",
                    is_error=True,
                )
            preview = output[:100] + ("..." if len(output) > 100 else "")
            span.add_attribute("output_preview", preview)
            return ToolResult(tool_call_id=call.id, output=output, is_error=False)
        finally:
            span.end()
            pop_span(span)


def parse_args(raw: str) -> dict:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("工具参数必须是 JSON 对象")
    return data


def execute_parallel(registry: Registry, calls: list[ToolCall]) -> list[ToolResult]:
    if not calls:
        return []
    results: list[ToolResult | None] = [None] * len(calls)
    with ThreadPoolExecutor(max_workers=max(len(calls), 1)) as pool:
        futures = {pool.submit(registry.execute, call): i for i, call in enumerate(calls)}
        for fut in as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()
    return [r if r is not None else ToolResult(tool_call_id="", output="", is_error=True) for r in results]

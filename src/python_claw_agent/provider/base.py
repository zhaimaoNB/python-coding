from __future__ import annotations

from collections.abc import Callable

from python_claw_agent.schema import Message, ToolDefinition

OnDelta = Callable[[str], None]


class LLMProvider:
    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
        on_delta: OnDelta | None = None,
    ) -> Message:
        raise NotImplementedError

from __future__ import annotations

from python_claw_agent.provider.base import LLMProvider, OnDelta
from python_claw_agent.schema import Message, ToolDefinition, Usage


class ScriptedProvider(LLMProvider):
    """Deterministic provider for tests and offline demos."""

    def __init__(self, script: list[Message]) -> None:
        self.script = list(script)
        self.index = 0

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
        on_delta: OnDelta | None = None,
    ) -> Message:
        if self.index >= len(self.script):
            msg = Message(role="assistant", content="任务完成。")
        else:
            msg = self.script[self.index]
            self.index += 1
        if msg.usage is None:
            msg.usage = Usage(prompt_tokens=10, completion_tokens=5)
        if on_delta and msg.content:
            on_delta(msg.content)
        return msg

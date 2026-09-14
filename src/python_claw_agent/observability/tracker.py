from __future__ import annotations

import time

from python_claw_agent.context.session import Session
from python_claw_agent.observability.log import vprint
from python_claw_agent.provider.base import LLMProvider, OnDelta
from python_claw_agent.schema import Message, ToolDefinition

# USD per 1M tokens (approximate public DeepSeek pricing)
PRICING = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
}


class CostTracker(LLMProvider):
    def __init__(self, next_provider: LLMProvider, model_name: str, session: Session | None = None) -> None:
        self.next_provider = next_provider
        self.model_name = model_name
        self.session = session

    def replace_provider(self, next_provider: LLMProvider, model_name: str) -> None:
        self.next_provider = next_provider
        self.model_name = model_name

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
        on_delta: OnDelta | None = None,
    ) -> Message:
        start = time.perf_counter()
        try:
            resp = self.next_provider.generate(messages, available_tools, on_delta=on_delta)
        except Exception:
            latency = time.perf_counter() - start
            print(f"[Tracker] API 调用失败，耗时: {latency:.3f}s")
            raise
        latency = time.perf_counter() - start
        if resp.usage is not None:
            price = PRICING.get(self.model_name, {"input": 0.0, "output": 0.0})
            cost = (
                resp.usage.prompt_tokens * price["input"]
                + resp.usage.completion_tokens * price["output"]
            ) / 1_000_000
            vprint(
                f"[Tracker] API 调用完成 | 耗时: {latency:.3f}s | "
                f"输入: {resp.usage.prompt_tokens} tk | 输出: {resp.usage.completion_tokens} tk | 花费: ${cost:.6f}"
            )
            if self.session is not None:
                self.session.record_usage(
                    resp.usage.prompt_tokens, resp.usage.completion_tokens, cost
                )
                vprint(f"[Tracker] 当前会话 ({self.session.id}) 累计花费: ${self.session.total_cost:.6f}")
        else:
            vprint(f"[Tracker] API 调用完成，但未返回 Usage 数据 | 耗时: {latency:.3f}s")
        return resp

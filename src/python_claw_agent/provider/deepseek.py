from __future__ import annotations

import os

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI

from python_claw_agent.provider.base import LLMProvider, OnDelta
from python_claw_agent.schema import Message, ToolCall, ToolDefinition, Usage

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
VALIDATE_TIMEOUT_SEC = 20.0


def resolve_base_url(base_url: str | None = None) -> str:
    return (base_url or "").strip() or os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL


def validate_api_key(
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    timeout: float = VALIDATE_TIMEOUT_SEC,
) -> str | None:
    """Probe chat completions. Return None if the key works, else a user-facing error."""
    key = (api_key or "").strip()
    if not key:
        return "密钥为空"
    client = OpenAI(api_key=key, base_url=resolve_base_url(base_url), timeout=timeout)
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
    except AuthenticationError:
        return "密钥无效或已过期"
    except APITimeoutError:
        return "连接 DeepSeek 超时，请检查网络后重试"
    except APIConnectionError:
        return "无法连接 DeepSeek，请检查网络后重试"
    except APIStatusError as exc:
        if exc.status_code in (401, 403):
            return "密钥无效或没有访问权限"
        return f"API 返回 HTTP {exc.status_code}"
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            return "密钥无效或没有访问权限"
        return f"校验失败: {exc}"
    return None


def _to_openai_messages(messages: list[Message]) -> list[dict]:
    openai_msgs: list[dict] = []
    for msg in messages:
        if msg.role == "system":
            openai_msgs.append({"role": "system", "content": msg.content})
        elif msg.role == "user":
            if msg.tool_call_id:
                openai_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content or "",
                    }
                )
            else:
                openai_msgs.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            item: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            openai_msgs.append(item)
    return openai_msgs


def _tool_payload(available_tools: list[ToolDefinition] | None) -> list[dict]:
    tools = available_tools or []
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


def collect_stream(stream, on_delta: OnDelta | None = None) -> Message:
    """Assemble a streamed OpenAI-compatible chat completion into one Message."""
    pieces: list[str] = []
    tool_acc: dict[int, dict[str, str]] = {}
    usage: Usage | None = None
    saw_choice = False
    for chunk in stream:
        if getattr(chunk, "usage", None) is not None:
            raw = chunk.usage
            usage = Usage(
                prompt_tokens=getattr(raw, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(raw, "completion_tokens", 0) or 0,
            )
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        saw_choice = True
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            continue
        text = getattr(delta, "content", None)
        if text:
            pieces.append(text)
            if on_delta:
                on_delta(text)
        for tc in getattr(delta, "tool_calls", None) or []:
            idx = getattr(tc, "index", 0) or 0
            slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
            if getattr(tc, "id", None):
                slot["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn is None:
                continue
            if getattr(fn, "name", None):
                slot["name"] = fn.name
            args = getattr(fn, "arguments", None)
            if args:
                slot["arguments"] += args
    if not saw_choice and usage is None:
        raise RuntimeError("DeepSeek API 返回了空的 Choices")
    result = Message(role="assistant", content="".join(pieces))
    result.usage = usage
    for idx in sorted(tool_acc):
        slot = tool_acc[idx]
        result.tool_calls.append(
            ToolCall(
                id=slot["id"] or f"call_{idx}",
                name=slot["name"],
                arguments=slot["arguments"] or "{}",
            )
        )
    return result


class DeepSeekProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str | None = None,
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not key:
            raise RuntimeError("请设置 DEEPSEEK_API_KEY 环境变量")
        self.model = model
        self.client = OpenAI(
            api_key=key,
            base_url=resolve_base_url(base_url),
        )

    def generate(
        self,
        messages: list[Message],
        available_tools: list[ToolDefinition] | None = None,
        on_delta: OnDelta | None = None,
    ) -> Message:
        kwargs: dict = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        payload = _tool_payload(available_tools)
        if payload:
            kwargs["tools"] = payload
        stream = self.client.chat.completions.create(**kwargs)
        return collect_stream(stream, on_delta)

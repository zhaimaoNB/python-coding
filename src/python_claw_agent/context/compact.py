from __future__ import annotations

from python_claw_agent.schema import ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_USER, Message


class Compactor:
    def __init__(self, max_chars: int = 40_000, retain_last_msgs: int = 12) -> None:
        self.max_chars = max_chars
        self.retain_last_msgs = retain_last_msgs

    def compact(self, msgs: list[Message], *, force: bool = False) -> list[Message]:
        current = self.estimate_length(msgs)
        if not force and current < self.max_chars:
            return msgs

        protect_start = max(0, len(msgs) - self.retain_last_msgs)
        compacted: list[Message] = []
        for i, msg in enumerate(msgs):
            if msg.role == ROLE_SYSTEM:
                compacted.append(msg)
                continue
            if msg.role == ROLE_USER and not msg.tool_call_id:
                compacted.append(msg)
                continue
            new_msg = Message(
                role=msg.role,
                content=msg.content,
                tool_calls=list(msg.tool_calls),
                tool_call_id=msg.tool_call_id,
                usage=msg.usage,
            )
            in_working = i >= protect_start
            if msg.role == ROLE_USER and msg.tool_call_id:
                if not in_working and len(msg.content) > 200:
                    new_msg.content = (
                        f"...[为了节省内存，早期的工具输出已被系统强制清理。原始长度: {len(msg.content)} 字节]..."
                    )
                elif in_working and len(msg.content) > 1000:
                    head = msg.content[:500]
                    tail = msg.content[-500:]
                    new_msg.content = (
                        f"{head}\n\n...[内容过长，中间 {len(msg.content) - 1000} 字节已被系统截断]...\n\n{tail}"
                    )
            elif msg.role == ROLE_ASSISTANT and msg.content:
                if not in_working and len(msg.content) > 200:
                    new_msg.content = "...[早期的推理思考过程已折叠]..."
            compacted.append(new_msg)
        return compacted

    def estimate_length(self, msgs: list[Message]) -> int:
        length = 0
        for msg in msgs:
            length += len(msg.content)
            for tc in msg.tool_calls:
                length += len(tc.name) + len(tc.arguments)
        return length

from __future__ import annotations

import hashlib
import json

from python_claw_agent.observability.log import vprint
from python_claw_agent.schema import ROLE_USER, Message, ToolCall, ToolResult


def _normalize_args(args: str) -> str:
    try:
        data = json.loads(args)
        return json.dumps(data, sort_keys=True, ensure_ascii=False)
    except Exception:
        return args.strip()


def generate_fingerprint(tool_name: str, args: str) -> str:
    payload = tool_name + _normalize_args(args)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


class ReminderInjector:
    def __init__(self) -> None:
        self.consecutive_failures: dict[str, int] = {}

    def check_and_inject(self, last_call: ToolCall, last_result: ToolResult) -> Message | None:
        fingerprint = generate_fingerprint(last_call.name, last_call.arguments)
        if not last_result.is_error:
            self.consecutive_failures = {}
            return None
        self.consecutive_failures[fingerprint] = self.consecutive_failures.get(fingerprint, 0) + 1
        fail_count = self.consecutive_failures[fingerprint]
        vprint(f"[Reminder] 监控到工具 {last_call.name} 执行失败，该参数特征连续失败次数: {fail_count}")
        if fail_count < 3:
            return None
        vprint("[Reminder] 触发死循环干预！注入强力修正指令。")
        nudge = f"""[SYSTEM REMINDER 警告]
你似乎陷入了死循环。你刚刚连续 {fail_count} 次使用相同的参数调用了 '{last_call.name}' 工具，并且都失败了。
请立即停止这种无效的重试！你的注意力被当前的报错过度吸引了。
你需要：
1. 停止猜测参数。跳出当前的局部思维。
2. 彻底改变你的策略。
3. 如果你确实无法通过系统工具解决当前问题，请直接结束任务并向用户说明你需要什么人工帮助。"""
        return Message(role=ROLE_USER, content=nudge)

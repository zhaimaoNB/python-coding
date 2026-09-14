from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import json

from python_claw_agent.schema import ToolCall

AskFn = Callable[[str], str]

DANGEROUS_TOOLS = frozenset({"write_file", "edit_file", "bash"})
PLAN_ARTIFACTS = frozenset({"plan.md", "todo.md"})
DENIED_MESSAGE = (
    "执行被用户拒绝。请不要用相同参数立刻重试；向用户说明你打算做什么，并等待新的指示。"
)
PLAN_DENIED_MESSAGE = (
    "当前是 Plan Mode：系统已拦截这次写操作/命令。"
    "你只能阅读、搜索，以及更新工作区根目录的 PLAN.md / TODO.md。"
    "请把方案写进 PLAN.md，然后等待用户输入 /plan off 批准后再改代码。"
)


def _call_path(call: ToolCall) -> str:
    try:
        data = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("path") or "").strip()


def is_plan_artifact(path: str) -> bool:
    rel = path.replace("\\", "/").strip()
    if rel.startswith("./"):
        rel = rel[2:]
    if not rel or "/" in rel:
        return False
    return Path(rel).name.lower() in PLAN_ARTIFACTS


def is_allowed_in_plan(call: ToolCall) -> bool:
    if call.name not in DANGEROUS_TOOLS:
        return True
    if call.name == "bash":
        return False
    return is_plan_artifact(_call_path(call))


def _tool_args(call: ToolCall) -> dict:
    try:
        data = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _clip(text: str, limit: int = 240) -> str:
    compact = text.replace("\r\n", "\n").rstrip()
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _indent_block(text: str, prefix: str = "      | ") -> str:
    if not text:
        return f"{prefix}(空)"
    lines = text.replace("\r\n", "\n").split("\n")
    shown = lines[:8]
    body = "\n".join(prefix + line for line in shown)
    extra = len(lines) - len(shown)
    if extra > 0:
        body += f"\n      ... 另有 {extra} 行"
    return body


def preview_call(call: ToolCall) -> str:
    """Human-readable summary for confirmation, not a raw JSON dump."""
    data = _tool_args(call)
    if call.name == "write_file":
        path = str(data.get("path") or "?").strip() or "?"
        content = str(data.get("content") or "")
        n_lines = len(content.splitlines()) if content else 0
        header = f"write_file  {path}  （{n_lines} 行，{len(content)} 字）"
        return f"{header}\n{_indent_block(content)}"
    if call.name == "edit_file":
        path = str(data.get("path") or "?").strip() or "?"
        old_text = str(data.get("old_text") or "")
        new_text = str(data.get("new_text") or "")
        old_lines = _clip(old_text, 180).replace("\n", " / ")
        new_lines = _clip(new_text, 180).replace("\n", " / ")
        return f"edit_file  {path}\n      - {old_lines}\n      + {new_lines}"
    if call.name == "bash":
        command = str(data.get("command") or call.arguments)
        return f"bash  {_clip(command, 400)}"
    return f"{call.name}  {_clip(call.arguments, 200)}"


class PermissionGate:
    def __init__(self, auto_yes: bool = False, ask: AskFn | None = None) -> None:
        self.auto_yes = auto_yes
        self._ask = ask or input

    def needs_confirm(self, call: ToolCall) -> bool:
        if call.name not in DANGEROUS_TOOLS:
            return False
        return not self.auto_yes

    def allow(self, call: ToolCall) -> bool:
        """Single-call confirm. Batch flows should use confirm_batch."""
        if not self.needs_confirm(call):
            return True
        approved = self.confirm_batch([call])
        return call.id in approved

    def confirm_batch(self, calls: list[ToolCall]) -> set[str]:
        if not calls:
            return set()
        if self.auto_yes:
            return {call.id for call in calls}
        print()
        if len(calls) == 1:
            print("[Permit] 即将执行:")
        else:
            print(f"[Permit] 本轮共 {len(calls)} 项需确认:")
        for i, call in enumerate(calls, start=1):
            block = preview_call(call)
            numbered = block.split("\n", 1)
            print(f"  {i}. {numbered[0]}")
            if len(numbered) > 1:
                print(numbered[1])
        prompt = "   允许全部执行? [y/N] " if len(calls) > 1 else "   允许执行? [y/N] "
        try:
            ans = self._ask(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return set()
        if ans in {"y", "yes", "是"}:
            return {call.id for call in calls}
        return set()

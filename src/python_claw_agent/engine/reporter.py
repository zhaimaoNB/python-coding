from __future__ import annotations

from typing import Protocol


class Reporter(Protocol):
    def on_thinking(self) -> None: ...

    def on_text_delta(self, text: str) -> None: ...

    def on_tool_call(self, tool_name: str, args: str) -> None: ...

    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None: ...

    def on_message(self, content: str) -> None: ...


class NullReporter:
    def on_thinking(self) -> None:
        return None

    def on_text_delta(self, text: str) -> None:
        return None

    def on_tool_call(self, tool_name: str, args: str) -> None:
        return None

    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        return None

    def on_message(self, content: str) -> None:
        return None


class TerminalReporter:
    def __init__(self) -> None:
        self._streaming = False

    def on_thinking(self) -> None:
        self._end_stream()
        print("\n[Thinking] 模型正在推理...")

    def on_text_delta(self, text: str) -> None:
        if not text:
            return
        if not self._streaming:
            print("\n[Agent]")
            self._streaming = True
        print(text, end="", flush=True)

    def on_tool_call(self, tool_name: str, args: str) -> None:
        self._end_stream()
        print(f"[Tool] {tool_name}")
        display = args.replace("\n", "\\n").replace("\r", "\\r")
        if len(display) > 150:
            display = display[:150] + "... (已截断)"
        print(f"   参数: {display}")

    def on_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
        self._end_stream()
        if is_error:
            print(f"[FAIL] {tool_name}")
            if result:
                print(f"   错误: {result}")
        else:
            print(f"[OK] {tool_name}")

    def on_message(self, content: str) -> None:
        if self._streaming:
            self._end_stream()
            return
        if content:
            print(f"\n[Agent]\n{content}\n")

    def _end_stream(self) -> None:
        if not self._streaming:
            return
        print()
        print()
        self._streaming = False

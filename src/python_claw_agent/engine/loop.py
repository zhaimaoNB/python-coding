from __future__ import annotations

from python_claw_agent.context.compact import Compactor
from python_claw_agent.context.composer import PromptComposer
from python_claw_agent.context.recovery import RecoveryManager
from python_claw_agent.context.session import Session, is_user_task
from python_claw_agent.engine.permission import (
    DENIED_MESSAGE,
    PLAN_DENIED_MESSAGE,
    PermissionGate,
    is_allowed_in_plan,
)
from python_claw_agent.engine.reminder import ReminderInjector
from python_claw_agent.engine.reporter import NullReporter, Reporter
from python_claw_agent.observability.log import vprint
from python_claw_agent.observability.trace import export_trace_to_file, pop_span, start_span
from python_claw_agent.provider.base import LLMProvider
from python_claw_agent.schema import ROLE_ASSISTANT, ROLE_USER, Message, ToolCall, ToolResult
from python_claw_agent.tools.registry import Registry, execute_parallel

SUBAGENT_SYSTEM = """你是一个专门负责深度探索的探路者 (Explorer Subagent)。
你的任务是根据主架构师的指令，在当前工作区内仔细阅读代码、查阅日志，搜集足够的信息。

【核心纪律】
1. 你必须、且只能依靠内置工具（list_dir、read_file、grep）去寻找答案。绝对不允许凭空捏造或猜测！你没有 bash，也不能修改文件。
2. 如果你没有找到确切的答案，你必须继续使用工具深入搜索。
3. 当且仅当你找到了确切的线索后，停止调用工具，直接输出一段纯文本作为你的终极汇报。主架构师会根据你的汇报来做下一步决策。
"""

DEFAULT_MAX_TURNS = 20
MAX_TURNS_CAP = 200


def clamp_max_turns(value: int) -> int:
    return max(1, min(int(value), MAX_TURNS_CAP))


def _latest_user_task(session: Session) -> str:
    for msg in reversed(session.history):
        if is_user_task(msg):
            return msg.content
    return ""


class AgentEngine:
    def __init__(
        self,
        provider: LLMProvider,
        registry: Registry,
        enable_thinking: bool = False,
        plan_mode: bool = False,
        max_turns: int = DEFAULT_MAX_TURNS,
        gate: PermissionGate | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.enable_thinking = enable_thinking
        self.plan_mode = plan_mode
        self.max_turns = clamp_max_turns(max_turns)
        self.gate = gate
        self.compactor = Compactor(max_chars=40_000, retain_last_msgs=12)
        self.recovery = RecoveryManager()
        self.injector = ReminderInjector()

    def run(self, session: Session, reporter: Reporter | None = None) -> None:
        reporter = reporter or NullReporter()
        vprint(f"[Engine] 唤醒会话 [{session.id}]，锁定工作区: {session.work_dir} (PlanMode: {self.plan_mode})")
        _, root_span = start_span("Agent.Run")
        root_span.add_attribute("SessionID", session.id)
        root_span.add_attribute("WorkDir", session.work_dir)
        try:
            composer = PromptComposer(session.work_dir, self.plan_mode)
            system_msg = composer.build(task=_latest_user_task(session))
            last_tools: list[str] = []
            for turn in range(1, self.max_turns + 1):
                _, turn_span = start_span(f"Turn-{turn}")
                try:
                    available_tools = self.registry.get_available_tools()
                    working_memory = session.get_working_memory()
                    context_history = [system_msg, *working_memory]
                    compacted = self.compactor.compact(context_history)
                    turn_span.add_attribute("context_message_count", len(compacted))

                    thinking_content = ""
                    if self.enable_thinking:
                        reporter.on_thinking()
                        _, think_span = start_span("LLM.Thinking")
                        try:
                            think_resp = self._generate(compacted, None, reporter, stream=False)
                        finally:
                            think_span.end()
                            pop_span(think_span)
                        if think_resp.content:
                            thinking_content = think_resp.content
                            compacted = [*compacted, think_resp]

                    _, act_span = start_span("LLM.Action")
                    try:
                        action_resp = self._generate(compacted, available_tools, reporter)
                    finally:
                        act_span.end()
                        pop_span(act_span)

                    session.append(
                        Message(
                            role=ROLE_ASSISTANT,
                            content=(thinking_content + "\n" + action_resp.content).strip(),
                            tool_calls=list(action_resp.tool_calls),
                            usage=action_resp.usage,
                        )
                    )

                    if not action_resp.tool_calls:
                        return

                    last_tools = [call.name for call in action_resp.tool_calls]
                    for call in action_resp.tool_calls:
                        reporter.on_tool_call(call.name, call.arguments)

                    results = self._execute_calls(action_resp.tool_calls)
                    observations: list[Message] = []
                    last_call: ToolCall | None = None
                    last_result: ToolResult | None = None
                    for call, result in zip(action_resp.tool_calls, results):
                        output = result.output
                        if result.is_error:
                            output = self.recovery.analyze_and_inject(call.name, result.output)
                        display = output if len(output) <= 200 else output[:200] + "... (已截断)"
                        reporter.on_tool_result(call.name, display, result.is_error)
                        observations.append(
                            Message(role=ROLE_USER, content=output, tool_call_id=call.id)
                        )
                        if result.is_error or last_result is None:
                            last_call, last_result = call, result
                    session.append(*observations)
                    if last_call is not None and last_result is not None:
                        reminder = self.injector.check_and_inject(last_call, last_result)
                        if reminder is not None:
                            session.append(reminder)
                finally:
                    turn_span.end()
                    pop_span(turn_span)
            self._pause_at_turn_limit(session, reporter, last_tools)
        finally:
            root_span.end()
            pop_span(root_span)
            export_trace_to_file(root_span, session.work_dir, session.id)
            vprint("[Tracing] 本次任务的执行回放链路已保存至工作区的 .claw/traces 目录下")

    def _pause_at_turn_limit(
        self,
        session: Session,
        reporter: Reporter,
        last_tools: list[str],
    ) -> None:
        tools = "、".join(last_tools) if last_tools else "（无）"
        notice = (
            f"本轮已用满 {self.max_turns} 次工具往返，任务尚未结束，我先停在这里。"
            f"最后一次工具：{tools}。"
            "请直接回复「继续」让我接着干；若要提高上限可输入 /turns 40。"
        )
        session.append(Message(role=ROLE_ASSISTANT, content=notice))
        reporter.on_message(notice)
        print(
            f"\n[Turns] 已暂停（上限 {self.max_turns}）。"
            "会话还在。输入「继续」接着干，或 /turns 加大上限后再继续。"
        )

    def _generate(
        self,
        messages: list[Message],
        tools: list | None,
        reporter: Reporter,
        stream: bool = True,
    ) -> Message:
        streamed = False

        def on_delta(text: str) -> None:
            nonlocal streamed
            if not stream or not text:
                return
            streamed = True
            reporter.on_text_delta(text)

        try:
            resp = self.provider.generate(
                messages, tools, on_delta=on_delta if stream else None
            )
        except BaseException:
            if streamed:
                reporter.on_message("")
            raise
        if stream and (streamed or resp.content):
            reporter.on_message(resp.content)
        return resp

    def _execute_calls(self, calls: list[ToolCall]) -> list[ToolResult]:
        allowed: list[ToolCall] = []
        denied: dict[str, ToolResult] = {}
        pending_confirm: list[ToolCall] = []
        for call in calls:
            if self.plan_mode and not is_allowed_in_plan(call):
                print(
                    f"\n[Plan] 已拦截 {call.name}。"
                    "只读规划中不能改代码或跑命令，请写 PLAN.md，或 /plan off 后再动手。"
                )
                denied[call.id] = ToolResult(
                    tool_call_id=call.id,
                    output=PLAN_DENIED_MESSAGE,
                    is_error=True,
                )
                continue
            skip_confirm = (
                self.plan_mode
                and call.name in {"write_file", "edit_file"}
                and is_allowed_in_plan(call)
            )
            if (
                self.gate is not None
                and not skip_confirm
                and self.gate.needs_confirm(call)
            ):
                pending_confirm.append(call)
                continue
            allowed.append(call)
        if pending_confirm and self.gate is not None:
            approved = self.gate.confirm_batch(pending_confirm)
            for call in pending_confirm:
                if call.id in approved:
                    allowed.append(call)
                else:
                    denied[call.id] = ToolResult(
                        tool_call_id=call.id,
                        output=DENIED_MESSAGE,
                        is_error=True,
                    )
        ran = execute_parallel(self.registry, allowed) if allowed else []
        ran_by_id = {call.id: result for call, result in zip(allowed, ran)}
        return [denied.get(call.id) or ran_by_id[call.id] for call in calls]

    def run_sub(
        self,
        task_prompt: str,
        read_only_registry: Registry,
        reporter: Reporter | None = None,
    ) -> str:
        reporter = reporter or NullReporter()
        history = [
            Message(role="system", content=SUBAGENT_SYSTEM),
            Message(role=ROLE_USER, content=task_prompt),
        ]
        max_sub_turns = 10
        for _ in range(max_sub_turns):
            available = read_only_registry.get_available_tools()
            compacted = self.compactor.compact(history)
            action_resp = self.provider.generate(compacted, available)
            history.append(action_resp)
            if not action_resp.tool_calls:
                return action_resp.content
            for call in action_resp.tool_calls:
                reporter.on_tool_call(f"[Subagent] {call.name}", call.arguments)
            results = execute_parallel(read_only_registry, action_resp.tool_calls)
            observations: list[Message] = []
            for call, result in zip(action_resp.tool_calls, results):
                output = result.output
                if result.is_error:
                    output = self.recovery.analyze_and_inject(call.name, result.output)
                display = output if len(output) <= 200 else output[:200] + "... (已截断)"
                reporter.on_tool_result(f"[Subagent] {call.name}", display, result.is_error)
                observations.append(Message(role=ROLE_USER, content=output, tool_call_id=call.id))
            history.extend(observations)
        raise RuntimeError("子智能体探索过于深入，超过 10 轮被强制召回")

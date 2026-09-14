from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from python_claw_agent.apikey import KeyCancelled, collect_valid_key, persist_api_key
from python_claw_agent.context.session import SESSION_WARN_BYTES, global_session_mgr
from python_claw_agent.engine.loop import DEFAULT_MAX_TURNS, AgentEngine, clamp_max_turns
from python_claw_agent.engine.permission import PermissionGate
from python_claw_agent.engine.reporter import TerminalReporter
from python_claw_agent.envfile import load_dotenv
from python_claw_agent.observability.log import is_verbose, set_verbose
from python_claw_agent.observability.tracker import CostTracker
from python_claw_agent.provider.deepseek import DEFAULT_MODEL, DeepSeekProvider
from python_claw_agent.provider.mock import ScriptedProvider
from python_claw_agent.repl_history import configure_readline, remember_input
from python_claw_agent.schema import ROLE_ASSISTANT, ROLE_USER, Message, ToolCall
from python_claw_agent.tools.bash import BashTool
from python_claw_agent.tools.edit_file import EditFileTool
from python_claw_agent.tools.grep import GrepTool
from python_claw_agent.tools.list_dir import ListDirTool
from python_claw_agent.tools.read_file import ReadFileTool
from python_claw_agent.tools.registry import Registry
from python_claw_agent.tools.subagent import SubagentTool
from python_claw_agent.tools.write_file import WriteFileTool


def build_registries(work_dir: str) -> tuple[Registry, Registry]:
    registry = Registry()
    registry.register(ReadFileTool(work_dir))
    registry.register(WriteFileTool(work_dir))
    registry.register(BashTool(work_dir))
    registry.register(EditFileTool(work_dir))
    registry.register(ListDirTool(work_dir))
    registry.register(GrepTool(work_dir))

    read_only = Registry()
    read_only.register(ReadFileTool(work_dir))
    read_only.register(ListDirTool(work_dir))
    read_only.register(GrepTool(work_dir))
    return registry, read_only


def demo_script() -> list[Message]:
    return [
        Message(
            role=ROLE_ASSISTANT,
            content="我先读取 hello.txt。",
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="read_file",
                    arguments='{"path":"hello.txt"}',
                )
            ],
        ),
        Message(
            role=ROLE_ASSISTANT,
            content="hello.txt 是一段向 coding 问好的演示文本。任务完成。",
        ),
    ]


def configure_stdio() -> None:
    """Windows 默认 GBK 控制台无法打印 emoji，先切到 UTF-8 再兜底替换。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            pass


REPL_HELP = """斜杠命令:
  /help   显示本说明
  /cost   显示本会话累计花费
  /clear  清空对话历史（同时擦掉磁盘上的会话记录）
  /compact  折叠早期工具输出并写回磁盘（保留用户任务）
  /key    更换 DeepSeek API Key（隐藏输入，校验通过后写入工作区 .env）
  /plan   切换只读规划（也可 /plan on 或 /plan off）。ON 时只能读和写 PLAN.md / TODO.md，改代码需 /plan off
  /yes    写文件/bash 自动执行（也可 /yes off 改回询问）
  /turns  查看或设置每条消息的工具轮次上限（如 /turns 40）
  /verbose  切换详细日志（挂载工具、Tracker、Trace）
  /exit   退出（也可 /quit）
空行忽略。方向键可翻历史。Ctrl+C：输入时退出；模型执行中则中断本轮。写文件、edit_file、bash 默认会先问你；同一轮多项会一次确认。"""


def _print_banner(
    work_dir: str,
    provider_label: str,
    interactive: bool,
    plan_mode: bool,
    session_id: str,
    history_len: int,
    auto_yes: bool,
) -> None:
    print("==================================================")
    print("[Start] coding")
    print(f"[Workspace] {work_dir}")
    print(f"[Provider] {provider_label}")
    print(f"[Plan] {'ON（只读，仅可写 PLAN.md / TODO.md）' if plan_mode else 'OFF'}")
    restored = f"已恢复 {history_len} 条历史" if history_len else "新会话"
    print(f"[Session] {session_id}  {restored}")
    print(f"[Permit] {'自动执行写操作' if auto_yes else '写文件/bash 需确认（/yes 可关闭询问）'}")
    if interactive:
        print("[Mode] 交互对话  （/help 查看命令，方向键翻历史）")
    print("==================================================")


def _warn_if_session_large(session) -> None:
    size = session.disk_size_bytes()
    if size < SESSION_WARN_BYTES:
        return
    kb = max(1, size // 1024)
    print(f"[Session] 会话文件约 {kb} KB，偏大。可用 /compact 折叠早期工具输出，或 /clear 清空。")


def _print_cost(session) -> None:
    print(
        f"[Cost] ${session.total_cost:.6f} | "
        f"Token: Input {session.total_prompt_tokens}, Output {session.total_completion_tokens}"
    )


def _swap_to_deepseek(engine: AgentEngine, api_key: str, model: str) -> None:
    provider = DeepSeekProvider(api_key=api_key, model=model)
    tracker = engine.provider
    if isinstance(tracker, CostTracker):
        tracker.replace_provider(provider, model)
    else:
        engine.provider = provider


def _handle_slash(line: str, session, engine: AgentEngine, gate, model: str) -> str:
    parts = line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    if cmd in {"/exit", "/quit", "/q"}:
        return "exit"
    if cmd == "/help":
        print(REPL_HELP)
        return "ok"
    if cmd == "/cost":
        _print_cost(session)
        return "ok"
    if cmd == "/clear":
        session.clear_history()
        print("[REPL] 已清空对话历史（磁盘会话已更新）。")
        return "ok"
    if cmd == "/compact":
        before, after = session.compact_history()
        print(f"[REPL] 已折叠早期工具输出：{before} → {after} 字符（用户任务保留）。")
        return "ok"
    if cmd == "/key":
        if len(parts) > 1:
            print("[REPL] 请勿把密钥写在 /key 后面。接下来会提示隐藏输入。")
        print("[REPL] 更换 DeepSeek API Key。")
        try:
            key = collect_valid_key(model=model)
        except KeyCancelled:
            print("[REPL] 已取消更换密钥。")
            return "ok"
        persist_api_key(session.work_dir, key)
        _swap_to_deepseek(engine, key, model)
        print(f"[REPL] 已切换 Provider: DeepSeek/{model}")
        return "ok"
    if cmd == "/plan":
        if arg in {"on", "1", "true"}:
            engine.plan_mode = True
        elif arg in {"off", "0", "false"}:
            engine.plan_mode = False
        else:
            engine.plan_mode = not engine.plan_mode
        print(
            f"[REPL] Plan Mode: {'ON' if engine.plan_mode else 'OFF'}"
            f"{'（只读，批准前不可改代码）' if engine.plan_mode else '（可以改代码）'}"
        )
        return "ok"
    if cmd == "/yes":
        gate.auto_yes = arg not in {"off", "0", "false", "ask"}
        print(f"[REPL] Permit: {'自动执行' if gate.auto_yes else '需确认'}")
        return "ok"
    if cmd == "/turns":
        if not arg:
            print(f"[REPL] Turns: 当前上限 {engine.max_turns}")
            return "ok"
        try:
            engine.max_turns = clamp_max_turns(int(arg))
        except ValueError:
            print("[REPL] 用法: /turns 40   （1–200）")
            return "ok"
        print(f"[REPL] Turns: 上限已设为 {engine.max_turns}")
        return "ok"
    if cmd == "/verbose":
        if arg in {"off", "0", "false"}:
            set_verbose(False)
        elif arg in {"on", "1", "true"}:
            set_verbose(True)
        else:
            set_verbose(not is_verbose())
        print(f"[REPL] Verbose: {'ON' if is_verbose() else 'OFF'}")
        return "ok"
    print(f"[REPL] 未知命令: {cmd}  （输入 /help）")
    return "ok"


def run_once(engine: AgentEngine, session, reporter, prompt: str) -> int:
    print(f"\n[Task] {prompt}\n")
    session.append(Message(role=ROLE_USER, content=prompt))
    try:
        engine.run(session, reporter)
    finally:
        session.save()
    print("==================================================")
    print("[Done] 任务结束。", end=" ")
    _print_cost(session)
    print("==================================================")
    return 0


def run_repl(engine: AgentEngine, session, reporter, gate: PermissionGate, model: str) -> int:
    configure_readline(session.work_dir)
    print()
    print("输入任务后回车。/help 查看命令。")
    print()
    try:
        while True:
            try:
                line = input("you> ").strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print("\n[REPL] 已退出。")
                break
            if not line:
                continue
            remember_input(line)
            if line.startswith("/"):
                if _handle_slash(line, session, engine, gate, model) == "exit":
                    break
                continue
            session.append(Message(role=ROLE_USER, content=line))
            try:
                engine.run(session, reporter)
            except KeyboardInterrupt:
                print("\n[REPL] 已中断本轮，可继续输入。")
            except Exception as exc:
                print(f"[REPL] 本轮失败: {exc}")
            print()
    finally:
        session.save()
    print("==================================================")
    print("[Done] 会话结束。", end=" ")
    _print_cost(session)
    print("==================================================")
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="coding：本地编码助手 Harness")
    parser.add_argument("--prompt", default="", help="一次性任务；省略则进入多轮对话")
    parser.add_argument("--dir", default=".", help="工作区目录，默认当前目录")
    parser.add_argument("--session", default="cli_default_session", help="会话 ID")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DeepSeek 模型名")
    parser.add_argument("--mock", action="store_true", help="使用脚本化 Mock Provider，不调用真实 API")
    parser.add_argument("--thinking", action="store_true", help="开启慢思考阶段")
    parser.add_argument("--plan", action="store_true", help="开启 Plan Mode（只读规划，批准前不可改代码）")
    parser.add_argument("--yes", action="store_true", help="写文件/bash 不询问，自动执行")
    parser.add_argument("--verbose", action="store_true", help="打印 Tracker、Registry、Trace 等详细日志")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"每条消息的工具往返上限，默认 {DEFAULT_MAX_TURNS}，最大 200",
    )
    args = parser.parse_args(argv)

    work_dir = str(Path(args.dir).resolve())
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    load_dotenv(work_dir)
    set_verbose(args.verbose)

    interactive = not args.prompt
    model_name = args.model
    if args.mock:
        provider = ScriptedProvider(demo_script())
        model_name = "mock"
        use_mock = True
    else:
        use_mock = False
        key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
        if not key:
            can_prompt = interactive and sys.stdin.isatty()
            if not can_prompt:
                print(
                    "[CLI] 未设置 DEEPSEEK_API_KEY。"
                    "交互启动会提示输入；一次性任务请先配置环境变量或工作区 .env，或加 --mock。"
                )
                return 1
            print("[CLI] 未检测到 DEEPSEEK_API_KEY。")
            try:
                key = collect_valid_key(model=args.model)
            except KeyCancelled:
                print("[CLI] 已取消。")
                return 1
            persist_api_key(work_dir, key)
        provider = DeepSeekProvider(api_key=key, model=args.model)

    session = global_session_mgr.get_or_create(args.session, work_dir)
    tracked = CostTracker(provider, model_name, session)
    registry, read_only = build_registries(work_dir)
    gate = PermissionGate(auto_yes=args.yes)
    engine = AgentEngine(
        tracked,
        registry,
        enable_thinking=args.thinking,
        plan_mode=args.plan,
        max_turns=clamp_max_turns(args.max_turns),
        gate=gate,
    )
    reporter = TerminalReporter()
    registry.register(SubagentTool(engine, read_only, reporter))

    provider_label = "Mock" if use_mock else f"DeepSeek/{model_name}"
    _print_banner(
        work_dir,
        provider_label,
        interactive,
        engine.plan_mode,
        session.id,
        len(session.history),
        gate.auto_yes,
    )
    _warn_if_session_large(session)

    if interactive:
        return run_repl(engine, session, reporter, gate, args.model)
    return run_once(engine, session, reporter, args.prompt)


if __name__ == "__main__":
    sys.exit(main())

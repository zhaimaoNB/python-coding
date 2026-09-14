from pathlib import Path

from python_claw_agent.context.composer import PromptComposer
from python_claw_agent.context.session import Session
from python_claw_agent.engine.loop import AgentEngine
from python_claw_agent.engine.permission import PLAN_DENIED_MESSAGE, PermissionGate, is_plan_artifact
from python_claw_agent.engine.reporter import NullReporter
from python_claw_agent.provider.mock import ScriptedProvider
from python_claw_agent.schema import ROLE_ASSISTANT, Message, ToolCall
from python_claw_agent.tools.read_file import ReadFileTool
from python_claw_agent.tools.registry import Registry
from python_claw_agent.tools.write_file import WriteFileTool


def _script(calls: list[ToolCall], final: str = "done") -> list[Message]:
    return [
        Message(role=ROLE_ASSISTANT, content="working", tool_calls=calls),
        Message(role=ROLE_ASSISTANT, content=final),
    ]


def test_plan_artifact_only_root_files() -> None:
    assert is_plan_artifact("PLAN.md")
    assert is_plan_artifact("./TODO.md")
    assert not is_plan_artifact("src/PLAN.md")
    assert not is_plan_artifact("x.txt")


def test_plan_mode_blocks_code_write_even_with_yes(tmp_path: Path) -> None:
    gate = PermissionGate(auto_yes=True, ask=lambda _: (_ for _ in ()).throw(AssertionError("asked")))
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(
            _script(
                [
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments='{"path":"app.py","content":"bad"}',
                    )
                ]
            )
        ),
        registry,
        plan_mode=True,
        max_turns=5,
        gate=gate,
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="改代码"))
    engine.run(sess, NullReporter())
    assert not (tmp_path / "app.py").exists()
    assert any(PLAN_DENIED_MESSAGE[:12] in m.content for m in sess.history)


def test_plan_mode_allows_plan_md_without_ask(tmp_path: Path) -> None:
    gate = PermissionGate(
        auto_yes=False,
        ask=lambda _: (_ for _ in ()).throw(AssertionError("asked")),
    )
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(
            _script(
                [
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments='{"path":"PLAN.md","content":"# 方案\\n只读规划"}',
                    )
                ]
            )
        ),
        registry,
        plan_mode=True,
        max_turns=5,
        gate=gate,
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="写计划"))
    engine.run(sess, NullReporter())
    assert "只读规划" in (tmp_path / "PLAN.md").read_text(encoding="utf-8")


def test_plan_mode_blocks_bash(tmp_path: Path) -> None:
    registry = Registry()
    engine = AgentEngine(
        ScriptedProvider(
            _script([ToolCall(id="c1", name="bash", arguments='{"command":"echo hi"}')])
        ),
        registry,
        plan_mode=True,
        max_turns=5,
        gate=PermissionGate(auto_yes=True),
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="跑命令"))
    engine.run(sess, NullReporter())
    assert any("Plan Mode" in m.content for m in sess.history)


def test_plan_mode_allows_read(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    registry = Registry()
    registry.register(ReadFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(
            _script([ToolCall(id="c1", name="read_file", arguments='{"path":"a.txt"}')])
        ),
        registry,
        plan_mode=True,
        max_turns=5,
        gate=PermissionGate(
            auto_yes=False,
            ask=lambda _: (_ for _ in ()).throw(AssertionError("asked")),
        ),
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="读文件"))
    engine.run(sess, NullReporter())
    assert any("hello" in m.content for m in sess.history)


def test_plan_off_then_write_works(tmp_path: Path) -> None:
    gate = PermissionGate(auto_yes=True)
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(
            _script(
                [
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments='{"path":"app.py","content":"ok"}',
                    )
                ]
            )
        ),
        registry,
        plan_mode=False,
        max_turns=5,
        gate=gate,
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="改代码"))
    engine.run(sess, NullReporter())
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "ok"


def test_composer_plan_prompt_is_readonly(tmp_path: Path) -> None:
    msg = PromptComposer(str(tmp_path), plan_mode=True).build()
    assert "只读规划" in msg.content
    assert "/plan off" in msg.content
    assert "不要用 bash" in msg.content

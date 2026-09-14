from pathlib import Path

from python_claw_agent.context.session import Session
from python_claw_agent.engine.loop import AgentEngine
from python_claw_agent.engine.reporter import NullReporter
from python_claw_agent.provider.mock import ScriptedProvider
from python_claw_agent.schema import ROLE_ASSISTANT, Message, ToolCall
from python_claw_agent.tools.read_file import ReadFileTool
from python_claw_agent.tools.registry import Registry
from python_claw_agent.tools.write_file import WriteFileTool


def test_loop_reads_file_then_stops(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello world", encoding="utf-8")
    registry = Registry()
    registry.register(ReadFileTool(str(tmp_path)))
    provider = ScriptedProvider(
        [
            Message(
                role=ROLE_ASSISTANT,
                content="reading",
                tool_calls=[
                    ToolCall(id="c1", name="read_file", arguments='{"path":"hello.txt"}')
                ],
            ),
            Message(role=ROLE_ASSISTANT, content="文件内容是 hello world"),
        ]
    )
    engine = AgentEngine(provider, registry, enable_thinking=False, plan_mode=False, max_turns=5)
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="读 hello.txt"))
    engine.run(sess, NullReporter())
    texts = [m.content for m in sess.history]
    assert any("hello world" in t for t in texts)
    assert any("文件内容是 hello world" in t for t in texts)


def test_loop_max_turns(tmp_path: Path) -> None:
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    forever = Message(
        role=ROLE_ASSISTANT,
        content="again",
        tool_calls=[ToolCall(id="c", name="write_file", arguments='{"path":"x.txt","content":"1"}')],
    )
    provider = ScriptedProvider([forever, forever, forever, forever])
    engine = AgentEngine(provider, registry, max_turns=2, plan_mode=False)
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="loop"))
    engine.run(sess, NullReporter())
    texts = [m.content for m in sess.history]
    assert any("用满 2 次" in t for t in texts)
    assert any("继续" in t for t in texts)


def test_loop_continue_after_pause(tmp_path: Path) -> None:
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    forever = Message(
        role=ROLE_ASSISTANT,
        content="again",
        tool_calls=[ToolCall(id="c", name="write_file", arguments='{"path":"x.txt","content":"1"}')],
    )
    provider = ScriptedProvider(
        [forever, forever, Message(role=ROLE_ASSISTANT, content="收尾完成")]
    )
    engine = AgentEngine(provider, registry, max_turns=2, plan_mode=False)
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="loop"))
    engine.run(sess, NullReporter())
    sess.append(Message(role="user", content="继续"))
    engine.run(sess, NullReporter())
    texts = [m.content for m in sess.history]
    assert any("收尾完成" in t for t in texts)

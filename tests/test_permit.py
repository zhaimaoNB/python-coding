from pathlib import Path

from python_claw_agent.context.session import Session
from python_claw_agent.engine.loop import AgentEngine
from python_claw_agent.engine.permission import DENIED_MESSAGE, PermissionGate, preview_call
from python_claw_agent.engine.reporter import NullReporter
from python_claw_agent.provider.mock import ScriptedProvider
from python_claw_agent.schema import ROLE_ASSISTANT, Message, ToolCall
from python_claw_agent.tools.registry import Registry
from python_claw_agent.tools.write_file import WriteFileTool


def _write_script() -> list[Message]:
    return [
        Message(
            role=ROLE_ASSISTANT,
            content="writing",
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="write_file",
                    arguments='{"path":"x.txt","content":"secret"}',
                )
            ],
        ),
        Message(role=ROLE_ASSISTANT, content="done"),
    ]


def test_gate_allows_read_without_ask(tmp_path: Path) -> None:
    gate = PermissionGate(auto_yes=False, ask=lambda _: (_ for _ in ()).throw(AssertionError("asked")))
    call = ToolCall(id="1", name="read_file", arguments='{"path":"a.txt"}')
    assert gate.allow(call) is True


def test_gate_denies_write(tmp_path: Path) -> None:
    asks = iter(["n"])
    gate = PermissionGate(auto_yes=False, ask=lambda _: next(asks))
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(_write_script()),
        registry,
        plan_mode=False,
        max_turns=5,
        gate=gate,
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="write"))
    engine.run(sess, NullReporter())
    assert not (tmp_path / "x.txt").exists()
    assert any(DENIED_MESSAGE[:8] in m.content or "用户拒绝" in m.content for m in sess.history)


def test_gate_yes_writes_file(tmp_path: Path) -> None:
    asks = iter(["y"])
    gate = PermissionGate(auto_yes=False, ask=lambda _: next(asks))
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(_write_script()),
        registry,
        plan_mode=False,
        max_turns=5,
        gate=gate,
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="write"))
    engine.run(sess, NullReporter())
    assert (tmp_path / "x.txt").read_text(encoding="utf-8") == "secret"


def test_gate_auto_yes_does_not_ask(tmp_path: Path) -> None:
    gate = PermissionGate(auto_yes=True, ask=lambda _: (_ for _ in ()).throw(AssertionError("asked")))
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(_write_script()),
        registry,
        plan_mode=False,
        max_turns=5,
        gate=gate,
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="write"))
    engine.run(sess, NullReporter())
    assert (tmp_path / "x.txt").exists()


def test_preview_write_shows_path_not_json_blob() -> None:
    call = ToolCall(
        id="1",
        name="write_file",
        arguments='{"path":"src/app.py","content":"line1\\nline2\\nline3"}',
    )
    text = preview_call(call)
    assert "src/app.py" in text
    assert "write_file" in text
    assert "3 行" in text
    assert '{"path"' not in text


def test_preview_edit_shows_minus_plus() -> None:
    call = ToolCall(
        id="1",
        name="edit_file",
        arguments='{"path":"a.py","old_text":"foo","new_text":"bar"}',
    )
    text = preview_call(call)
    assert "a.py" in text
    assert "- foo" in text
    assert "+ bar" in text


def test_batch_confirm_asks_once_and_writes_all(tmp_path: Path) -> None:
    asks: list[str] = []

    def ask(prompt: str) -> str:
        asks.append(prompt)
        return "y"

    gate = PermissionGate(auto_yes=False, ask=ask)
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(
            [
                Message(
                    role=ROLE_ASSISTANT,
                    content="writing",
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="write_file",
                            arguments='{"path":"a.txt","content":"A"}',
                        ),
                        ToolCall(
                            id="c2",
                            name="write_file",
                            arguments='{"path":"b.txt","content":"B"}',
                        ),
                    ],
                ),
                Message(role=ROLE_ASSISTANT, content="done"),
            ]
        ),
        registry,
        plan_mode=False,
        max_turns=5,
        gate=gate,
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="write two"))
    engine.run(sess, NullReporter())
    assert len(asks) == 1
    assert "全部" in asks[0]
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "A"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "B"


def test_batch_deny_writes_nothing(tmp_path: Path) -> None:
    asks: list[str] = []

    def ask(prompt: str) -> str:
        asks.append(prompt)
        return "n"

    gate = PermissionGate(auto_yes=False, ask=ask)
    registry = Registry()
    registry.register(WriteFileTool(str(tmp_path)))
    engine = AgentEngine(
        ScriptedProvider(
            [
                Message(
                    role=ROLE_ASSISTANT,
                    content="writing",
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="write_file",
                            arguments='{"path":"a.txt","content":"A"}',
                        ),
                        ToolCall(
                            id="c2",
                            name="write_file",
                            arguments='{"path":"b.txt","content":"B"}',
                        ),
                    ],
                ),
                Message(role=ROLE_ASSISTANT, content="done"),
            ]
        ),
        registry,
        plan_mode=False,
        max_turns=5,
        gate=gate,
    )
    sess = Session(id="t", work_dir=str(tmp_path))
    sess.append(Message(role="user", content="write two"))
    engine.run(sess, NullReporter())
    assert len(asks) == 1
    assert not (tmp_path / "a.txt").exists()
    assert not (tmp_path / "b.txt").exists()

from types import SimpleNamespace

import pytest

from python_claw_agent.engine.reporter import TerminalReporter
from python_claw_agent.provider.deepseek import collect_stream
from python_claw_agent.schema import Message


def _chunk(content=None, tool_calls=None, usage=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice], usage=usage)


def test_collect_stream_joins_text_and_usage() -> None:
    deltas: list[str] = []
    usage = SimpleNamespace(prompt_tokens=4, completion_tokens=2)
    stream = [
        _chunk(content="你"),
        _chunk(content="好"),
        SimpleNamespace(choices=[], usage=usage),
    ]
    msg = collect_stream(stream, deltas.append)
    assert msg.content == "你好"
    assert deltas == ["你", "好"]
    assert msg.usage is not None
    assert msg.usage.prompt_tokens == 4
    assert msg.usage.completion_tokens == 2
    assert msg.tool_calls == []


def test_collect_stream_assembles_tool_calls() -> None:
    fn1 = SimpleNamespace(name="grep", arguments=None)
    fn2 = SimpleNamespace(name=None, arguments='{"pattern":')
    fn3 = SimpleNamespace(name=None, arguments='"DEEPSEEK"}')
    tc1 = SimpleNamespace(index=0, id="call_1", function=fn1)
    tc2 = SimpleNamespace(index=0, id=None, function=fn2)
    tc3 = SimpleNamespace(index=0, id=None, function=fn3)
    msg = collect_stream(
        [
            _chunk(tool_calls=[tc1]),
            _chunk(tool_calls=[tc2]),
            _chunk(tool_calls=[tc3]),
        ]
    )
    assert msg.content == ""
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0].id == "call_1"
    assert msg.tool_calls[0].name == "grep"
    assert msg.tool_calls[0].arguments == '{"pattern":"DEEPSEEK"}'


def test_collect_stream_empty_raises() -> None:
    with pytest.raises(RuntimeError, match="空的 Choices"):
        collect_stream([])


def test_terminal_reporter_does_not_reprint_stream(capsys) -> None:
    reporter = TerminalReporter()
    reporter.on_text_delta("Hel")
    reporter.on_text_delta("lo")
    reporter.on_message("Hello")
    out = capsys.readouterr().out
    assert out.count("Hello") == 1
    assert "[Agent]" in out
    assert "Hel" in out


def test_deepseek_generate_uses_stream(monkeypatch) -> None:
    from python_claw_agent.provider.deepseek import DeepSeekProvider

    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return [_chunk(content="ok")]

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr("python_claw_agent.provider.deepseek.OpenAI", FakeClient)
    provider = DeepSeekProvider()
    msg = provider.generate([Message(role="user", content="hi")])
    assert captured.get("stream") is True
    assert msg.content == "ok"

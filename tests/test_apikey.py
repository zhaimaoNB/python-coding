from types import SimpleNamespace

import pytest

from python_claw_agent.apikey import KeyCancelled, collect_valid_key
from python_claw_agent.provider.deepseek import validate_api_key


def test_collect_valid_key_retries_then_ok(capsys) -> None:
    keys = iter(["bad", "sk-good"])

    def read_fn(_prompt: str) -> str:
        return next(keys)

    def validate_fn(key: str, **_: object) -> str | None:
        if key == "bad":
            return "密钥无效或已过期"
        return None

    assert collect_valid_key(read_fn=read_fn, validate_fn=validate_fn) == "sk-good"
    assert "密钥无效或已过期" in capsys.readouterr().out


def test_collect_valid_key_empty_cancels() -> None:
    with pytest.raises(KeyCancelled):
        collect_valid_key(read_fn=lambda _p: "", validate_fn=lambda *_a, **_k: None)


def test_validate_api_key_ok(monkeypatch) -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[])

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    monkeypatch.setattr("python_claw_agent.provider.deepseek.OpenAI", FakeClient)
    assert validate_api_key("sk-test") is None


def test_validate_api_key_empty() -> None:
    assert validate_api_key("  ") == "密钥为空"


def test_validate_api_key_auth(monkeypatch) -> None:
    class Boom(Exception):
        pass

    class FakeCompletions:
        def create(self, **kwargs):
            raise Boom("invalid")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    monkeypatch.setattr("python_claw_agent.provider.deepseek.AuthenticationError", Boom)
    monkeypatch.setattr("python_claw_agent.provider.deepseek.OpenAI", FakeClient)
    assert validate_api_key("sk-bad") == "密钥无效或已过期"

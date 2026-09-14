from __future__ import annotations

from collections.abc import Callable
from getpass import getpass
from pathlib import Path

from python_claw_agent.envfile import upsert_env_value
from python_claw_agent.provider.deepseek import DEFAULT_MODEL, validate_api_key

ENV_KEY_NAME = "DEEPSEEK_API_KEY"
SECRET_PROMPT = "DeepSeek API Key（不回显，空回车取消）: "


class KeyCancelled(Exception):
    """User skipped key entry (empty input, EOF, or Ctrl+C)."""


def read_secret(prompt: str = SECRET_PROMPT) -> str:
    try:
        return getpass(prompt).strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise KeyCancelled from exc


def persist_api_key(work_dir: str | Path, api_key: str) -> None:
    upsert_env_value(Path(work_dir).resolve() / ".env", ENV_KEY_NAME, api_key)


def collect_valid_key(
    *,
    model: str = DEFAULT_MODEL,
    read_fn: Callable[[str], str] | None = None,
    validate_fn: Callable[..., str | None] | None = None,
) -> str:
    """Prompt until a key passes validation. Empty / Ctrl+C raises KeyCancelled."""
    getter = read_fn or read_secret
    check = validate_fn or validate_api_key
    first = True
    while True:
        prompt = SECRET_PROMPT if first else "请重新输入（空回车取消）: "
        first = False
        raw = getter(prompt)
        if not raw:
            raise KeyCancelled
        err = check(raw, model=model)
        if err is None:
            return raw
        print(f"[CLI] {err}")

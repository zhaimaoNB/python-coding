from __future__ import annotations

from typing import Any

_verbose = False


def set_verbose(enabled: bool) -> None:
    global _verbose
    _verbose = bool(enabled)


def is_verbose() -> bool:
    return _verbose


def vprint(*args: Any, **kwargs: Any) -> None:
    if _verbose:
        print(*args, **kwargs)

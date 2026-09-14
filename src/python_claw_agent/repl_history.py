from __future__ import annotations

from pathlib import Path
import atexit
from typing import Any


def _import_readline() -> Any:
    try:
        import readline

        return readline
    except ImportError:
        try:
            import pyreadline3 as readline  # type: ignore

            return readline
        except ImportError:
            return None


def configure_readline(work_dir: str) -> Path | None:
    readline = _import_readline()
    if readline is None:
        return None
    path = Path(work_dir).resolve() / ".claw" / "repl_history"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            readline.read_history_file(str(path))
        except OSError:
            pass
    try:
        readline.set_history_length(1000)
    except Exception:
        pass

    def _save() -> None:
        try:
            readline.write_history_file(str(path))
        except OSError:
            pass

    atexit.register(_save)
    return path


def _is_secret_line(line: str) -> bool:
    return line.strip().lower().startswith("/key")


def _drop_secret_history() -> None:
    readline = _import_readline()
    if readline is None:
        return
    try:
        length = readline.get_current_history_length()
    except Exception:
        return
    for i in range(length, 0, -1):
        try:
            item = readline.get_history_item(i)
        except Exception:
            continue
        if item is None:
            continue
        if _is_secret_line(str(item)):
            try:
                readline.remove_history_item(i - 1)
            except Exception:
                pass
            return


def remember_input(line: str) -> None:
    if not line:
        return
    if _is_secret_line(line):
        _drop_secret_history()
        return
    readline = _import_readline()
    if readline is None:
        return
    try:
        readline.add_history(line)
    except Exception:
        pass

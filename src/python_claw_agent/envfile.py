from __future__ import annotations

from pathlib import Path
import os


def load_env_file(path: Path) -> dict[str, str]:
    """Load KEY=VALUE lines. Does not override existing environment variables."""
    loaded: dict[str, str] = {}
    if not path.is_file():
        return loaded
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return loaded
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not key or key in os.environ:
            continue
        os.environ[key] = value
        loaded[key] = value
    return loaded


def load_dotenv(work_dir: str | Path) -> None:
    work_env = Path(work_dir).resolve() / ".env"
    cwd_env = Path.cwd() / ".env"
    load_env_file(work_env)
    if cwd_env.resolve() != work_env:
        load_env_file(cwd_env)


def _line_env_key(raw: str) -> str | None:
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        return None
    return line.partition("=")[0].strip()


def upsert_env_value(path: Path, key: str, value: str) -> None:
    """Create or replace KEY=VALUE in an .env file, then set os.environ."""
    lines: list[str] = []
    found = False
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        for raw in existing.splitlines():
            if _line_env_key(raw) == key:
                if not found:
                    lines.append(f"{key}={value}")
                    found = True
                continue
            lines.append(raw)
    if not found:
        lines.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value

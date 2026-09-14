from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
import os
import re

from python_claw_agent.paths import PathEscapeError, resolve_in_workdir
from python_claw_agent.schema import ToolDefinition
from python_claw_agent.tools.registry import BaseTool, parse_args

MAX_MATCHES = 50
MAX_LINE_CHARS = 240
MAX_FILE_BYTES = 1_048_576
HEAD_SAMPLE = 8192

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".claw",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        ".eggs",
        "dist",
        "build",
    }
)
SKIP_FILE_NAMES = frozenset({".env"})
SKIP_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".bmp",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".zip",
        ".gz",
        ".tar",
        ".7z",
        ".rar",
        ".pdf",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".pyc",
        ".pyo",
        ".class",
        ".mp3",
        ".mp4",
        ".wav",
    }
)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _skip_file(path: Path) -> bool:
    name = path.name
    if name in SKIP_FILE_NAMES or name.startswith(".env"):
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def _looks_binary(sample: bytes) -> bool:
    return b"\x00" in sample


def _clip_line(text: str) -> str:
    stripped = text.replace("\t", "    ").rstrip("\r\n")
    if len(stripped) <= MAX_LINE_CHARS:
        return stripped
    return stripped[:MAX_LINE_CHARS] + "..."


def _glob_ok(rel: str, name: str, glob_pat: str) -> bool:
    if not glob_pat:
        return True
    return fnmatch(name, glob_pat) or fnmatch(rel, glob_pat) or fnmatch(rel, f"**/{glob_pat}")


def iter_search_files(root: Path, work_dir: Path) -> list[Path]:
    base = work_dir.resolve()
    if root.is_file():
        resolved = root.resolve()
        if _skip_file(resolved):
            return []
        return [resolved]
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        current = Path(dirpath)
        for name in filenames:
            path = current / name
            if _skip_file(path):
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            try:
                resolved.relative_to(base)
            except ValueError:
                continue
            found.append(resolved)
    found.sort()
    return found


def search_files(
    work_dir: str | Path,
    pattern: str,
    path: str = ".",
    glob: str = "",
    case_insensitive: bool = False,
) -> str:
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        raise RuntimeError(f"无效正则: {exc}") from exc

    try:
        root = resolve_in_workdir(work_dir, path)
    except PathEscapeError as exc:
        raise RuntimeError(str(exc)) from exc
    if not root.exists():
        raise RuntimeError(f"路径不存在: {path}")

    base = Path(work_dir).resolve()
    hits: list[str] = []
    truncated = False
    for file_path in iter_search_files(root, base):
        rel = file_path.relative_to(base).as_posix()
        if not _glob_ok(rel, file_path.name, glob):
            continue
        try:
            size = file_path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            continue
        try:
            data = file_path.read_bytes()
        except OSError:
            continue
        if _looks_binary(data[:HEAD_SAMPLE]):
            continue
        text = data.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                hits.append(f"{rel}:{i}:{_clip_line(line)}")
                if len(hits) >= MAX_MATCHES:
                    truncated = True
                    break
        if truncated:
            break

    if not hits:
        return "(无匹配)"
    out = "\n".join(hits)
    if truncated:
        out += f"\n\n...[仅显示前 {MAX_MATCHES} 条匹配，其余已省略]"
    return out


class GrepTool(BaseTool):
    def __init__(self, work_dir: str) -> None:
        self.work_dir = work_dir

    def name(self) -> str:
        return "grep"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description=(
                "在工作区内搜索文件内容，返回 path:行号:匹配行。"
                "pattern 为正则（普通关键字直接写即可）。"
                "不要用 bash 的 findstr / Select-String / grep 搜代码。"
                "默认跳过 .git、.venv、node_modules、.env 和二进制文件。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "要搜索的正则或关键字",
                    },
                    "path": {
                        "type": "string",
                        "description": "相对工作区的文件或目录，默认 .",
                    },
                    "glob": {
                        "type": "string",
                        "description": "可选文件名过滤，如 *.py",
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "是否忽略大小写，默认 false",
                    },
                },
                "required": ["pattern"],
            },
        )

    def execute(self, args: str) -> str:
        data = parse_args(args)
        pattern = str(data.get("pattern") or "").strip()
        if not pattern:
            raise RuntimeError("缺少 pattern")
        path = str(data.get("path") or ".").strip() or "."
        glob = str(data.get("glob") or "").strip()
        return search_files(
            self.work_dir,
            pattern,
            path=path,
            glob=glob,
            case_insensitive=_truthy(data.get("case_insensitive")),
        )

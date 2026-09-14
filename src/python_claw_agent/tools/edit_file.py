from __future__ import annotations

from python_claw_agent.paths import PathEscapeError, resolve_in_workdir
from python_claw_agent.schema import ToolDefinition
from python_claw_agent.tools.registry import BaseTool, parse_args


class EditFileTool(BaseTool):
    def __init__(self, work_dir: str) -> None:
        self.work_dir = work_dir

    def name(self) -> str:
        return "edit_file"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name(),
            description="对现有文件进行局部的字符串替换。这比重写整个文件更安全、更快速。请提供足够的 old_text 上下文以确保匹配的唯一性。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要修改的文件路径"},
                    "old_text": {
                        "type": "string",
                        "description": "文件中原有的文本。必须包含足够的上下文，以确保唯一性。",
                    },
                    "new_text": {"type": "string", "description": "要替换成的新文本"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        )

    def execute(self, args: str) -> str:
        data = parse_args(args)
        path = data.get("path", "")
        old_text = data.get("old_text", "")
        new_text = data.get("new_text", "")
        try:
            full = resolve_in_workdir(self.work_dir, path)
        except PathEscapeError as exc:
            raise RuntimeError(str(exc)) from exc
        try:
            original = full.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise RuntimeError(f"读取文件失败，请确认路径是否正确: {exc}") from exc
        new_content = fuzzy_replace(original, old_text, new_text)
        full.write_text(new_content, encoding="utf-8")
        return f"成功修改文件: {path}"


def fuzzy_replace(original_content: str, old_text: str, new_text: str) -> str:
    count = original_content.count(old_text)
    if count == 1:
        return original_content.replace(old_text, new_text, 1)
    if count > 1:
        raise RuntimeError(f"old_text 匹配到了 {count} 处，请提供更多的上下文代码以确保唯一性")

    normalized_content = original_content.replace("\r\n", "\n")
    normalized_old = old_text.replace("\r\n", "\n")
    count = normalized_content.count(normalized_old)
    if count == 1:
        return normalized_content.replace(normalized_old, new_text, 1)

    trimmed_old = normalized_old.strip()
    if trimmed_old:
        count = normalized_content.count(trimmed_old)
        if count == 1:
            return normalized_content.replace(trimmed_old, new_text, 1)

    return line_by_line_replace(normalized_content, normalized_old, new_text)


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _split_replacement_lines(new_text: str) -> list[str]:
    lines = new_text.replace("\r\n", "\n").split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines = lines[:-1]
    return lines


def align_replacement(new_text: str, block_indent: str, last_indent: str | None = None) -> list[str]:
    """Fit replacement lines to the matched block's indent. Never insert as one jammed line."""
    lines = _split_replacement_lines(new_text)
    if not lines:
        return []
    nonempty = [ln for ln in lines if ln.strip()]
    if not nonempty:
        return [""] * len(lines)

    first_ws = _leading_ws(nonempty[0])
    last_ws = _leading_ws(nonempty[-1])
    orig_last = last_indent if last_indent is not None else block_indent
    later = nonempty[1:]

    mixed = (
        len(first_ws) < len(block_indent)
        and len(block_indent) > 0
        and bool(later)
        and len(last_ws) == len(orig_last)
        and len(orig_last) >= len(block_indent)
    )
    if mixed:
        out: list[str] = []
        first_done = False
        for ln in lines:
            if not ln.strip():
                out.append("")
                continue
            if not first_done:
                out.append(block_indent + ln.lstrip(" \t"))
                first_done = True
            else:
                out.append(ln)
        return out

    min_len = min(len(_leading_ws(ln)) for ln in nonempty)
    out = []
    for ln in lines:
        if not ln.strip():
            out.append("")
            continue
        ws_len = len(_leading_ws(ln))
        rest = ln[min_len:] if ws_len >= min_len else ln.lstrip(" \t")
        out.append(block_indent + rest)
    return out


def line_by_line_replace(content: str, old_text: str, new_text: str) -> str:
    content_lines = content.split("\n")
    old_lines = [line.strip() for line in old_text.strip().split("\n")]
    if not old_lines or len(content_lines) < len(old_lines):
        raise RuntimeError("找不到该代码片段")

    match_count = 0
    match_start = -1
    match_end = -1
    for i in range(0, len(content_lines) - len(old_lines) + 1):
        if all(content_lines[i + j].strip() == old_lines[j] for j in range(len(old_lines))):
            match_count += 1
            match_start = i
            match_end = i + len(old_lines)

    if match_count == 0:
        raise RuntimeError("在文件中未找到 old_text，请检查内容和缩进")
    if match_count > 1:
        raise RuntimeError(f"模糊匹配到了 {match_count} 处代码，请提供更多上下文以定位")

    block_indent = _leading_ws(content_lines[match_start])
    last_indent = _leading_ws(content_lines[match_end - 1])
    replacement = align_replacement(new_text, block_indent, last_indent)
    new_lines = content_lines[:match_start] + replacement + content_lines[match_end:]
    return "\n".join(new_lines)

from pathlib import Path

import pytest

from python_claw_agent.tools.edit_file import EditFileTool, fuzzy_replace
from python_claw_agent.tools.list_dir import ListDirTool
from python_claw_agent.tools.read_file import ReadFileTool
from python_claw_agent.tools.write_file import WriteFileTool


def test_write_and_read(tmp_path: Path) -> None:
    WriteFileTool(str(tmp_path)).execute('{"path":"hello.txt","content":"hi"}')
    out = ReadFileTool(str(tmp_path)).execute('{"path":"hello.txt"}')
    assert out == "hi"


def test_read_blocks_escape(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="路径越界"):
        ReadFileTool(str(tmp_path)).execute('{"path":"../outside.txt"}')


def test_list_dir_names(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    out = ListDirTool(str(tmp_path)).execute("{}")
    assert "a.txt" in out
    assert "sub/" in out


def test_list_dir_blocks_escape(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="路径越界"):
        ListDirTool(str(tmp_path)).execute('{"path":".."}')


def test_fuzzy_exact() -> None:
    assert fuzzy_replace("abc", "b", "B") == "aBc"


def test_fuzzy_indent(tmp_path: Path) -> None:
    src = "func main() {\n    if true {\n        fmt.Println(1)\n    }\n}\n"
    (tmp_path / "server.go").write_text(src, encoding="utf-8")
    tool = EditFileTool(str(tmp_path))
    tool.execute(
        '{"path":"server.go","old_text":"if true {\\nfmt.Println(1)\\n}","new_text":"if false {\\n        fmt.Println(2)\\n    }"}'
    )
    text = (tmp_path / "server.go").read_text(encoding="utf-8")
    assert "    if false {" in text
    assert "        fmt.Println(2)" in text
    assert "            fmt.Println(2)" not in text
    assert "    }" in text


def test_fuzzy_relative_indent() -> None:
    src = "def outer():\n    if True:\n        x = 1\n        return x\n"
    out = fuzzy_replace(src, "if True:\nx = 1\nreturn x", "if False:\n    x = 2\n    return x")
    assert out == "def outer():\n    if False:\n        x = 2\n        return x\n"


def test_fuzzy_unique_required() -> None:
    with pytest.raises(RuntimeError, match="匹配到了 2 处"):
        fuzzy_replace("foo\nfoo", "foo", "bar")

from pathlib import Path

import pytest

from python_claw_agent.tools.grep import MAX_MATCHES, GrepTool


def test_grep_hits_with_line_numbers(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("alpha\nDEEPSEEK_API_KEY = 1\nbeta\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "util.py").write_text("print('hello')\n", encoding="utf-8")
    out = GrepTool(str(tmp_path)).execute('{"pattern":"DEEPSEEK"}')
    assert "app.py:2:DEEPSEEK_API_KEY = 1" in out
    assert "util.py" not in out


def test_grep_no_match(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    out = GrepTool(str(tmp_path)).execute('{"pattern":"zzzz-not-there"}')
    assert out == "(无匹配)"


def test_grep_blocks_escape(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="路径越界"):
        GrepTool(str(tmp_path)).execute('{"pattern":"x","path":".."}')


def test_grep_skips_venv_and_env(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("TOKEN_UNIQUE = 1\n", encoding="utf-8")
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "secret.py").write_text("TOKEN_UNIQUE = 2\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN_UNIQUE=hidden\n", encoding="utf-8")
    out = GrepTool(str(tmp_path)).execute('{"pattern":"TOKEN_UNIQUE"}')
    assert "src/main.py:1:" in out.replace("\\", "/")
    assert ".venv" not in out
    assert ".env" not in out


def test_grep_glob_filter(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("needle here\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("needle here\n", encoding="utf-8")
    out = GrepTool(str(tmp_path)).execute('{"pattern":"needle","glob":"*.py"}')
    assert "a.py:" in out
    assert "a.md" not in out


def test_grep_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("DeepSeek\n", encoding="utf-8")
    miss = GrepTool(str(tmp_path)).execute('{"pattern":"deepseek"}')
    assert miss == "(无匹配)"
    hit = GrepTool(str(tmp_path)).execute('{"pattern":"deepseek","case_insensitive":true}')
    assert "a.txt:1:DeepSeek" in hit


def test_grep_truncates(tmp_path: Path) -> None:
    lines = "\n".join(f"hit {i}" for i in range(MAX_MATCHES + 10))
    (tmp_path / "many.txt").write_text(lines + "\n", encoding="utf-8")
    out = GrepTool(str(tmp_path)).execute('{"pattern":"hit"}')
    assert f"仅显示前 {MAX_MATCHES} 条" in out
    assert out.count("\n") >= MAX_MATCHES


def test_grep_invalid_regex(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="无效正则"):
        GrepTool(str(tmp_path)).execute('{"pattern":"("}')


def test_grep_missing_pattern(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="缺少 pattern"):
        GrepTool(str(tmp_path)).execute("{}")

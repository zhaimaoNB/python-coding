from pathlib import Path

import json
import pytest

from python_claw_agent.tools.bash import BashTool, decode_stream


def test_bash_echo(tmp_path: Path) -> None:
    out = BashTool(str(tmp_path)).execute('{"command":"echo hello-claw"}')
    assert "hello-claw" in out


def test_decode_utf8_that_is_invalid_gbk() -> None:
    raw = "内网设备配置".encode("utf-8")
    try:
        raw.decode("gbk")
        gbk_ok = True
    except UnicodeDecodeError:
        gbk_ok = False
    assert not gbk_ok
    assert decode_stream(raw) == "内网设备配置"


def test_decode_never_raises_on_garbage() -> None:
    assert "\ufffd" in decode_stream(b"\xab\x00\xff") or decode_stream(b"\xab\x00\xff")


def test_bash_lists_chinese_filename(tmp_path: Path) -> None:
    work = tmp_path / "内网设备配置"
    work.mkdir()
    (work / "交换机.txt").write_text("ok", encoding="utf-8")
    out = BashTool(str(work)).execute('{"command":"ls"}')
    assert "交换机" in out
    assert "UnicodeDecodeError" not in out
    assert "无终端输出" not in out


def test_bash_rejects_cd_dotdot(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="路径越界"):
        BashTool(str(tmp_path)).execute('{"command":"cd .."}')


def test_bash_rejects_outside_absolute(tmp_path: Path) -> None:
    outside = str((tmp_path.parent / "secret.txt").resolve())
    payload = json.dumps({"command": f"type {outside}"})
    with pytest.raises(RuntimeError, match="路径越界"):
        BashTool(str(tmp_path)).execute(payload)


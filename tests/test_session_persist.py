from pathlib import Path

from python_claw_agent.context.session import Session, SessionManager, session_file
from python_claw_agent.schema import ROLE_ASSISTANT, ROLE_USER, Message, ToolCall


def test_session_roundtrip_on_disk(tmp_path: Path) -> None:
    mgr = SessionManager()
    sess = mgr.get_or_create("alpha", str(tmp_path))
    sess.append(
        Message(role=ROLE_USER, content="记住苹果"),
        Message(
            role=ROLE_ASSISTANT,
            content="好的",
            tool_calls=[ToolCall(id="c1", name="list_dir", arguments='{"path":"."}')],
        ),
    )
    sess.record_usage(10, 4, 0.001)
    path = session_file(tmp_path, "alpha")
    assert path.is_file()

    mgr.clear_cache()
    loaded = mgr.get_or_create("alpha", str(tmp_path))
    assert [m.content for m in loaded.history] == ["记住苹果", "好的"]
    assert loaded.history[1].tool_calls[0].name == "list_dir"
    assert loaded.total_prompt_tokens == 10
    assert loaded.total_cost == 0.001


def test_sessions_isolated_by_workdir(tmp_path: Path) -> None:
    a = tmp_path / "wa"
    b = tmp_path / "wb"
    a.mkdir()
    b.mkdir()
    mgr = SessionManager()
    sa = mgr.get_or_create("cli_default_session", str(a))
    sa.append(Message(role=ROLE_USER, content="in-a"))
    sb = mgr.get_or_create("cli_default_session", str(b))
    assert sb.history == []
    assert sa.history[0].content == "in-a"


def test_clear_history_rewrites_disk(tmp_path: Path) -> None:
    mgr = SessionManager()
    sess = mgr.get_or_create("wipe", str(tmp_path))
    sess.append(Message(role=ROLE_USER, content="gone"))
    sess.clear_history()
    mgr.clear_cache()
    loaded = mgr.get_or_create("wipe", str(tmp_path))
    assert loaded.history == []


def test_unsafe_session_id_stays_in_workdir(tmp_path: Path) -> None:
    mgr = SessionManager()
    sess = mgr.get_or_create("../escape", str(tmp_path))
    sess.append(Message(role=ROLE_USER, content="x"))
    path = session_file(tmp_path, "../escape")
    assert path.parent == (tmp_path / ".claw" / "sessions").resolve()
    assert path.is_file()


def test_direct_session_does_not_write_disk(tmp_path: Path) -> None:
    sess = Session(id="ephemeral", work_dir=str(tmp_path))
    sess.append(Message(role=ROLE_USER, content="no-disk"))
    assert not session_file(tmp_path, "ephemeral").exists()


def test_compact_history_rewrites_disk(tmp_path: Path) -> None:
    mgr = SessionManager()
    sess = mgr.get_or_create("fat", str(tmp_path))
    secret = "暗号是蓝桥"
    sess.append(
        Message(role=ROLE_USER, content=secret),
        Message(role=ROLE_ASSISTANT, content="think " + "y" * 300),
        Message(role=ROLE_USER, content="Z" * 800, tool_call_id="t1"),
        Message(role=ROLE_ASSISTANT, content="recent reply"),
    )
    path = session_file(tmp_path, "fat")
    before_size = path.stat().st_size
    before, after = sess.compact_history(retain_last_msgs=1)
    assert after < before
    assert sess.history[0].content == secret
    assert "早期的工具输出" in sess.history[2].content
    assert path.stat().st_size < before_size
    mgr.clear_cache()
    loaded = mgr.get_or_create("fat", str(tmp_path))
    assert loaded.history[0].content == secret
    assert "早期的工具输出" in loaded.history[2].content

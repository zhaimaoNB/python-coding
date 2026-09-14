from pathlib import Path

from python_claw_agent.context.composer import PromptComposer
from python_claw_agent.context.recovery import RecoveryManager
from python_claw_agent.context.session import Session
from python_claw_agent.engine.reminder import ReminderInjector
from python_claw_agent.observability.log import set_verbose
from python_claw_agent.schema import ROLE_USER, Message, ToolCall, ToolResult


def test_session_drops_orphan_tool_result() -> None:
    sess = Session(id="s", work_dir=".")
    sess.append(
        Message(role=ROLE_USER, content="tool-out", tool_call_id="abc"),
        Message(role=ROLE_USER, content="hello"),
        Message(role="assistant", content="ok"),
    )
    mem = sess.get_working_memory(2)
    assert mem[0].content == "hello"
    assert mem[0].tool_call_id == ""


def test_composer_loads_agents_and_skills(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("必须用中文", encoding="utf-8")
    skill_dir = tmp_path / ".claw" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: 演示技能\ntriggers: 演示技能\n---\n\n# body\nSECRET_BODY\n",
        encoding="utf-8",
    )
    catalog = PromptComposer(str(tmp_path), plan_mode=True).build()
    assert "必须用中文" in catalog.content
    assert "demo" in catalog.content
    assert "演示技能" in catalog.content
    assert "SECRET_BODY" not in catalog.content
    assert "Plan Mode" in catalog.content
    assert "coding" in catalog.content

    loaded = PromptComposer(str(tmp_path), plan_mode=True).build(task="请按演示技能处理")
    assert "SECRET_BODY" in loaded.content
    assert "已加载技能: demo" in loaded.content


def test_recovery_edit_hint() -> None:
    out = RecoveryManager().analyze_and_inject("edit_file", "在文件中未找到 old_text")
    assert "read_file" in out


def test_reminder_triggers_on_third_same_failure() -> None:
    inj = ReminderInjector()
    call = ToolCall(id="1", name="read_file", arguments='{"path":"a.txt"}')
    err = ToolResult(tool_call_id="1", output="missing", is_error=True)
    assert inj.check_and_inject(call, err) is None
    assert inj.check_and_inject(call, err) is None
    msg = inj.check_and_inject(call, err)
    assert msg is not None
    assert "死循环" in msg.content


def test_reminder_normalizes_whitespace() -> None:
    inj = ReminderInjector()
    a = ToolCall(id="1", name="read_file", arguments='{"path": "a.txt"}')
    b = ToolCall(id="2", name="read_file", arguments='{"path":"a.txt"}')
    err = ToolResult(tool_call_id="1", output="x", is_error=True)
    inj.check_and_inject(a, err)
    inj.check_and_inject(b, err)
    msg = inj.check_and_inject(a, err)
    assert msg is not None


def test_reminder_logs_only_when_verbose(capsys) -> None:
    call = ToolCall(id="1", name="read_file", arguments='{"path":"a.txt"}')
    err = ToolResult(tool_call_id="1", output="missing", is_error=True)
    set_verbose(False)
    inj = ReminderInjector()
    inj.check_and_inject(call, err)
    inj.check_and_inject(call, err)
    inj.check_and_inject(call, err)
    assert "[Reminder]" not in capsys.readouterr().out

    set_verbose(True)
    inj2 = ReminderInjector()
    inj2.check_and_inject(call, err)
    inj2.check_and_inject(call, err)
    inj2.check_and_inject(call, err)
    out = capsys.readouterr().out
    set_verbose(False)
    assert "[Reminder]" in out
    assert "死循环干预" in out

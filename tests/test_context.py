from python_claw_agent.context.compact import Compactor
from python_claw_agent.context.session import select_working_memory
from python_claw_agent.schema import ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_USER, Message, ToolCall


def test_compactor_masks_old_tool_output() -> None:
    msgs = [
        Message(role=ROLE_SYSTEM, content="sys"),
        Message(role=ROLE_USER, content="x" * 500, tool_call_id="t1"),
        Message(role=ROLE_ASSISTANT, content="think " + "y" * 300),
        Message(role=ROLE_USER, content="recent"),
    ]
    compacted = Compactor(max_chars=10, retain_last_msgs=1).compact(msgs)
    assert compacted[0].content == "sys"
    assert "早期的工具输出" in compacted[1].content
    assert "早期的推理" in compacted[2].content
    assert compacted[3].content == "recent"


def test_compactor_skips_when_short() -> None:
    msgs = [Message(role=ROLE_USER, content="hi")]
    assert Compactor(max_chars=1000).compact(msgs) is msgs


def test_compactor_force_runs_when_short() -> None:
    msgs = [
        Message(role=ROLE_USER, content="task"),
        Message(role=ROLE_USER, content="x" * 500, tool_call_id="t1"),
        Message(role=ROLE_ASSISTANT, content="done"),
    ]
    skipped = Compactor(max_chars=100_000, retain_last_msgs=1).compact(msgs)
    assert skipped is msgs
    forced = Compactor(max_chars=100_000, retain_last_msgs=1).compact(msgs, force=True)
    assert forced is not msgs
    assert "早期的工具输出" in forced[1].content
    assert forced[0].content == "task"


def test_compactor_never_folds_user_task() -> None:
    secret = "暗号是蓝桥" + "!" * 300
    msgs = [
        Message(role=ROLE_SYSTEM, content="sys"),
        Message(role=ROLE_USER, content=secret),
        Message(role=ROLE_USER, content="t" * 400, tool_call_id="t1"),
        Message(role=ROLE_ASSISTANT, content="ok"),
    ]
    compacted = Compactor(max_chars=10, retain_last_msgs=1).compact(msgs)
    assert compacted[1].content == secret


def test_working_memory_keeps_old_user_task_after_tool_flood() -> None:
    history = [Message(role=ROLE_USER, content="暗号是蓝桥")]
    for i in range(30):
        history.append(
            Message(
                role=ROLE_ASSISTANT,
                content=f"call-{i}",
                tool_calls=[ToolCall(id=f"c{i}", name="list_dir", arguments="{}")],
            )
        )
        history.append(Message(role=ROLE_USER, content=f"out-{i}", tool_call_id=f"c{i}"))
    history.append(Message(role=ROLE_USER, content="我的暗号是什么？"))
    mem = select_working_memory(history, tail_limit=8, max_user_tasks=6)
    assert mem[0].content == "暗号是蓝桥"
    assert mem[-1].content == "我的暗号是什么？"
    assert not any("断点标记" in m.content for m in mem)


def test_working_memory_keeps_last_n_user_tasks() -> None:
    history = []
    for i in range(8):
        history.append(Message(role=ROLE_USER, content=f"task-{i}"))
        history.append(Message(role=ROLE_ASSISTANT, content=f"ok-{i}"))
    mem = select_working_memory(history, max_user_tasks=6)
    user_tasks = [m.content for m in mem if m.role == ROLE_USER and not m.tool_call_id]
    assert user_tasks == [f"task-{i}" for i in range(2, 8)]


def test_working_memory_does_not_start_on_tool_result() -> None:
    history = [
        Message(role=ROLE_USER, content="hello"),
        Message(role=ROLE_ASSISTANT, content="working", tool_calls=[ToolCall(id="c", name="list_dir", arguments="{}")]),
        Message(role=ROLE_USER, content="files", tool_call_id="c"),
        Message(role=ROLE_ASSISTANT, content="done"),
    ]
    mem = select_working_memory(history, tail_limit=2)
    assert mem[0].content == "hello"
    assert mem[0].tool_call_id == ""

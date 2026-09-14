import sys

from python_claw_agent.cli import build_registries, main
from python_claw_agent.context.session import Session, SessionManager, global_session_mgr
from python_claw_agent.schema import ROLE_ASSISTANT, ROLE_USER, Message


def test_cli_mock_run(tmp_path) -> None:
    hello = tmp_path / "hello.txt"
    hello.write_text("demo text", encoding="utf-8")
    code = main(
        [
            "--prompt",
            "读取 hello.txt 并总结",
            "--dir",
            str(tmp_path),
            "--mock",
            "--session",
            "oneshot",
        ]
    )
    assert code == 0


def test_repl_exit_immediately(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "/exit")
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_exit"])
    assert code == 0


def test_repl_multi_turn_keeps_history(tmp_path, monkeypatch) -> None:
    (tmp_path / "hello.txt").write_text("demo text", encoding="utf-8")
    lines = iter(["读取 hello.txt", "再问一句", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_multi"])
    assert code == 0
    sess = global_session_mgr.get_or_create("repl_multi", str(tmp_path))
    user_texts = [m.content for m in sess.history if m.role == "user" and not m.tool_call_id]
    assert "读取 hello.txt" in user_texts
    assert "再问一句" in user_texts


def test_repl_clear_and_unknown_command(tmp_path, monkeypatch, capsys) -> None:
    (tmp_path / "hello.txt").write_text("demo text", encoding="utf-8")
    lines = iter(["读取 hello.txt", "/clear", "/nope", "/cost", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_clear"])
    assert code == 0
    sess = global_session_mgr.get_or_create("repl_clear", str(tmp_path))
    assert sess.history == []
    out = capsys.readouterr().out
    assert "未知命令" in out
    assert "[Cost]" in out


def test_repl_ctrl_c_on_input_exits(tmp_path, monkeypatch) -> None:
    def boom(_prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", boom)
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_int"])
    assert code == 0


def test_default_dir_is_cwd(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "/exit")
    code = main(["--mock", "--session", "cwd_default"])
    assert code == 0
    out = capsys.readouterr().out
    assert str(tmp_path.resolve()) in out
    assert "[Plan] OFF" in out


def test_repl_plan_toggle(tmp_path, monkeypatch, capsys) -> None:
    lines = iter(["/plan", "/plan off", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_plan"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Plan Mode: ON" in out
    assert "Plan Mode: OFF" in out
    assert "只读" in out
    assert "可以改代码" in out


def test_repl_yes_toggle(tmp_path, monkeypatch, capsys) -> None:
    lines = iter(["/yes", "/yes off", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_yes"])
    assert code == 0
    out = capsys.readouterr().out
    assert "自动执行" in out
    assert "需确认" in out


def test_cli_plan_flag_starts_on(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "/exit")
    code = main(["--dir", str(tmp_path), "--mock", "--plan", "--session", "repl_plan_flag"])
    assert code == 0
    assert "[Plan] ON" in capsys.readouterr().out


def test_subagent_registry_is_readonly(tmp_path) -> None:
    full, read_only = build_registries(str(tmp_path))
    ro_names = {t.name for t in read_only.get_available_tools()}
    full_names = {t.name for t in full.get_available_tools()}
    assert ro_names == {"read_file", "list_dir", "grep"}
    assert "bash" in full_names
    assert "list_dir" in full_names
    assert "grep" in full_names
    assert "write_file" not in ro_names


def test_cli_restores_session_from_disk(tmp_path, monkeypatch, capsys) -> None:
    (tmp_path / "hello.txt").write_text("demo text", encoding="utf-8")
    lines = iter(["读取 hello.txt", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    assert main(["--dir", str(tmp_path), "--mock", "--session", "persist_cli"]) == 0
    global_session_mgr.clear_cache()
    monkeypatch.setattr("builtins.input", lambda _: "/exit")
    assert main(["--dir", str(tmp_path), "--mock", "--session", "persist_cli"]) == 0
    out = capsys.readouterr().out
    assert "已恢复" in out
    sess = global_session_mgr.get_or_create("persist_cli", str(tmp_path))
    assert any(m.content == "读取 hello.txt" for m in sess.history)


def test_cli_quiet_hides_internal_logs(tmp_path, capsys) -> None:
    hello = tmp_path / "hello.txt"
    hello.write_text("demo text", encoding="utf-8")
    main(
        [
            "--prompt",
            "读取 hello.txt 并总结",
            "--dir",
            str(tmp_path),
            "--mock",
            "--session",
            "quiet_logs",
        ]
    )
    out = capsys.readouterr().out
    assert "[Registry]" not in out
    assert "[Tracker]" not in out
    assert "[Engine]" not in out
    assert "[Agent]" in out


def test_cli_verbose_shows_internal_logs(tmp_path, capsys) -> None:
    hello = tmp_path / "hello.txt"
    hello.write_text("demo text", encoding="utf-8")
    main(
        [
            "--prompt",
            "读取 hello.txt 并总结",
            "--dir",
            str(tmp_path),
            "--mock",
            "--verbose",
            "--session",
            "verbose_logs",
        ]
    )
    out = capsys.readouterr().out
    assert "[Registry]" in out
    assert "[Tracker]" in out


def test_repl_verbose_toggle(tmp_path, monkeypatch, capsys) -> None:
    lines = iter(["/verbose", "/verbose off", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_verbose"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Verbose: ON" in out
    assert "Verbose: OFF" in out


def test_prompt_without_key_exits(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    code = main(
        [
            "--prompt",
            "读取 hello.txt",
            "--dir",
            str(tmp_path),
            "--session",
            "no_key_once",
        ]
    )
    assert code == 1
    assert "未设置 DEEPSEEK_API_KEY" in capsys.readouterr().out


def test_repl_prompts_for_missing_key(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("python_claw_agent.apikey.validate_api_key", lambda key, **_: None)
    monkeypatch.setattr("python_claw_agent.apikey.read_secret", lambda prompt="": "sk-from-prompt")
    monkeypatch.setattr("builtins.input", lambda _: "/exit")
    code = main(["--dir", str(tmp_path), "--session", "need_key"])
    assert code == 0
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-from-prompt" in env_text
    out = capsys.readouterr().out
    assert "DeepSeek/deepseek-chat" in out
    assert "sk-from-prompt" not in out


def test_repl_startup_key_cancel(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("python_claw_agent.apikey.read_secret", lambda prompt="": "")
    code = main(["--dir", str(tmp_path), "--session", "cancel_key"])
    assert code == 1
    assert "已取消" in capsys.readouterr().out


def test_repl_key_command_swaps_provider(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("python_claw_agent.apikey.validate_api_key", lambda key, **_: None)
    monkeypatch.setattr("python_claw_agent.apikey.read_secret", lambda prompt="": "sk-rotated")
    lines = iter(["/key", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "swap_key"])
    assert code == 0
    out = capsys.readouterr().out
    assert "已切换 Provider: DeepSeek/deepseek-chat" in out
    assert "sk-rotated" not in out
    assert "DEEPSEEK_API_KEY=sk-rotated" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_repl_key_cancel_keeps_going(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("python_claw_agent.apikey.read_secret", lambda prompt="": "")
    lines = iter(["/key", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "key_cancel"])
    assert code == 0
    out = capsys.readouterr().out
    assert "已取消更换密钥" in out
    assert not (tmp_path / ".env").exists()


def test_repl_help_lists_key(tmp_path, monkeypatch, capsys) -> None:
    lines = iter(["/help", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "help_key"])
    assert code == 0
    out = capsys.readouterr().out
    assert "/key" in out
    assert "/turns" in out
    assert "/compact" in out


def test_repl_compact_command(tmp_path, monkeypatch, capsys) -> None:
    mgr = SessionManager()
    sess = mgr.get_or_create("repl_compact", str(tmp_path))
    blob = [Message(role=ROLE_USER, content="记住苹果")]
    for i in range(16):
        blob.append(Message(role=ROLE_ASSISTANT, content="think " + "y" * 300))
        blob.append(Message(role=ROLE_USER, content="Z" * 500, tool_call_id=f"t{i}"))
    blob.append(Message(role=ROLE_ASSISTANT, content="ok"))
    sess.append(*blob)
    lines = iter(["/compact", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_compact"])
    assert code == 0
    out = capsys.readouterr().out
    assert "已折叠" in out
    global_session_mgr.clear_cache()
    loaded = global_session_mgr.get_or_create("repl_compact", str(tmp_path))
    assert any(m.content == "记住苹果" for m in loaded.history)
    assert any("早期的工具输出" in m.content for m in loaded.history)


def test_cli_warns_large_session(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("python_claw_agent.cli.SESSION_WARN_BYTES", 80)
    sess = Session(id="fat_warn", work_dir=str(tmp_path), persist=True)
    sess.append(Message(role=ROLE_USER, content="x" * 200))
    monkeypatch.setattr("builtins.input", lambda _: "/exit")
    code = main(["--dir", str(tmp_path), "--mock", "--session", "fat_warn"])
    assert code == 0
    out = capsys.readouterr().out
    assert "偏大" in out
    assert "/compact" in out


def test_repl_turns_command(tmp_path, monkeypatch, capsys) -> None:
    lines = iter(["/turns", "/turns 40", "/turns xyz", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    code = main(["--dir", str(tmp_path), "--mock", "--session", "repl_turns"])
    assert code == 0
    out = capsys.readouterr().out
    assert "当前上限 20" in out
    assert "上限已设为 40" in out
    assert "用法" in out



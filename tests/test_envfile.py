from pathlib import Path
import os

from python_claw_agent.envfile import load_env_file, load_dotenv


def test_load_env_sets_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CLAW_TEST_MISSING", raising=False)
    (tmp_path / ".env").write_text('CLAW_TEST_MISSING="from-file"\n', encoding="utf-8")
    load_env_file(tmp_path / ".env")
    assert os.environ["CLAW_TEST_MISSING"] == "from-file"


def test_load_env_does_not_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAW_TEST_KEEP", "already")
    (tmp_path / ".env").write_text("CLAW_TEST_KEEP=from-file\n", encoding="utf-8")
    load_env_file(tmp_path / ".env")
    assert os.environ["CLAW_TEST_KEEP"] == "already"


def test_load_dotenv_reads_workdir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CLAW_TEST_WORK", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("CLAW_TEST_WORK=workspace\n# comment\nexport CLAW_TEST_EXPORT=ok\n")
    monkeypatch.delenv("CLAW_TEST_EXPORT", raising=False)
    load_dotenv(tmp_path)
    assert os.environ["CLAW_TEST_WORK"] == "workspace"
    assert os.environ["CLAW_TEST_EXPORT"] == "ok"


def test_upsert_env_creates_and_replaces(tmp_path: Path, monkeypatch) -> None:
    from python_claw_agent.envfile import upsert_env_value

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("FOO=1\nDEEPSEEK_API_KEY=old\nBAR=2\n", encoding="utf-8")
    upsert_env_value(path, "DEEPSEEK_API_KEY", "new-secret")
    text = path.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=new-secret" in text
    assert "DEEPSEEK_API_KEY=old" not in text
    assert "FOO=1" in text
    assert "BAR=2" in text
    assert os.environ["DEEPSEEK_API_KEY"] == "new-secret"

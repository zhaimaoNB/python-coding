import pytest

from python_claw_agent.context import skill as skill_mod


@pytest.fixture(autouse=True)
def isolate_user_skills(tmp_path, monkeypatch):
    """Keep tests from picking up whatever is in the developer's ~/.claw/skills."""
    monkeypatch.setattr(skill_mod, "user_skills_dir", lambda: tmp_path / ".claw-user-skills-isolated")

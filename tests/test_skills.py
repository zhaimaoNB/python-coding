from pathlib import Path

from python_claw_agent.context.composer import PromptComposer
from python_claw_agent.context.session import Session
from python_claw_agent.context.skill import Skill, SkillLoader, parse_skill_md, skill_matches
from python_claw_agent.engine.loop import AgentEngine, _latest_user_task
from python_claw_agent.provider.mock import ScriptedProvider
from python_claw_agent.schema import ROLE_ASSISTANT, ROLE_USER, Message
from python_claw_agent.tools.registry import Registry


def _write_skill(root: Path, name: str, description: str, triggers: str, body: str) -> None:
    folder = root / ".claw" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\ntriggers: {triggers}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_parse_skill_frontmatter() -> None:
    skill = parse_skill_md(
        "---\nname: git-commit\ndescription: 提交代码\ntriggers: 提交, commit, 'git commit'\n---\n\n# body\n"
    )
    assert skill.name == "git-commit"
    assert skill.description == "提交代码"
    assert skill.triggers == ["提交", "commit", "git commit"]
    assert skill.body == "# body"


def test_skill_matches_triggers_and_name() -> None:
    skill = Skill(name="git-commit", description="提交代码", body="SOP", triggers=["提交", "commit", "git status"])
    assert skill_matches(skill, "帮我提交这次改动")
    assert skill_matches(skill, "please commit the fix")
    assert skill_matches(skill, "use git-commit please")
    assert skill_matches(skill, "git  status")
    assert not skill_matches(skill, "read the commitment docs")
    assert not skill_matches(skill, "读一下 hello.txt")
    assert not skill_matches(skill, "")


def test_skill_matches_chinese_aliases() -> None:
    git = Skill(
        name="git-commit",
        description="提交代码",
        body="SOP",
        triggers=["提交", "git status", "git状态", "git 状态"],
    )
    assert skill_matches(git, "查看当前git状态")
    assert skill_matches(git, "查看当前 git 状态")
    assert not skill_matches(git, "查看当前git 版本")
    assert not skill_matches(git, "你是什么模型")

    pytest_skill = Skill(
        name="pytest-fix",
        description="修测试",
        body="SOP",
        triggers=["pytest", "测试挂了", "测试报错"],
    )
    assert skill_matches(pytest_skill, "测试挂了帮我看")
    assert skill_matches(pytest_skill, "测试报错了")
    assert not skill_matches(pytest_skill, "读一下 hello.txt")


def test_loader_catalog_without_bodies(tmp_path: Path) -> None:
    _write_skill(tmp_path, "git-commit", "提交代码", "提交, commit", "GIT_BODY_SECRET")
    _write_skill(tmp_path, "pytest-fix", "修测试", "pytest, 测试失败", "PYTEST_BODY_SECRET")
    loader = SkillLoader(str(tmp_path))
    catalog = loader.catalog_text()
    assert "git-commit" in catalog
    assert "pytest-fix" in catalog
    assert "GIT_BODY_SECRET" not in catalog
    assert "PYTEST_BODY_SECRET" not in catalog
    assert loader.loaded_text("读 hello.txt") == ""


def test_select_loads_only_matching_skill(tmp_path: Path) -> None:
    _write_skill(tmp_path, "git-commit", "提交代码", "提交, commit", "GIT_BODY_SECRET")
    _write_skill(tmp_path, "pytest-fix", "修测试", "pytest, 测试失败", "PYTEST_BODY_SECRET")
    loader = SkillLoader(str(tmp_path))
    git_loaded = loader.loaded_text("帮我提交这些改动")
    assert "GIT_BODY_SECRET" in git_loaded
    assert "PYTEST_BODY_SECRET" not in git_loaded
    pytest_loaded = loader.loaded_text("pytest 失败了，帮我看断言")
    assert "PYTEST_BODY_SECRET" in pytest_loaded
    assert "GIT_BODY_SECRET" not in pytest_loaded


def test_composer_on_demand_skills(tmp_path: Path) -> None:
    _write_skill(tmp_path, "git-commit", "提交代码", "提交, commit", "GIT_BODY_SECRET")
    _write_skill(tmp_path, "pytest-fix", "修测试", "pytest, 测试失败", "PYTEST_BODY_SECRET")
    idle = PromptComposer(str(tmp_path)).build(task="读取 hello.txt")
    assert "**git-commit**" in idle.content
    assert "**pytest-fix**" in idle.content
    assert "GIT_BODY_SECRET" not in idle.content
    assert "PYTEST_BODY_SECRET" not in idle.content

    commit = PromptComposer(str(tmp_path)).build(task="请帮我 commit")
    assert "GIT_BODY_SECRET" in commit.content
    assert "PYTEST_BODY_SECRET" not in commit.content
    assert "已加载技能: git-commit" in commit.content


def test_engine_uses_latest_user_task_for_skills(tmp_path: Path) -> None:
    _write_skill(tmp_path, "git-commit", "提交代码", "提交, commit", "GIT_BODY_SECRET")
    provider = ScriptedProvider([Message(role=ROLE_ASSISTANT, content="先看 diff 再提交。")])
    session = Session(id="s", work_dir=str(tmp_path))
    session.append(Message(role=ROLE_USER, content="帮我提交这次修改"))
    AgentEngine(provider, Registry()).run(session)
    assert session.history[-1].content == "先看 diff 再提交。"
    assert _latest_user_task(session) == "帮我提交这次修改"


def test_empty_workdir_still_loads_bundled(tmp_path: Path) -> None:
    loader = SkillLoader(str(tmp_path))
    names = {skill.name for skill in loader.list_skills()}
    assert "git-commit" in names
    assert "pytest-fix" in names
    git_loaded = loader.loaded_text("帮我提交这些改动")
    assert "Git 提交流程" in git_loaded
    assert "pytest 修复流程" not in git_loaded
    pytest_loaded = loader.loaded_text("pytest 失败了")
    assert "pytest 修复流程" in pytest_loaded
    assert "Git 提交流程" not in pytest_loaded
    assert loader.loaded_text("读取 hello.txt") == ""
    assert "Git 提交流程" in loader.loaded_text("查看当前git状态")
    assert loader.loaded_text("查看当前git 版本") == ""

    idle = PromptComposer(str(tmp_path)).build(task="读取 hello.txt")
    assert "Agent Skills" in idle.content
    assert "Git 提交流程" not in idle.content
    loaded = PromptComposer(str(tmp_path)).build(task="提交代码")
    assert "已加载技能: git-commit" in loaded.content
    assert "Git 提交流程" in loaded.content


def test_project_skill_overrides_bundled(tmp_path: Path) -> None:
    _write_skill(tmp_path, "git-commit", "项目提交规矩", "提交, commit", "PROJECT_GIT_SOP")
    loader = SkillLoader(str(tmp_path))
    git_skills = [s for s in loader.list_skills() if s.name == "git-commit"]
    assert len(git_skills) == 1
    assert git_skills[0].body == "PROJECT_GIT_SOP"
    assert "PROJECT_GIT_SOP" in loader.loaded_text("帮我提交")
    assert "Git 提交流程" not in loader.loaded_text("帮我提交")


def test_user_skill_overrides_bundled_not_project(tmp_path: Path, monkeypatch) -> None:
    from python_claw_agent.context import skill as skill_mod

    user_root = tmp_path / "user-skills"
    (user_root / "git-commit").mkdir(parents=True)
    (user_root / "git-commit" / "SKILL.md").write_text(
        "---\nname: git-commit\ndescription: 用户提交规矩\ntriggers: 提交\n---\n\nUSER_GIT_SOP\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(skill_mod, "user_skills_dir", lambda: user_root)

    empty_proj = tmp_path / "empty-proj"
    empty_proj.mkdir()
    loader = SkillLoader(str(empty_proj))
    assert "USER_GIT_SOP" in loader.loaded_text("帮我提交")
    assert "Git 提交流程" not in loader.loaded_text("帮我提交")

    proj = tmp_path / "proj"
    proj.mkdir()
    _write_skill(proj, "git-commit", "项目提交规矩", "提交", "PROJECT_GIT_SOP")
    project_loader = SkillLoader(str(proj))
    assert "PROJECT_GIT_SOP" in project_loader.loaded_text("帮我提交")
    assert "USER_GIT_SOP" not in project_loader.loaded_text("帮我提交")

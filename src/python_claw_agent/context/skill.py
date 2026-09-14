from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
import re
import unicodedata


@dataclass
class Skill:
    name: str
    description: str
    body: str
    triggers: list[str] = field(default_factory=list)
    path: str = ""


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _parse_triggers(raw: str) -> list[str]:
    items: list[str] = []
    for part in raw.split(","):
        item = _unquote(part)
        if item:
            items.append(item)
    return items


def parse_skill_md(content: str, path: str = "") -> Skill:
    skill = Skill(name="Unknown Skill", description="No description provided.", body=content, path=path)
    if content.startswith("---\n") or content.startswith("---\r\n"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            frontmatter = parts[1]
            skill.body = parts[2].strip()
            for line in frontmatter.splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    skill.name = _unquote(line[len("name:") :]) or skill.name
                elif line.startswith("description:"):
                    skill.description = _unquote(line[len("description:") :]) or skill.description
                elif line.startswith("triggers:"):
                    skill.triggers = _parse_triggers(line[len("triggers:") :])
    return skill


_LATIN_TRIGGER = re.compile(r"^[a-z0-9]+(?:[\s\-][a-z0-9]+)*$")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u3000", " ")
    return " ".join(text.casefold().split())


def _compact(text: str) -> str:
    return re.sub(r"[\s\-_]+", "", _normalize(text))


def _iter_needles(skill: Skill) -> list[str]:
    raw = list(skill.triggers)
    name = (skill.name or "").strip()
    if name and name != "Unknown Skill":
        raw.append(name)
        raw.append(name.replace("-", " "))
        raw.append(name.replace("_", " "))
    seen: set[str] = set()
    needles: list[str] = []
    for item in raw:
        for variant in (item, item.replace("-", " "), item.replace("_", " ")):
            variant = variant.strip()
            if len(variant) < 2:
                continue
            key = variant.casefold()
            if key in seen:
                continue
            seen.add(key)
            needles.append(variant)
    return needles


def skill_matches(skill: Skill, task: str) -> bool:
    hay = _normalize(task)
    if not hay:
        return False
    hay_compact = _compact(task)
    for needle in _iter_needles(skill):
        n = _normalize(needle)
        if len(n) < 2:
            continue
        if _LATIN_TRIGGER.fullmatch(n):
            if re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", hay):
                return True
            if (" " in n or "-" in n) and _compact(n) in hay_compact:
                return True
            continue
        if n in hay or _compact(n) in hay_compact:
            return True
    return False


def bundled_skills_dir() -> Path:
    try:
        root = files("python_claw_agent.skills")
        return Path(str(root))
    except (ModuleNotFoundError, TypeError, OSError):
        return Path(__file__).resolve().parent.parent / "skills"


def user_skills_dir() -> Path:
    return Path.home() / ".claw" / "skills"


def project_skills_dir(work_dir: str | Path) -> Path:
    return Path(work_dir).resolve() / ".claw" / "skills"


def default_skill_roots(work_dir: str | Path) -> list[Path]:
    """Bundled, then user-global, then project. Later roots override the same name."""
    return [bundled_skills_dir(), user_skills_dir(), project_skills_dir(work_dir)]


def _load_from_dir(folder: Path) -> dict[str, Skill]:
    found: dict[str, Skill] = {}
    if not folder.is_dir():
        return found
    for path in sorted(folder.rglob("SKILL.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        skill = parse_skill_md(text, path=str(path))
        key = skill.name.strip() or path.parent.name
        found[key] = skill
    return found


class SkillLoader:
    def __init__(self, work_dir: str, roots: list[Path] | None = None) -> None:
        self.work_dir = work_dir
        self.roots = list(roots) if roots is not None else default_skill_roots(work_dir)

    def list_skills(self) -> list[Skill]:
        merged: dict[str, Skill] = {}
        for root in self.roots:
            merged.update(_load_from_dir(root))
        return sorted(merged.values(), key=lambda skill: skill.name.casefold())

    def select(self, task: str) -> list[Skill]:
        return [skill for skill in self.list_skills() if skill_matches(skill, task)]

    def catalog_text(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = [
            "\n### 可用专业技能 (Agent Skills)\n",
            "下面是技能目录（名称与触发说明）。只有与当前任务匹配的技能会加载正文；未加载的不要假装已经执行。\n\n",
        ]
        for skill in skills:
            lines.append(f"- **{skill.name}**：{skill.description}\n")
        return "".join(lines)

    def format_loaded(self, selected: list[Skill]) -> str:
        if not selected:
            return ""
        parts: list[str] = []
        for skill in selected:
            parts.append(f"\n### 已加载技能: {skill.name}\n\n")
            parts.append(skill.body)
            parts.append("\n")
        return "".join(parts)

    def loaded_text(self, task: str) -> str:
        return self.format_loaded(self.select(task))

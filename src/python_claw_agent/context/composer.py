from __future__ import annotations

from pathlib import Path

from python_claw_agent.context.skill import SkillLoader
from python_claw_agent.observability.log import vprint
from python_claw_agent.schema import ROLE_SYSTEM, Message

CORE_PROMPT = """# 核心身份
你名叫 coding，一个绑定当前工作区的本地研发助手。
你具备极简主义哲学，拒绝废话。你能通过系统提供的内置工具，创建、读取、修改和执行工作区中的代码。

# 核心纪律 (CRITICAL)
1. 如需列出目录或确认文件是否存在，请使用 list_dir，不要对目录使用 read_file。搜索文件内容请使用 grep，不要用 bash 的 findstr / Select-String / grep。bash 仅用于运行程序，不得使用 '..'、~ 或工作区外的绝对路径。
2. 创建新文件时，务必使用 write_file，并同时提供 path 和 content 参数。
3. 编辑文件前务必先读取现有文件，以理解上下文。
4. 无论何时你需要写代码或创建文件，都要直接使用 write_file 工具。
5. 遇到工具执行报错时，仔细阅读 stderr，尝试自己修正命令并重试。
6. 始终用中文回复，以便传达你的进展和想法。
"""

PLAN_MODE_PROMPT = """
# Plan Mode: ON（只读规划）

系统已经锁住写操作。你现在只能：
- 使用 list_dir / read_file / grep 了解代码
- 使用 write_file / edit_file 更新工作区根目录的 PLAN.md 和 TODO.md

禁止：修改任何其它文件、运行 bash、动手改业务代码。就算你调用这些工具，系统也会拦截。

你必须按这个顺序工作：
1. 用只读工具摸清现状（用 list_dir 看根目录有没有 PLAN.md / TODO.md，不要用 bash）。
2. 把方案写入 PLAN.md：目标、改动范围、步骤、风险。
3. 把待办写入 TODO.md（Markdown checkbox，如 `- [ ] 步骤1`）。若文件已存在，先 read_file，不要无故清空。
4. 用中文向用户陈述方案，并明确告诉他们：输入 `/plan off` 批准后，你才会开始改代码。

不要假装已经改完。不要对业务代码调用 write_file / edit_file / bash。
"""


class PromptComposer:
    def __init__(self, work_dir: str, plan_mode: bool = False) -> None:
        self.work_dir = work_dir
        self.plan_mode = plan_mode
        self.skill_loader = SkillLoader(work_dir)

    def build(self, task: str = "") -> Message:
        chunks = [CORE_PROMPT]
        if self.plan_mode:
            chunks.append(PLAN_MODE_PROMPT)
        agents_path = Path(self.work_dir) / "AGENTS.md"
        if agents_path.is_file():
            chunks.append("\n# 项目专属指南 (来自 AGENTS.md)\n```markdown\n")
            chunks.append(agents_path.read_text(encoding="utf-8"))
            chunks.append("\n```\n")
        catalog = self.skill_loader.catalog_text()
        if catalog:
            chunks.append(catalog)
        selected = self.skill_loader.select(task)
        if selected:
            vprint("[Skill] 已加载: " + ", ".join(skill.name for skill in selected))
            chunks.append(self.skill_loader.format_loaded(selected))
        return Message(role=ROLE_SYSTEM, content="".join(chunks))

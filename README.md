# python-coding

本地编码助手 Harness。进一个目录敲 `coding`，当前目录就是工作区。

把大模型当成 CPU，把对话历史当成内存，用一层薄运行时去调度工具、压缩上下文、拦住越界路径。不依赖 LangChain。

## 能力

- ReAct 主循环：Think / Act / Observe
- 工具：`read_file` / `write_file` / `edit_file` / `bash` / `list_dir` / `grep`，以及只读 `spawn_subagent`
- 会话写入 `.claw/sessions/`，关窗口可续聊；`/compact` 折叠早期工具输出
- `AGENTS.md` 是项目规矩；Skills 按需加载（包内置 → `~/.claw/skills/` → 工作区 `.claw/skills/`）
- Plan Mode 只读锁、写操作确认、路径 jail、轮次上限
- DeepSeek（OpenAI 兼容协议）、费用统计、本地 JSON Trace

## 环境

- Python 3.11+
- 真实推理需要 [DeepSeek API Key](https://platform.deepseek.com/)

## 安装

在仓库根目录下：

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

pip install -e ".[dev]"
```

## 测试

```bash
pytest -q
```

测试全部走 Mock Provider，**不需要** API Key。

## 启动

```bash
cd C:\你的项目
coding
```

也可以：`python -m python_claw_agent`。短命令 `coding` 需要已执行过 `pip install -e .`。

提示符是 `you>`。斜杠命令：`/help` `/cost` `/clear` `/compact` `/key` `/plan` `/yes` `/turns` `/verbose` `/exit`。要用别的目录时再加 `--dir`。

默认是普通对话。大改之前可加 `--plan` 或敲 `/plan`：此时只能读代码并写 `PLAN.md` / `TODO.md`，`/plan off` 之后才允许改文件。

写文件、`edit_file`、`bash` 默认会先问。预览是路径和内容摘要；同一轮多个写操作只问一次（`y` 全过 / `n` 全拒）。想少打断可加 `--yes`，或对话里 `/yes`。

密钥写在工作区 `.env`（不会覆盖已经存在的环境变量）：

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

交互启动时如果还没有密钥，会提示隐藏输入；校验通过后写入工作区 `.env`。REPL 里可用 `/key` 更换。一次性任务（`--prompt`）不会交互问密钥，请事先配好环境变量 / `.env`，或加 `--mock`。

默认少打内部日志；需要 Tracker / Trace 时加 `--verbose` 或 `/verbose`。助手正文会边生成边打印；出现工具调用时停住流式，再走确认与执行。

一次性任务：

```bash
cd workspace
python -m python_claw_agent --prompt "读取 hello.txt 并总结" --mock
```

## 参数

| 参数 | 含义 |
|------|------|
| `--prompt` | 一次性任务；省略则进入多轮对话 |
| `--dir` | 工作区，默认当前目录 |
| `--session` | 会话 ID |
| `--model` | 默认 `deepseek-chat` |
| `--mock` | 强制 Mock |
| `--thinking` | 每轮先不带工具推理一次 |
| `--plan` | 开启只读 Plan Mode |
| `--yes` | 写文件/bash 不询问 |
| `--max-turns` | 每条消息工具往返上限，默认 20 |
| `--verbose` | 打印 Tracker、Registry、Trace 等详细日志 |

## 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek 密钥（也可写在工作区 `.env`） |
| `DEEPSEEK_BASE_URL` | 可选，默认 `https://api.deepseek.com` |

## Skills

系统提示只带技能目录（名字 + description）。当前用户任务命中 `triggers` 或技能名时，才加载对应 `SKILL.md` 正文。

查找顺序：包内置 → `%USERPROFILE%\.claw\skills\`（或 `~/.claw/skills/`）→ 工作区 `.claw/skills/`，同名后者覆盖。内置 `git-commit`、`pytest-fix`。新技能格式：

```yaml
---
name: your-skill
description: 一句话说明何时用
triggers: 关键词1, 关键词2
---
正文 SOP
```

## 目录结构

```
python-coding/
  src/python_claw_agent/
    schema.py
    cli.py
    engine/          # 主循环、权限、Reminder
    provider/        # DeepSeek + Mock
    tools/           # 文件、bash、grep、subagent
    context/         # Session、Composer、Compactor、Skills
    observability/   # Cost、Trace
    skills/          # 内置 git-commit / pytest-fix
  tests/
  workspace/         # 可选演示区
```

## 边界

- 上下文压缩按字符数（约 4 万字符触发）；会话文件超过约 256KB 时启动会提示 `/compact` 或 `/clear`
- Trace 写在 `.claw/traces/`，只保留最近 20 份
- Windows 无 Git Bash 时，`bash` 走 PowerShell
- bash 工作区限制是启发式拦截（`..` / `~` / 区外绝对路径），不是完整沙箱
- 无 MCP

# python-coding

本地编码助手。进入你的项目目录，敲 `coding`，它就能读文件、改代码、跑命令。

用的是 DeepSeek。对话会记在当前项目里，关掉窗口下次还能接着聊。

## 需要什么

- Python 3.11 或更高
- Git
- [DeepSeek API Key](https://platform.deepseek.com/)（真要让模型干活时才需要；跑测试不用）

## 安装

### 1. 从 GitHub 拉取

```bash
git clone https://github.com/zhaimaoNB/python-coding.git
cd python-coding
```

### 2. 建虚拟环境并安装

**Windows（CMD）：**

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

装好后，当前窗口里可以直接用 `coding` 命令。

**Windows（PowerShell）：**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

如果提示无法加载脚本，先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**macOS / Linux：**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

想一起装测试依赖，把最后一步改成：

```bash
pip install -e ".[dev]"
```

> 以后每次用，先进入 `python-coding` 目录，再激活 `.venv`。没激活的话，系统可能找不到 `coding` 命令。

### 3. 配置密钥

在**你要改的那个项目目录**里建 `.env`（不是必须放在本仓库里）：

```
DEEPSEEK_API_KEY=sk-你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

也可以启动后按提示输入，校验通过会自动写入该目录的 `.env`。对话里用 `/key` 可以更换。

## 使用

`coding` 把**当前目录**当成工作区。先 `cd` 到你的项目，再启动。

```bat
cd C:\你的项目
coding
```

出现 `you>` 后，直接输入任务，例如：`帮我看看这个项目怎么启动`。

也可以：

```bash
python -m python_claw_agent
```

指定别的目录：

```bash
coding --dir C:\你的项目
```

一次性任务（跑完就退出）：

```bash
coding --prompt "读取 README.md 并总结"
```

不调用真实 API、只走模拟（适合试命令）：

```bash
coding --prompt "读取 hello.txt" --mock
```

## 常用操作

| 你想做的事 | 怎么做 |
|---|---|
| 查看命令 | `/help` |
| 先规划、先不改代码 | 启动加 `--plan`，或对话里 `/plan` |
| 批准开始改代码 | `/plan off` |
| 写文件 / 跑命令不要每次问 | 启动加 `--yes`，或对话里 `/yes` |
| 改密钥 | `/key` |
| 压缩过长的历史 | `/compact` |
| 清空会话 | `/clear` |
| 看费用 | `/cost` |
| 退出 | `/exit` 或 `Ctrl+C` |

默认改文件、跑命令前会问你一声：`y` 同意，`n` 拒绝。同一轮多个写操作只问一次。

大改之前建议先 `/plan`：这时只能读代码，并写 `PLAN.md` / `TODO.md`。看完方案再 `/plan off`。

## 测试（可选）

```bash
pip install -e ".[dev]"
pytest -q
```

测试全部走模拟接口，**不需要** API Key。

## 它能做什么

- 读、写、改文件，列目录，搜索代码，执行命令
- 会话保存在项目下的 `.claw/sessions/`，关掉还能续
- 项目根目录的 `AGENTS.md` 会当成这个项目的规矩
- 技能按需加载：包内置 → 用户目录 `~/.claw/skills/`（Windows 是 `%USERPROFILE%\.claw\skills\`）→ 当前项目 `.claw/skills/`
- 有路径限制：默认不能改工作区外面的文件

## 参数和环境变量

| 参数 | 含义 |
|------|------|
| `--prompt` | 一次性任务；不写则进入多轮对话 |
| `--dir` | 工作区，默认当前目录 |
| `--session` | 会话 ID |
| `--model` | 默认 `deepseek-chat` |
| `--mock` | 不调用真实 API |
| `--plan` | 只读规划模式 |
| `--yes` | 写文件 / 跑命令不再询问 |
| `--max-turns` | 每条消息工具往返上限，默认 20 |
| `--verbose` | 打印更详细的内部日志 |

| 环境变量 | 说明 |
|----------|------|
| `DEEPSEEK_API_KEY` | DeepSeek 密钥 |
| `DEEPSEEK_BASE_URL` | 可选，默认 `https://api.deepseek.com` |

已经存在的环境变量，不会被 `.env` 覆盖。

## 注意

- Windows 如果没有 Git Bash，命令会走 PowerShell
- 工作区限制是启发式的，不是完整沙箱
- 会话太长时，启动会提示你 `/compact` 或 `/clear`
- 目前没有 MCP

## 联系作者

技术交流或商务合作，可加作者微信：`fengyu3650`

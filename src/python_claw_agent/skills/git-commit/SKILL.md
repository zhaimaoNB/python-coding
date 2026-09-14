---
name: git-commit
description: 提交代码、写 commit message、整理暂存区或执行 git commit 时使用。
triggers: 提交, commit, git commit, 暂存, 提交说明, git status, git状态, git 状态, 仓库状态, 暂存区, 提交代码, 写提交, commit message, 提交信息, git diff, git log
---

# Git 提交流程

1. 先用 bash 跑 `git status`，再看 `git diff` 和 `git log -5`，弄清改了什么、最近的说明怎么写。
2. 只暂存与这次任务相关的文件，不要无脑 `git add .`。有拿不准的文件先问用户。
3. 提交说明写清「为什么」，用 `feat` / `fix` / `docs` / `test` / `refactor` 这类前缀加一句要点。禁止 `git commit -am "update"`、`git commit -m "fix"` 这种空说明。
4. Windows PowerShell 下用单引号包说明，例如：`git commit -m 'fix: 纠正 compact 后会话未写盘'`。
5. 用户没明确说 push，就只 commit。禁止 `git push --force`、禁止改 git config、禁止 amend 已经推送的提交。
6. 不要提交 `.env`、密钥、`.claw/sessions/`、`.claw/traces/`。

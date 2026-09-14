from __future__ import annotations


class RecoveryManager:
    def analyze_and_inject(self, tool_name: str, raw_error: str) -> str:
        hint = ""
        lower = raw_error.lower()

        if "用户拒绝" in raw_error or "Plan Mode" in raw_error:
            if "Plan Mode" in raw_error:
                return (
                    f"{raw_error}\n\n[系统救援指南]: "
                    "现在是只读规划。继续用 list_dir / read_file / grep 收集信息，"
                    "把方案写入 PLAN.md / TODO.md，然后请用户输入 /plan off。"
                )
            return (
                f"{raw_error}\n\n[系统救援指南]: "
                "用户没有批准这次操作。请向用户说明你想做什么，等待新的指示，不要用相同参数立刻重试。"
            )

        if tool_name == "edit_file":
            if "在文件中未找到 old_text" in raw_error or "找不到该代码片段" in raw_error:
                hint = "你提供的 old_text 与文件当前内容不一致，或者缺少必要的缩进。请先使用 `read_file` 工具重新读取该文件。"
            elif "匹配到了多处" in raw_error or "提供更多上下文" in raw_error:
                hint = "你的 old_text 不够具体，命中了多个相同代码块。请在 old_text 中增加上下相邻的几行代码。"
        elif tool_name in ("read_file", "write_file", "list_dir", "grep"):
            if (
                "no such file" in lower
                or "cannot find the file" in lower
                or "系统找不到" in raw_error
                or "打开文件失败" in raw_error
                or "目录不存在" in raw_error
                or "路径不存在" in raw_error
            ):
                hint = "路径似乎不正确。请不要凭空猜测，先使用 `list_dir` 查找正确的文件名。"
            elif "permission denied" in lower or "路径越界" in raw_error:
                hint = "你没有权限操作该路径。请检查工作区限制，不要使用 .. 逃出工作区。"
            elif tool_name == "grep" and "无效正则" in raw_error:
                hint = "pattern 不是合法正则。普通关键字无需转义；若要搜特殊字符，请先转义。"
        elif tool_name == "bash":
            if "路径越界" in raw_error:
                hint = "shell 被限制在工作区内。请改用相对路径，或使用 list_dir / read_file / grep。"
            elif "command not found" in lower or "不是内部或外部命令" in raw_error:
                hint = "系统中未安装该命令。请先思考是否有替代命令。"
            elif "超时" in raw_error or "timeout" in lower:
                hint = "该命令执行被超时强杀。如果它是常驻服务，请转入后台执行，不要阻塞主循环。"
            elif "syntax error" in lower:
                hint = "Shell 语法错误。请检查引号转义或特殊字符。"

        if not hint:
            return raw_error
        return f"{raw_error}\n\n[系统救援指南]: {hint}"

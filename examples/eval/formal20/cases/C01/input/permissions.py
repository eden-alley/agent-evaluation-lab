"""permissions.py —— 第 3 课：权限与安全边界"""
from __future__ import annotations

import os
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from textwrap import indent
from urllib.parse import urlsplit


class Workspace:
    """文件工具与权限检查共用的路径边界。"""
    def __init__(self, root):
        self.root = Path(root).resolve()

    def resolve(self, path_str):
        path = Path(path_str).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        return path if path.is_relative_to(self.root) else None


class Risk(Enum):
    SAFE = "safe"        # 只读：直接放行
    CONFIRM = "confirm"  # 有副作用：问人
    DENY = "deny"        # 永远不允许


# 工具风险登记表。没登记的工具一律按 CONFIRM 处理。
TOOL_RISK = {
    "list_dir": Risk.SAFE,
    "read_file": Risk.SAFE,
    "write_file": Risk.CONFIRM,
    "run_shell": Risk.CONFIRM,
    "fetch_url": Risk.CONFIRM,
}

# 人工确认模式允许"本次会话一直允许"的工具。run_shell 在此模式下仍逐条确认。
REMEMBERABLE = {"write_file"}

# 明显的灾难性命令。注意：这是安全带，不是边界（见文章第八节）。
SHELL_DENY_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(/|~|\*)",  # rm -rf / ~ *
    r"\bsudo\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\s*\{",                                    # fork bomb
    r"(curl|wget)\b.*\|\s*(sh|bash)\b",               # curl ... | sh
    r">\s*/dev/sd",
]


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    code: str = ""


def fetch_url_denial(url):
    """只限制 URL 协议和基本格式；不改变宿主的公网、内网和代理可达范围。"""
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            return "网页工具仅允许具有主机名的 HTTP/HTTPS URL。"
        parsed.port  # 由标准解析器拒绝非法端口格式。
    except (TypeError, ValueError):
        return "网页 URL 格式不合法。"
    return None


def render_call(name: str, args: dict, max_chars: int = 400) -> str:
    """确认界面：展示将要执行的真实内容，而不是模型的自述。"""
    if name == "run_shell":
        return f"  $ {args.get('command', '')}"
    if name == "write_file":
        content = args.get("content", "")
        preview = content[:max_chars]
        if len(content) > max_chars:
            preview += f"\n...（已截断，共 {len(content)} 字符）"
        return f"  路径：{args.get('path')}\n" + indent(preview, "    ")
    return f"  {args}"


class PermissionManager:
    def __init__(self, ask=None, *, workspace=None, mcp_read_only=()):
        if workspace is None:
            workspace = os.environ.get("NAMI_WORKSPACE", os.getcwd())
        self.workspace = (workspace if isinstance(workspace, Workspace)
                          else Workspace(workspace))
        self.always_allowed: set[str] = set()
        self.auto_approve = False
        self.mcp_read_only = frozenset(mcp_read_only)
        # ask 可注入：ask(name, args) -> ("y" | "n" | "a", 拒绝原因)
        # 第 3 课用它方便测试，第 6、7 课会换成聊天确认和无人值守的预授权
        self.ask = ask or self._ask_terminal

    # ---------- 对外入口 ----------
    def set_auto_approve(self, enabled: bool):
        self.auto_approve = enabled
        self.always_allowed.clear()   # 切回人工模式时不沿用旧的「一直允许」。

    def check(self, name: str, args: dict) -> Decision:
        # 第 1 关：硬规则，人也无法放行
        reason = self._hard_limits(name, args)
        if reason:
            return Decision(False, reason, "policy_denied")

        # 第 2 关：风险分级
        default_risk = Risk.SAFE if name.startswith("mcp__") and name in self.mcp_read_only else Risk.CONFIRM
        risk = TOOL_RISK.get(name, default_risk)
        if risk is Risk.DENY:
            return Decision(False, f"工具 {name} 被策略禁用。", "policy_denied")
        if risk is Risk.SAFE or name in self.always_allowed:
            return Decision(True)
        if self.auto_approve and name in TOOL_RISK:
            return Decision(True)   # 只跳过已登记工具的确认，不跳过硬规则或 DENY。

        # 第 3 关：人工确认
        return self._confirm(name, args)

    # ---------- 第 1 关 ----------
    def _hard_limits(self, name: str, args: dict) -> str | None:
        if name == "fetch_url":
            return fetch_url_denial(args.get("url", ""))
        if name in ("read_file", "write_file", "list_dir"):
            path = args.get("path", ".")
            if self.workspace.resolve(path) is None:
                return f"路径 {path!r} 在工作区 {self.workspace.root} 之外，禁止访问。"
        if name == "run_shell":
            cmd = args.get("command", "")
            for pat in SHELL_DENY_PATTERNS:
                if re.search(pat, cmd):
                    return f"命令命中危险模式，已被策略拦截：{cmd!r}"
        return None

    # ---------- 第 3 关 ----------
    def _confirm(self, name: str, args: dict) -> Decision:
        approval_args = deepcopy(args)
        response = self.ask(name, approval_args)
        if approval_args != args:
            return Decision(False, "权限确认组件修改了工具参数，未执行操作且未保存授权。", "execution_error")
        if isinstance(response, Decision):
            return response
        answer, note = response
        if answer == "a" and name in REMEMBERABLE:
            self.always_allowed.add(name)
            return Decision(True)
        if answer in ("y", "a"):
            return Decision(True)
        msg = "用户拒绝了这次操作。"
        if note:
            msg += f"原因：{note}。"
        msg += "不要重试同一操作；请换一种方式，或向用户说明你想做什么、为什么。"
        return Decision(False, msg, "user_denied")

    @staticmethod
    def _ask_terminal(name: str, args: dict):
        if not sys.stdin.isatty():
            # 非交互环境（管道、脚本）没有人可以确认，默认拒绝
            return Decision(False, "当前是非交互环境，无法确认", "confirmation_unavailable")
        print(f"\n[权限确认] Agent 想执行：{name}")
        print(render_call(name, args))
        options = "[y]允许 / [n]拒绝" + (" / [a]本次会话一直允许" if name in REMEMBERABLE else "")
        while True:
            ans = input(f"{options} > ").strip().lower()
            if ans in ("y", "n") or (ans == "a" and name in REMEMBERABLE):
                break
        note = input("拒绝原因（可选，回车跳过）> ").strip() if ans == "n" else ""
        return ans, note

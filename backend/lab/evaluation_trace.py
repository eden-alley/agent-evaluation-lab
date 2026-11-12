"""Describe recorded actions without guessing what the model intended."""

import json
import re


PREVIEW_CHARS = 8000
STOP_TEXT = {
    "end_turn": "模型提交了本轮答复。",
    "max_steps": "运行到达步数上限，结束了这一轮。",
    "verification_unmet": "验收未通过，运行结束。",
    "error": "运行因错误结束。",
}


def as_text(value):
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def preview(value):
    text = as_text(value)
    if len(text) <= PREVIEW_CHARS:
        return text
    return text[:6000] + "\n…中段已折叠，完整内容可下载原始轨迹…\n" + text[-2000:]


def tool_arguments(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def shell_action(command):
    lower = command.lower()
    if "unittest" in lower or "pytest" in lower or "run-check.cmd" in lower or "run-tests.cmd" in lower:
        return "从终端运行了测试命令"
    if re.search(r"\b(findstr|rg|select-string)\b", lower):
        return "运行了文本搜索命令"
    if re.search(r"\bget-content\b|\.(read_text|read_bytes|read)\s*\(|(?:^|&&)\s*type\s+", lower):
        return "运行了包含文件读取的命令"
    return "运行了终端命令"


def tool_sentence(call, result=None):
    tool = call.get("tool")
    args = tool_arguments(call.get("arguments"))
    path = as_text(args.get("path", "当前目录"))[:300]
    if tool == "list_dir":
        action = f"尝试查看「{path}」的目录内容"
    elif tool == "read_file":
        action = f"尝试读取「{path}」"
    elif tool == "write_file":
        action = f"尝试写入「{path}」"
    elif tool == "fetch_url":
        action = f"请求了「{as_text(args.get('url'))[:300]}」"
    elif tool == "run_shell":
        action = shell_action(as_text(args.get("command")))
    else:
        action = f"调用了「{as_text(tool) or '工具'}」"
    if result is None:
        return f"{action}，记录里没有这次调用的返回。"

    output = as_text(result.get("data"))
    match = re.search(r"(?m)^Ran (\d+) tests?\b", output) if tool == "run_shell" else None
    if match and re.search(r"(?m)^FAILED\b", output):
        outcome = f"测试输出显示运行了 {match[1]} 项，存在失败"
    elif match and int(match[1]) > 0 and re.search(r"(?m)^OK(?:\s*\(|\s*$)", output) and result.get("ok"):
        outcome = f"{match[1]} 项测试通过"
    elif result.get("ok") is True:
        outcome = {
            "write_file": "工具确认写入成功",
            "read_file": "工具返回了文件内容",
            "list_dir": "工具返回了目录内容",
        }.get(tool, "工具返回成功")
    elif result.get("ok") is False:
        message = as_text(result.get("message") or result.get("error")).strip()
        outcome = f"工具返回失败（{message[:160]}）" if message else "工具返回失败"
    else:
        outcome = "日志未标明结果"

    before, after = call.get("files"), result.get("files")
    edited = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k)) \
        if isinstance(before, dict) and isinstance(after, dict) else []
    if edited:
        names = "、".join(f"「{name[:160]}」" for name in edited[:4])
        suffix = f"等 {len(edited)} 个文件" if len(edited) > 4 else ""
        outcome += f"，文件变化涉及 {names}{suffix}"
    return f"{action}，{outcome}。"


def explain_trace(raw):
    """Build readable cards with stable line IDs, including multi-turn traces."""
    groups = []
    pending = {}
    step = 0
    group = None
    for line_no, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("event must be an object")
        kind = row.get("type")
        phase = row.get("phase", 1)
        event_id = row.get("event_id")
        if kind in ("task_started", "task_resumed", "model_response") or group is None:
            if kind == "model_response":
                step += 1
                heading = f"第 {step} 次模型响应"
            else:
                heading = "从检查点继续执行" if kind == "task_resumed" else f"开始第 {phase} 轮任务"
            group = {"line": line_no, "phase": phase, "heading": heading, "event_ids": [],
                     "actions": [], "outcomes": [], "evidence": []}
            groups.append(group)
        group["event_ids"].append(event_id)
        if kind == "tool_call":
            evidence = {"line": line_no, "label": f"事件 {event_id} · 工具输入", "text": preview(row.get("arguments"))}
            index = len(group["actions"])
            group["actions"].append(tool_sentence(row))
            group["evidence"].append(evidence)
            pending[row.get("call_id")] = (row, group, index, evidence)
        elif kind == "tool_result":
            pair = pending.pop(row.get("call_id"), None)
            result = "\n".join(filter(None, (as_text(row.get("message")), as_text(row.get("error")),
                                             as_text(row.get("data")))))
            evidence = {"line": line_no, "label": f"事件 {event_id} · 工具返回", "text": preview(result)}
            if pair:
                call, owner, index, call_evidence = pair
                owner["actions"][index] = tool_sentence(call, row)
                owner["evidence"].insert(owner["evidence"].index(call_evidence) + 1, evidence)
            else:
                group["outcomes"].append("记录中有工具返回，但没有对应的调用。")
                group["evidence"].append(evidence)
        elif kind in ("task_started", "task_resumed", "verification", "final_response"):
            text = row.get("task") or row.get("reason") or row.get("text")
            if kind == "verification":
                status = {"pass": "通过", "fail": "未通过", "needs_input": "需要补充信息"}.get(row.get("status"), "返回结果")
                group["outcomes"].append(f"验收{status}。")
            if kind == "final_response":
                group["outcomes"].append(STOP_TEXT.get(row.get("stop_reason"), "本轮运行结束。"))
            if text:
                label = {"task_started": "用户任务", "task_resumed": "恢复的任务",
                         "verification": "验收反馈", "final_response": "最终答复"}[kind]
                group["evidence"].append({"line": line_no, "label": f"事件 {event_id} · {label}", "text": preview(text)})
        elif kind not in ("model_response", "assistant_candidate"):
            group["outcomes"].append(f"记录了「{as_text(kind)}」事件。")
    for group in groups:
        group["text"] = "".join(group.pop("actions") + group.pop("outcomes")) or (
            "模型返回了响应，这一步没有记录工具操作。" if group["heading"].startswith("第")
            else f"{group['heading']}。"
        )
    return groups

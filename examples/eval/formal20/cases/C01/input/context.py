"""context.py —— 第 4 课：截断 → 清理 → 摘要，会话持久化"""
import json
import os
from pathlib import Path
import tempfile

MAX_TOOL_CHARS = 4000          # 单个工具结果最多保留的字符数
KEEP_RECENT_TOOL_RESULTS = 3   # 清理时，保留最近几条工具结果
KEEP_LAST_TURNS = 2            # 压缩时，原样保留最近几轮用户对话

PLACEHOLDER = "[旧工具结果已清理，如需要请重新调用工具]"

SUMMARY_PROMPT = """你是对话摘要器。把下面这段 Agent 的历史对话压缩成摘要，要求：
1. 保留：用户的目标、已完成的步骤、关键结论、重要的文件路径和参数、尚未解决的问题
2. 丢弃：寒暄、重复内容、工具返回的大段原文
3. 用简洁的条目写，不要超过 500 字
只输出摘要本身。"""


def render_tool_result(result):
    """只截断模型视图，保持结构合法；原始结果另存执行记录。"""
    payload = result.to_dict()
    if "data" in payload:
        text = (payload["data"] if isinstance(payload["data"], str)
                else json.dumps(payload["data"], ensure_ascii=False))
        if len(text) > 4000:
            original_chars = len(text)
            if len(text) > 8000:
                text = text[:8000] + f"\n...（已截断，共 {original_chars} 字符）"
            payload["data"] = truncate_tool_result(text)
            payload.update(truncated=True, original_chars=original_chars)
    return json.dumps(payload, ensure_ascii=False)


# ---------- 第 1 层：截断工具结果 ----------
def truncate_tool_result(text, limit=MAX_TOOL_CHARS):
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n...[中间省略 {len(text) - limit} 字符]...\n{text[-half:]}"


# ---------- 第 2 层：清理旧的工具结果（只改内容，不删消息） ----------
def clear_old_tool_results(messages, keep=KEEP_RECENT_TOOL_RESULTS):
    tool_idx = [i for i, m in enumerate(messages) if m["role"] == "tool"]
    old = tool_idx[:-keep] if keep > 0 else tool_idx
    for i in old:
        messages[i]["content"] = PLACEHOLDER


# ---------- 第 3 层：摘要压缩（只在 user 消息处切） ----------
def split_for_compact(messages, keep_turns=KEEP_LAST_TURNS):
    """返回 (要被压缩的旧消息, 原样保留的新消息)；没有可压缩的内容返回 None。
    约定 messages[0] 是 system。"""
    user_idx = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if len(user_idx) <= keep_turns:
        return None
    cut = user_idx[-keep_turns]
    return messages[1:cut], messages[cut:]


def render_for_summary(msgs):
    lines = []
    for m in msgs:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = ", ".join(f'{c["function"]["name"]}({c["function"]["arguments"]})'
                              for c in m["tool_calls"])
            if m.get("content"):
                lines.append(f'[assistant] {m["content"]}')
            lines.append(f"[assistant 调用工具] {calls}")
        else:
            lines.append(f'[{m["role"]}] {m.get("content") or ""}')
    return "\n".join(lines)


def compact(model, messages, record_usage, *, before_query=None):
    parts = split_for_compact(messages)
    if parts is None:
        return messages
    old, recent = parts
    if before_query is not None:
        before_query()
    resp = model.query([
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": render_for_summary(old)}])
    record_usage(resp.usage, "摘要")
    summary = resp.require_message().get('content')
    return [messages[0],
            {"role": "user", "content": f"[以下是此前对话的摘要]\n{summary}"},
            {"role": "assistant", "content": "好的，我已了解之前的进展，继续。"},
            *recent]


# ---------- 会话持久化 ----------
def atomic_write_json(path, payload):
    """同目录临时文件刷盘后替换；写失败保留上一份完整 JSON。"""
    path = Path(path)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=f'.{path.name}.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class SessionStore:
    """会话保存位置由实例管理，继续使用原有 JSON 消息列表格式。"""
    def __init__(self, directory=None):
        if directory is None:
            state_dir = Path(os.environ.get("NAMI_STATE_DIR", Path.home() / ".nami-agent"))
            directory = state_dir / "sessions"
        self.directory = Path(directory)

    def save(self, name, messages):
        atomic_write_json(self.directory / f'{name}.json', messages)

    def load(self, name):
        path = self.directory / f"{name}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def append_event(self, name, event):
        """与可压缩上下文分开保存的追加式轨迹，不保存 SDK 客户端或认证头。"""
        self.directory.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(event, ensure_ascii=False) + '\n').encode('utf-8')
        with (self.directory / f'{name}.trace.jsonl').open('a+b') as stream:
            if stream.tell():
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b'\n':
                    stream.write(b'\n')  # 保留硬退出断尾，并给后续事件独立行界。
            stream.write(encoded)

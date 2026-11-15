"""OpenAI Chat Completions 兼容传输；只转换请求和响应。"""
from copy import deepcopy

from .model_base import ModelResponse, ModelUsage


def _usage(raw):
    if not isinstance(raw, dict):
        return None
    counts = {name: value if type(value := raw.get(name)) is int and value >= 0 else None
              for name in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    return ModelUsage(**counts)


def _message(raw, tools_allowed):
    if not isinstance(raw, dict) or raw.get('role') != 'assistant':
        raise ValueError('模型消息必须是 assistant 对象')
    content = raw.get('content')
    if content is not None and not isinstance(content, str):
        raise ValueError('当前模型接口仅支持文本 content')
    calls = raw.get('tool_calls')
    if calls is not None and not isinstance(calls, list):
        raise ValueError('tool_calls 必须是列表')
    canonical = {'role': 'assistant'}
    if content is not None:
        canonical['content'] = content
    if calls:
        if not tools_allowed:
            raise ValueError('当前模型请求不允许调用工具')
        ids, normalized = set(), []
        for call in calls:
            if not isinstance(call, dict) or call.get('type') != 'function':
                raise ValueError('工具调用必须是 function 对象')
            call_id, function = call.get('id'), call.get('function')
            if not isinstance(call_id, str) or not call_id.strip() or call_id in ids:
                raise ValueError('工具调用 ID 必须非空且不能重复')
            if not isinstance(function, dict) or not isinstance(function.get('name'), str) or not function['name'].strip():
                raise ValueError('工具调用必须包含非空函数名')
            if not isinstance(function.get('arguments'), str):
                raise ValueError('工具调用 arguments 必须是 JSON 字符串')
            ids.add(call_id)
            normalized.append({'id': call_id, 'type': 'function', 'function': {
                'name': function['name'], 'arguments': function['arguments']}})
        canonical['tool_calls'] = normalized
    return canonical


def normalize_response(raw, *, tools_allowed):
    # 即使正文/工具调用损坏，usage 和原始响应仍交还调用方，先计数再报错。
    usage = _usage(raw.get('usage'))
    finish = None
    try:
        choices = raw.get('choices')
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError('模型响应缺少有效 choices')
        choice = choices[0]
        finish = choice.get('finish_reason')
        if finish not in ('stop', 'tool_calls'):
            raise ValueError(f'模型响应未正常结束：finish_reason={finish!r}')
        message = _message(choice.get('message'), tools_allowed)
        if bool(message.get('tool_calls')) != (finish == 'tool_calls'):
            raise ValueError('模型停止原因与工具调用不一致')
    except ValueError as error:
        return ModelResponse(None, usage, finish, raw, str(error))
    return ModelResponse(message, usage, finish, raw)


class OpenAIChatModel:
    def __init__(self, client, config):
        self.client = client
        self.config = config

    def _request_options(self):
        return {}

    def query(self, messages, *, tools=None):
        if self.client is None:
            raise ValueError('模型客户端尚未配置')
        payload = {'model': self.config.model_name, 'messages': deepcopy(messages)}
        if tools is not None:
            payload['tools'] = deepcopy(tools)
        payload.update(self._request_options())
        # 不捕获传输/预算/取消异常，不额外重试；沿用注入客户端的配置。
        response = self.client.chat.completions.create(**payload)
        raw = response.model_dump(mode='json', exclude_none=True, warnings=False)
        return normalize_response(raw, tools_allowed=tools is not None)

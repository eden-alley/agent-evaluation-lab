"""SWE 风格的可选请求前检查；0 关闭，不强杀已开始的调用。"""
import math
from time import time as clock


class LimitReached(RuntimeError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def validate(token_limit, wall_time_limit_seconds):
    if type(token_limit) is not int or token_limit < 0:
        raise ValueError('token_limit 必须是非负整数，0 表示关闭')
    if (type(wall_time_limit_seconds) not in (int, float) or
            not math.isfinite(wall_time_limit_seconds) or wall_time_limit_seconds < 0):
        raise ValueError('wall_time_limit_seconds 必须是非负有限数，0 表示关闭')


def check(state, token_limit, wall_time_limit_seconds):
    if token_limit:
        if state.limit_usage_incomplete:
            raise LimitReached('usage_unknown', '本任务存在未知用量，无法继续核对 token 上限，已停止模型请求。')
        if state.limit_tokens_used >= token_limit:
            raise LimitReached('token_limit', f'已达到 token 上限 {token_limit}，已知用量 {state.limit_tokens_used}。')
    if wall_time_limit_seconds and clock() - state.limit_started_at >= wall_time_limit_seconds:
        raise LimitReached('time_limit', f'已达到总时长上限 {wall_time_limit_seconds:g} 秒。')


def record(state, usage):
    count = getattr(usage, 'total_tokens', None)
    if type(count) is int and count >= 0:
        state.limit_tokens_used += count
    else:
        state.limit_usage_incomplete = True


class LimitedModel:
    """复用实际适配器及注入客户端；不增加请求或改变 SDK 重试策略。"""
    def __init__(self, model, before_query, after_query):
        self.model = model
        self.before_query = before_query
        self.after_query = after_query

    @property
    def config(self):
        return getattr(self.model, 'config', None)

    @property
    def client(self):
        return getattr(self.model, 'client', None)

    def query(self, messages, *, tools=None):
        self.before_query()
        response = self.model.query(messages, tools=tools)
        self.after_query(response.usage)
        return response

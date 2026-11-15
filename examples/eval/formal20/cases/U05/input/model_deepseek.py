"""DeepSeek 的服务参数；请求及响应转换复用通用 Chat Completions 实现。"""
from .model_openai import OpenAIChatModel


class DeepSeekModel(OpenAIChatModel):
    def _request_options(self):
        return {'extra_body': {'thinking': {'type': 'disabled'}}}

"""模型适配层的公共数据；不持有凭据，不决定循环或工具权限。"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelConfig:
    provider: str = 'deepseek'
    model_name: str = 'deepseek-flash'
    base_url: str | None = None


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ModelResponse:
    message: dict | None
    usage: ModelUsage | None
    finish_reason: str | None
    raw: dict
    protocol_error: str | None = None

    def require_message(self):
        if self.protocol_error:
            raise ValueError(self.protocol_error)
        if self.message is None:
            raise ValueError('模型未返回有效的 assistant 消息')
        return self.message


class Model(Protocol):
    def query(self, messages: list[dict], *, tools: list[dict] | None = None) -> ModelResponse: ...

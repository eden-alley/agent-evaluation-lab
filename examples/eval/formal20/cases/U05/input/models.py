"""模型工厂。由 agent 按当前源码版本加载，子模块不共用全局裸模块名。"""
from urllib.parse import urlsplit

from .model_base import Model, ModelConfig, ModelResponse, ModelUsage
from .model_deepseek import DeepSeekModel
from .model_openai import OpenAIChatModel

DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
_MODELS = {'deepseek': DeepSeekModel, 'openai_chat': OpenAIChatModel}
PROVIDERS = tuple(_MODELS)


def validate_config(config):
    if config.provider not in _MODELS:
        raise ValueError(f'未知模型供应商：{config.provider}；可选：{", ".join(PROVIDERS)}')
    if not isinstance(config.model_name, str) or not config.model_name.strip():
        raise ValueError('必须明确配置 MODEL')
    if config.base_url is not None:
        url = urlsplit(config.base_url)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ValueError('BASE_URL 必须是无认证信息的 HTTP/HTTPS 服务地址')
        try:
            url.port
        except ValueError:
            raise ValueError('BASE_URL 端口无效') from None


def get_model(config=None, *, client=None, api_key=None):
    config = config if config is not None else ModelConfig()
    validate_config(config)
    if client is None and api_key is not None:
        base_url = config.base_url
        if base_url is None:
            if config.provider != 'deepseek':
                raise ValueError('openai_chat 必须明确配置 BASE_URL')
            base_url = DEEPSEEK_BASE_URL
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
    return _MODELS[config.provider](client, config)

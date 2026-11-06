"""Strict input validation. Credentials are never accepted in config."""
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

# A key-name guard, not a guarantee that arbitrary values contain no credentials.
SENSITIVE_KEYS = {
    "authorization", "proxyauthorization", "apikey", "xapikey", "token",
    "accesstoken", "refreshtoken", "idtoken", "authtoken", "bearertoken",
    "password", "passwd", "secret", "clientsecret", "sharedsecret",
    "privatekey", "credential", "credentials",
}

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ProjectCreate(Input):
    name: StrictStr
    description: StrictStr = ""

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("项目名称不能为空")
        return value.strip()

class ProjectUpdate(Input):
    name: StrictStr | None = None
    description: StrictStr | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if value is None or not value.strip():
            raise ValueError("项目名称不能为空")
        return value.strip()

    @field_validator("description")
    @classmethod
    def valid_description(cls, value):
        if value is None:
            raise ValueError("项目描述须为文本")
        return value


def contains_secret(value):
    if isinstance(value, dict):
        return any(re.sub(r"[^a-z0-9]", "", str(k).lower()) in SENSITIVE_KEYS or contains_secret(v) for k, v in value.items())
    if isinstance(value, list):
        return any(contains_secret(v) for v in value)
    return False

class AgentInput(Input):
    name: StrictStr
    source_path: StrictStr
    python_executable: StrictStr
    entrypoint: StrictStr
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "source_path", "python_executable")
    @classmethod
    def required_text(cls, value):
        if not value.strip():
            raise ValueError("必填项不能为空")
        return value.strip()

    @field_validator("entrypoint")
    @classmethod
    def relative_python(cls, value):
        normalized = value.replace("\\", "/")
        posix = PurePosixPath(normalized)
        windows = PureWindowsPath(value)
        if not value.strip() or posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts or posix.suffix.lower() != ".py":
            raise ValueError("入口须为源码目录内的相对 .py 路径")
        return normalized

    @field_validator("config")
    @classmethod
    def no_secrets(cls, value):
        if contains_secret(value):
            raise ValueError("配置中不能保存凭据")
        return value

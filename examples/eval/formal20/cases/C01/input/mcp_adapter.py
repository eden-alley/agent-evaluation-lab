"""One explicitly configured MCP server over stdio or Streamable HTTP."""

from contextlib import ExitStack, asynccontextmanager, contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from referencing import Registry

from tools import ToolResult


STARTUP_SECONDS = 15
CALL_TIMEOUT = timedelta(seconds=10)
MAX_LIST_PAGES = 32
REMOTE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")
SERVER_NAME = re.compile(r"[A-Za-z0-9_-]{1,24}")
MODEL_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")


class MCPStartupError(RuntimeError):
    """An explicitly configured server could not be opened."""


@dataclass(frozen=True)
class MCPConfig:
    server: str
    command: str | None
    args: tuple[str, ...]
    cwd: Path
    allow_tools: tuple[str, ...]
    read_only_tools: frozenset[str]
    url: str | None = None

    @classmethod
    def load(cls, filename, workspace):
        location = Path(os.path.abspath(Path(filename).expanduser()))
        path = location.resolve(strict=True)
        if location.is_relative_to(workspace) or path.is_relative_to(workspace):
            raise ValueError("MCP 配置须放在任务工作区之外")
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        required = {"server", "allow_tools"}
        allowed = required | {"command", "url", "args", "read_only_tools"}
        if not isinstance(raw, dict) or not required <= raw.keys() <= allowed:
            raise ValueError("MCP 配置须包含 server、allow_tools，以及 command 或 url")
        if ("command" in raw) == ("url" in raw):
            raise ValueError("MCP 配置须在 command 和 url 中选一项")
        server = raw["server"]
        if not isinstance(server, str) or not SERVER_NAME.fullmatch(server):
            raise ValueError("MCP server 名称须为 1–24 位字母、数字、下划线或连字符")
        allow_tools = _tool_names(raw["allow_tools"], "allow_tools")
        read_only = frozenset(_tool_names(raw.get("read_only_tools", []), "read_only_tools"))
        if not allow_tools or not read_only.issubset(allow_tools):
            raise ValueError("MCP 白名单不能为空，只读工具须属于白名单")
        if "url" in raw:
            if "args" in raw:
                raise ValueError("远程 MCP 配置使用 url，args 用于本地进程")
            url = _remote_url(raw["url"])
            return cls(server, None, (), path.parent, allow_tools, read_only, url=url)

        command = raw["command"]
        if not isinstance(command, str) or not command:
            raise ValueError("MCP command 须为 python 或本地可执行文件的绝对路径")
        executable = Path(sys.executable if command == "python" else command)
        if not executable.is_absolute() or not executable.is_file():
            raise ValueError("MCP command 须为 python 或存在的本地可执行文件绝对路径")
        if executable.is_relative_to(workspace) or executable.resolve().is_relative_to(workspace):
            raise ValueError("MCP 可执行文件须放在任务工作区之外")
        if sys.platform == "win32" and executable.suffix.lower() != ".exe":
            raise ValueError("Windows 下 MCP command 须指向 .exe")
        args = raw.get("args", [])
        if not isinstance(args, list) or any(not isinstance(arg, str) or "\0" in arg for arg in args):
            raise ValueError("MCP args 须为字符串列表")
        return cls(server, str(executable), tuple(args), path.parent, allow_tools, read_only)


def _remote_url(url):
    if not isinstance(url, str) or any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise ValueError("MCP url 须为有效的 HTTPS 地址")
    address = urlsplit(url)
    if (address.scheme != "https" or not address.hostname or address.username is not None
            or address.password is not None or "?" in url or "#" in url):
        raise ValueError("MCP url 须为不含凭据、查询参数或片段的 HTTPS 地址")
    if address.port == 0:
        raise ValueError("MCP url 端口须为有效的 HTTPS 端口")
    return url


def _tool_names(values, field):
    if not isinstance(values, list) or any(
            not isinstance(name, str) or not REMOTE_NAME.fullmatch(name) for name in values):
        raise ValueError(f"MCP {field} 须为合法工具名的列表")
    if len(set(values)) != len(values):
        raise ValueError(f"MCP {field} 含重复工具名")
    return tuple(values)


def _check_references(value):
    # The SDK also validates outputSchema. Reject network references on both sides.
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                    not isinstance(nested, str) or not nested.startswith("#")):
                raise ValueError("MCP 工具 schema 仅允许文档内部引用")
            _check_references(nested)
    elif isinstance(value, list):
        for nested in value:
            _check_references(nested)


def _build_catalog(config, listed):
    selected = {}
    for tool in listed:
        if tool.name in config.allow_tools:
            if tool.name in selected:
                raise ValueError(f"MCP 服务重复声明白名单工具 {tool.name}")
            selected[tool.name] = tool
    missing = set(config.allow_tools) - selected.keys()
    if missing:
        raise ValueError("MCP 服务缺少白名单工具 " + ", ".join(sorted(missing)))

    catalog = {}
    for name in sorted(selected):
        tool = selected[name]
        alias = f"mcp__{config.server}__{name.replace('.', '_')}"
        if not MODEL_NAME.fullmatch(alias) or alias in catalog:
            raise ValueError(f"MCP 工具别名过长、非法或冲突 {alias}")
        parameters = deepcopy(tool.inputSchema)
        if parameters.get("type") != "object":
            raise ValueError(f"MCP 工具 {name} 的输入 schema 须声明 object")
        _check_references(parameters)
        _check_references(tool.outputSchema)
        Draft202012Validator.check_schema(parameters)
        catalog[alias] = {
            "remote_name": name,
            "schema": {"type": "function", "function": {
                "name": alias, "description": tool.description or name, "parameters": parameters}},
            "validator": Draft202012Validator(parameters, registry=Registry()),
            "output_schema": deepcopy(tool.outputSchema),
        }
    return catalog


class MCPAdapter:
    def __init__(self, config, catalog, request, server_identity):
        self.tools = catalog
        self._request = request
        self.read_only_tools = frozenset(
            alias for alias, tool in catalog.items() if tool["remote_name"] in config.read_only_tools
        )
        # Checkpoint binding hashes this configuration; the argv itself is not persisted.
        self.binding = {
            "server": config.server, "command": config.command, "args": list(config.args),
            "url": config.url,
            "cwd": str(config.cwd), "read_only_tools": sorted(self.read_only_tools),
            "identity": server_identity,
            "catalog": {alias: {"remote_name": tool["remote_name"], "output_schema": tool["output_schema"]}
                        for alias, tool in catalog.items()},
        }

    def execute(self, name, args):
        try:
            response = self._request(self.tools[name]["remote_name"], args)
        except TimeoutError:
            return ToolResult(False, code="mcp_timeout",
                              message="MCP 调用超时，执行状态待核实。请先检查结果再决定是否重试。")
        except Exception as error:
            return ToolResult(False, code="mcp_call_unconfirmed",
                              message=f"MCP 调用未取得完整结果（{type(error).__name__}），执行状态待核实。")

        data = response.structuredContent
        if data is None:
            texts = [part.text for part in response.content if part.type == "text"]
            if not response.isError and len(texts) != len(response.content):
                return ToolResult(False, code="mcp_unsupported_result",
                                  message="MCP 服务已返回，试点支持文本与结构化 JSON。")
            data = "\n".join(texts)
        if response.isError:
            return ToolResult(False, data=data, code="mcp_tool_error", message="MCP 服务报告工具失败。")
        return ToolResult(True, data=data)


async def _list_tools(session, allowed):
    from mcp.types import PaginatedRequestParams

    tools = []
    cursor = None
    seen = set()
    for _ in range(MAX_LIST_PAGES):
        params = PaginatedRequestParams(cursor=cursor) if cursor is not None else None
        page = await session.list_tools(params=params)
        tools.extend(tool for tool in page.tools if tool.name in allowed)
        cursor = page.nextCursor
        if cursor is None:
            return tools
        if cursor in seen:
            raise ValueError("MCP 工具列表返回重复分页游标")
        seen.add(cursor)
    raise ValueError("MCP 工具列表超过分页上限")


@asynccontextmanager
async def _transport(config):
    if config.url is not None:
        from httpx import AsyncClient
        from mcp.client.streamable_http import streamable_http_client

        async with AsyncClient(timeout=STARTUP_SECONDS, trust_env=False) as client:
            async with streamable_http_client(config.url, http_client=client) as (read, write, _):
                yield read, write
        return

    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=config.command, args=list(config.args), cwd=config.cwd,
        env={"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    async with stdio_client(params) as (read, write):
        yield read, write


@asynccontextmanager
async def _connect(config):
    from anyio import fail_after
    from mcp import ClientSession
    from mcp.shared.exceptions import McpError

    async with _transport(config) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=STARTUP_SECONDS)) as session:
            with fail_after(STARTUP_SECONDS):
                initialized = await session.initialize()
                if initialized.capabilities.tools is None:
                    raise ValueError("MCP 服务未声明工具能力")
                catalog = _build_catalog(config, await _list_tools(session, config.allow_tools))
            identity = {"name": initialized.serverInfo.name, "version": initialized.serverInfo.version,
                        "protocol": initialized.protocolVersion}

            async def request(name, args):
                try:
                    with fail_after(CALL_TIMEOUT.total_seconds()):
                        return await session.call_tool(name, args, read_timeout_seconds=CALL_TIMEOUT)
                except McpError as error:
                    if error.error.code == 408:
                        raise TimeoutError() from error
                    raise

            yield catalog, request, identity


@contextmanager
def open_mcp(config_path, *, workspace):
    """Own the SDK session for the entire synchronous CLI interaction."""
    with ExitStack() as stack:
        try:
            config = MCPConfig.load(config_path, workspace)
            from anyio.from_thread import start_blocking_portal

            portal = stack.enter_context(start_blocking_portal())
            connection = portal.wrap_async_context_manager(_connect(config))
            catalog, request, identity = stack.enter_context(connection)
        except Exception as error:
            cause = error
            while isinstance(cause, BaseExceptionGroup) and len(cause.exceptions) == 1:
                cause = cause.exceptions[0]
            raise MCPStartupError(f"MCP 启动或发现失败（{type(cause).__name__}）：{cause}") from error
        try:
            yield MCPAdapter(config, catalog, lambda name, args: portal.call(request, name, args), identity)
        finally:
            # Close the SDK scopes without injecting an unrelated CLI exception into their task group.
            stack.close()

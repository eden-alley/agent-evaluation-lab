"""tools.py —— 第 2 课的注册表 + 第 3 课加固：文件工具只认工作区，shell 固定目录、限时"""
import subprocess
import urllib.request
from urllib.error import HTTPError
from urllib.parse import urljoin
import inspect
import json
from copy import deepcopy
from dataclasses import dataclass
from http.client import IncompleteRead

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry

from sandbox import run_in_sandbox
from permissions import fetch_url_denial

MAX_OUTPUT = 8000
MAX_FETCH_BYTES = 2 * 1024 * 1024
MAX_FETCH_REDIRECTS = 5
TOOLS = {}


@dataclass(frozen=True)
class ToolResult:
    """单次工具结果；legacy 只表示旧函数正常返回，不保证业务操作成功。"""
    ok: bool
    data: object = None
    code: str = ""
    message: str = ""
    available_tools: list | None = None
    exit_code: int | None = None
    result_contract: str = "structured"

    def to_dict(self):
        result = {"ok": self.ok}
        if self.data is not None:
            result["data"] = self.data
        if not self.ok:
            result.update(code=self.code, message=self.message)
        if self.available_tools is not None:
            result["available_tools"] = self.available_tools
        if self.exit_code is not None:
            result["exit_code"] = self.exit_code
        if self.result_contract == "legacy":
            result["result_contract"] = "legacy"
        return result


def _checked_result(result, structured):
    try:
        if not isinstance(result, ToolResult):
            if structured:
                raise ValueError("原生工具必须返回 ToolResult")
            result = ToolResult(True, data=result, result_contract="legacy")
        if type(result.ok) is not bool:
            raise ValueError("ok 必须是布尔值")
        if not isinstance(result.code, str) or not isinstance(result.message, str):
            raise ValueError("code 和 message 必须是字符串")
        if not result.ok and (not result.code.strip() or not result.message.strip()):
            raise ValueError("失败结果必须包含错误码和说明")
        if result.ok and result.code:
            raise ValueError("成功结果不能包含错误码")
        if result.result_contract not in ("structured", "legacy") or (
                structured and result.result_contract != "structured"):
            raise ValueError("返回契约标记不合法")
        if result.exit_code is not None and type(result.exit_code) is not int:
            raise ValueError("exit_code 必须是整数")
        if result.available_tools is not None and (
                not isinstance(result.available_tools, list) or
                any(not isinstance(name, str) for name in result.available_tools)):
            raise ValueError("available_tools 必须是字符串列表")
        json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)
    except Exception as error:
        return ToolResult(False, code="invalid_tool_result",
                          message=f"工具已返回，但结果不符合契约：{error}；执行状态需核实，勿盲目重试。")
    return result


def tool(name, description, parameters):
    def decorator(func):
        if name in TOOLS:
            raise ValueError(f"工具重复注册：{name}")
        schema = deepcopy(parameters)
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as error:
            raise ValueError(f"工具 {name} 的 schema 不合法：{error.message}") from error
        TOOLS[name] = {
            "schema": {"type": "function", "function": {
                "name": name, "description": description, "parameters": schema}},
            "func": func,
            "validator": Draft202012Validator(schema, registry=Registry()),
            "structured_result": True,
        }
        return func
    return decorator


def get_schemas():
    return [t["schema"] for t in TOOLS.values()]


def _params(*, required=None, **props):
    return {"type": "object",
            "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
            "required": list(props) if required is None else required,
            "additionalProperties": False}


@tool("list_dir", "列出工作区内某个目录下的文件和子目录。",
      _params(required=[], path="目录路径，省略时为工作区根目录 ."))
def list_dir(tools, path="."):
    p = tools.workspace.resolve(path)
    if p is None:                      # 双保险：即使绕过了权限检查，这里还会拦
        return ToolResult(False, code="policy_denied", message="[错误] 路径在工作区之外")
    data = "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())) or "(空目录)"
    return ToolResult(True, data=data)


@tool("read_file", "读取一个文本文件的内容。", _params(path="文件路径"))
def read_file(tools, path):
    p = tools.workspace.resolve(path)
    if p is None:
        return ToolResult(False, code="policy_denied", message="[错误] 路径在工作区之外")
    return ToolResult(True, data=p.read_text(encoding="utf-8"))


@tool("write_file", "把内容写入文件，已存在则覆盖。", _params(path="文件路径", content="完整内容"))
def write_file(tools, path, content):
    p = tools.workspace.resolve(path)
    if p is None:
        return ToolResult(False, code="policy_denied", message="[错误] 路径在工作区之外")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return ToolResult(True, data=f"已写入 {p.relative_to(tools.workspace.root)}（{len(content)} 字符）")


def _decode_command_output(data):
    # 本机编码适配：先读原始字节，避免 Windows 的读取线程按 GBK 解码 UTF-8。
    for encoding in ("utf-8-sig", "gbk"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    # 保留原先 text=True 对换行符的统一处理。
    return text.replace("\r\n", "\n").replace("\r", "\n")


@tool("run_shell", "在 Windows 原生沙箱中执行 cmd 批处理命令，for 循环变量使用 %%。",
      _params(command="要执行的命令"))
def run_shell(tools, command, timeout=30):
    try:
        p = tools.run_command(command, tools.workspace.root, timeout)
    except subprocess.TimeoutExpired:
        return ToolResult(False, code="execution_error",
                          message=f"[超时] 命令执行超过 {timeout} 秒，已终止。")
    output = f"[exit {p.returncode}]\n{_decode_command_output(p.stdout)}{_decode_command_output(p.stderr)}"
    return ToolResult(p.returncode == 0, data=output, exit_code=p.returncode,
                      code="execution_error" if p.returncode else "",
                      message="命令非零退出" if p.returncode else "")


@tool("fetch_url", "抓取网页文本，url 以 http/https 开头。", _params(url="完整的 URL"))
def fetch_url(tools, url):
    denial = fetch_url_denial(url)
    if denial:
        return ToolResult(False, code="policy_denied", message=denial)
    opener = urllib.request.build_opener(_NoRedirect())
    for followed in range(MAX_FETCH_REDIRECTS + 1):
        denial = fetch_url_denial(url)
        if denial:
            return ToolResult(False, code="policy_denied", message=denial)
        req = urllib.request.Request(url, headers={"User-Agent": "nami-agent"})
        try:
            resp = opener.open(req, timeout=15)
        except HTTPError as error:
            location = (getattr(req, "_agent_redirect_url", None) or
                        error.headers.get("Location") or error.headers.get("URI"))
            redirect = error.code in (301, 302, 303, 307, 308)
            error.close()  # 重定向及错误正文都不应被无限读取。
            if not redirect or not location:
                raise
            if followed == MAX_FETCH_REDIRECTS:
                return ToolResult(False, code="output_limit_exceeded",
                                  message=f"网页重定向超过 {MAX_FETCH_REDIRECTS} 次，已停止。")
            url = urljoin(req.full_url, location)
            continue
        with resp:
            data = resp.read(MAX_FETCH_BYTES + 1)
            remaining = getattr(resp, "length", None)
            if len(data) <= MAX_FETCH_BYTES and remaining not in (None, 0):
                raise IncompleteRead(data, remaining)
        if len(data) > MAX_FETCH_BYTES:
            return ToolResult(False, code="output_limit_exceeded",
                              message=f"网页响应超过 {MAX_FETCH_BYTES} 字节，未返回不完整正文。")
        return ToolResult(True, data=data.decode("utf-8", errors="replace"))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        req._agent_redirect_url = newurl  # 保留标准库已编码、解析好的目标。
        return None


class Toolset:
    """绑定工作区与命令执行器；默认执行器始终是原生沙箱。"""
    def __init__(self, workspace, *, run_command=None, mcp=None):
        self.workspace = workspace
        self.run_command = run_command if run_command is not None else run_in_sandbox
        if mcp is not None and TOOLS.keys() & mcp.tools.keys():
            raise ValueError("MCP 工具名与原生工具冲突")
        self.mcp = mcp

    def get_schemas(self):
        schemas = get_schemas()
        if self.mcp is not None:
            schemas.extend(deepcopy(tool["schema"]) for tool in self.mcp.tools.values())
        return schemas

    def validate_call(self, name, args):
        if not isinstance(args, dict):
            return ToolResult(False, code="invalid_arguments", message="工具参数必须是 JSON 对象")
        tool = TOOLS.get(name)
        if tool is None and self.mcp is not None:
            tool = self.mcp.tools.get(name)
        if tool is None:
            available = sorted(item["function"]["name"] for item in self.get_schemas())
            return ToolResult(False, code="tool_unavailable",
                              message=f"不存在工具 '{name}'",
                              available_tools=available)
        try:
            if "func" in tool:
                inspect.signature(tool["func"]).bind(self, **args)
            json.dumps(args, allow_nan=False)
        except TypeError as error:
            return ToolResult(False, code="invalid_arguments", message=f"TypeError: {error}")
        except ValueError as error:
            return ToolResult(False, code="invalid_arguments", message=f"参数不是合法 JSON：{error}")
        validator = tool.get("validator")
        if validator is not None:
            try:
                validator.validate(args)
            except ValidationError as error:
                field = ".".join(map(str, error.absolute_path)) or "<参数对象>"
                return ToolResult(False, code="invalid_arguments",
                                  message=f"参数 {field} 不符合工具契约：{error.message}")
            except Exception as error:
                return ToolResult(False, code="execution_error",
                                  message=f"工具参数契约无法校验：{error}")
        return None

    def execute(self, name, args):
        """执行结果统一封装；完整数据留给记录，模型视图由上下文层截断。"""
        invalid = self.validate_call(name, args)
        if invalid is not None:
            return invalid
        try:
            if name not in TOOLS:
                return _checked_result(self.mcp.execute(name, args), structured=True)
            result = TOOLS[name]["func"](self, **args)
        except Exception as e:
            return ToolResult(False, code="execution_error", message=f"{type(e).__name__}: {e}")
        return _checked_result(result, TOOLS[name].get("structured_result", False))

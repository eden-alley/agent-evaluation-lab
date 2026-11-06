"""Inbound MCP stdio bridge. External Coding Agents are clients of the platform."""
import os
from urllib.parse import quote, urlencode, urlsplit

import httpx
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .quality_checks import canonical
from .quality_schemas import DraftInput, ReportInput


def api_url():
    value = os.environ.get("LAB_API_URL", "http://127.0.0.1:8100").rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("LAB_API_URL 必须是本机 HTTP 服务根地址。")
    return value


def result(body, is_error=False):
    return CallToolResult(content=[TextContent(type="text", text=canonical(body))], structuredContent=body, isError=is_error)


async def call(tool, method, path, payload=None):
    try:
        base = api_url()
        headers = {"X-Lab-Tool": tool, "X-Lab-Client": quote(os.environ.get("LAB_CLIENT_NAME", "external-coding-agent"), safe="")}
        async with httpx.AsyncClient(base_url=base, timeout=20, trust_env=False, follow_redirects=False) as client:
            response = await client.request(method, "/api/v1" + path, json=payload, headers=headers)
        body = response.json()
        return result(body, not response.is_success)
    except (httpx.HTTPError, ValueError):
        return result({"error": {"code": "PLATFORM_UNAVAILABLE", "message": "无法连接本地平台；请先启动平台服务并检查 LAB_API_URL。"}}, True)


server = MCPServer("Agent Evaluation Lab", version="0.2.0", instructions=
    "本地评测平台。可读取用户发布的 Skill、提交评测集草案和外部质量报告。用户在网页确认版本。工具完成不代表评测集质量已获独立验证。")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@server.tool(annotations=READ)
async def get_platform_status() -> CallToolResult:
    """读取真实平台能力；不调用任何模型。"""
    return await call("get_platform_status", "GET", "/health")


@server.tool(annotations=READ)
async def list_projects() -> CallToolResult:
    """列出用户已创建的项目，取得 project_id。"""
    return await call("list_projects", "GET", "/projects")


@server.tool(annotations=READ)
async def get_project_context(project_id: str) -> CallToolResult:
    """读取用户提供的项目目标和被测 Agent 信息；不会读取源码或密钥配置。"""
    return await call("get_project_context", "GET", f"/projects/{quote(project_id, safe='')}/context")


@server.tool(annotations=READ)
async def list_skills(query: str = "", kind: str = "") -> CallToolResult:
    """按名称/适用描述/标签关键词及 evaluation 或 business 分类发现已发布 Skill。关键词筛选不是语义推荐。"""
    return await call("list_skills", "GET", "/skills?" + urlencode({"available_only": "true", "query": query, "kind": kind}))


@server.tool(annotations=READ)
async def get_skill(skill_id: str, version_id: str | None = None) -> CallToolResult:
    """读取已发布 Skill 原文与版本哈希；按用户任务选择使用，并将引用写入产物 source.skills。"""
    query = "?" + urlencode({"version_id": version_id}) if version_id else ""
    return await call("get_skill", "GET", f"/skills/{quote(skill_id, safe='')}/content" + query)


@server.tool(annotations=READ)
async def get_submission_contract() -> CallToolResult:
    """读取草案和质量报告的 JSON Schema、限制与版本规则；不是 Skill。"""
    return await call("get_submission_contract", "GET", "/integration/contract")


@server.tool(annotations=READ)
async def list_dataset_drafts(project_id: str) -> CallToolResult:
    """读取项目草案、检查覆盖数和审阅状态。"""
    return await call("list_dataset_drafts", "GET", f"/projects/{quote(project_id, safe='')}/dataset-drafts")


@server.tool(annotations=WRITE)
async def submit_dataset_draft(draft: DraftInput) -> CallToolResult:
    """保存不可变评测集草案；source.skills 绑定用过的已发布 Skill。相同 request_id 只允许相同内容。"""
    return await call("submit_dataset_draft", "POST", "/dataset-drafts", draft.model_dump())


@server.tool(annotations=READ)
async def get_dataset_draft(draft_id: str) -> CallToolResult:
    """读取原始案例、程序校验、最新外部报告和审阅记录。"""
    return await call("get_dataset_draft", "GET", f"/dataset-drafts/{quote(draft_id, safe='')}")


@server.tool(annotations=WRITE)
async def submit_quality_report(draft_id: str, report: ReportInput) -> CallToolResult:
    """提交外部已完成的质量检查；绑定草案哈希及原文证据。不会自动批准数据集。"""
    return await call("submit_quality_report", "POST", f"/dataset-drafts/{quote(draft_id, safe='')}/reports", report.model_dump())


@server.tool(annotations=READ)
async def get_quality_report(draft_id: str, report_id: str) -> CallToolResult:
    """读取指定历史质量报告及其证据，保留报告版本。"""
    return await call("get_quality_report", "GET", f"/dataset-drafts/{quote(draft_id, safe='')}/reports/{quote(report_id, safe='')}")


@server.tool(annotations=READ)
async def list_dataset_versions(project_id: str) -> CallToolResult:
    """列出人工确认的数据集版本，用于选择新草案的 base_version_id。"""
    return await call("list_dataset_versions", "GET", f"/projects/{quote(project_id, safe='')}/dataset-versions")


@server.tool(annotations=READ)
async def get_dataset_version(version_id: str) -> CallToolResult:
    """读取已确认版本的内容、来源、质量报告和人工决定快照。"""
    return await call("get_dataset_version", "GET", f"/dataset-versions/{quote(version_id, safe='')}")


def main():
    server.run(transport="stdio")

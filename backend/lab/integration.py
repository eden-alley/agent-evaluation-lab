"""Connection instructions and observed tool traffic; no client-liveness claims."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Request

from .db import connect
from .datasets import require_project
from .projects import now
from .quality_schemas import submission_contract

TOOLS = ["get_platform_status", "list_projects", "get_project_context", "list_skills", "get_skill",
         "get_submission_contract", "list_dataset_drafts", "submit_dataset_draft", "get_dataset_draft",
         "submit_quality_report", "get_quality_report", "list_dataset_versions", "get_dataset_version",
         "list_evaluation_runs", "get_evaluation_run", "start_judgment", "get_judgment",
         "get_evaluation_evidence"]
router = APIRouter(prefix="/api/v1")


@router.get("/integration")
def integration(request: Request):
    entry = Path(__file__).resolve().parents[1] / "run_mcp.py"
    config = {"command": sys.executable, "args": [str(entry)],
              "env": {"LAB_API_URL": os.environ.get("LAB_PUBLIC_API_URL", "http://127.0.0.1:8100"), "LAB_CLIENT_NAME": "external-coding-agent"}}
    with connect(request.app.state.db_path) as conn:
        last = conn.execute("SELECT client,tool,status_code,created_at FROM external_tool_calls ORDER BY id DESC LIMIT 1").fetchone()
        count = conn.execute("SELECT count(*) FROM external_tool_calls").fetchone()[0]
    return {"transport": "stdio", "protocol": "MCP", "tool_names": TOOLS,
            "startup": config, "last_call": dict(last) if last else None, "recorded_calls": count,
            "skill_policy": "技能内容由用户共同设计并发布；平台只提供目录、版本和读取能力。"}


@router.get("/integration/contract")
def contract():
    return submission_contract()


@router.get("/projects/{project_id}/context")
def project_context(project_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        project = require_project(conn, project_id)
        row = conn.execute("SELECT id,name,source_path,entrypoint,last_check FROM agents WHERE project_id=?", (project_id,)).fetchone()
        agent = dict(row) if row else None
        if agent:
            agent["last_check"] = json.loads(agent["last_check"]) if agent["last_check"] else None
    return {"project": project, "agent_under_test": agent,
            "context_note": "项目描述由用户提供；不足以明确任务目标时，请先向用户确认。工具不读取源码文件或凭据配置。"}


class ToolTraffic:
    def __init__(self, app, db_path):
        self.app, self.db_path = app, db_path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        tool = headers.get(b"x-lab-tool", b"").decode("ascii", "ignore")
        client = unquote(headers.get(b"x-lab-client", b"").decode("ascii", "ignore"))[:160]
        if tool not in TOOLS or not client:
            return await self.app(scope, receive, send)
        status_code = 500
        async def observe(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, observe)
        finally:
            with connect(self.db_path) as conn:
                conn.execute("INSERT INTO external_tool_calls(client,tool,status_code,created_at) VALUES (?,?,?,?)", (client, tool, status_code, now()))

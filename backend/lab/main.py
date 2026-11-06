"""FastAPI application configuration and error handling."""
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from . import agents, projects, quality_routes, skills, integration
from .db import connect, initialize
from .errors import error
from .datasets import QualityError
from .request_limits import RequestSizeLimit
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]

def create_app(db_path=None):
    path = Path(db_path or os.environ.get("LAB_DB_PATH") or ROOT / "data" / "lab.sqlite3")
    initialize(path)
    app = FastAPI(title="Agent Evaluation Lab", docs_url=None, redoc_url=None)
    app.state.db_path = path
    app.add_middleware(RequestSizeLimit)
    app.add_middleware(integration.ToolTraffic, db_path=path)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if "dataset" in request.url.path or "skills" in request.url.path:
            return JSONResponse({"error": {"code": "INVALID_REQUEST", "message": "提交内容有误，请检查字段、编号与引用。",
                "details": [{"field": ".".join(map(str, e["loc"][1:])), "message": e["msg"]} for e in exc.errors()]}}, status_code=422)
        return error("INVALID_REQUEST", "输入有误，请检查必填项、路径格式和配置；配置中不能保存凭据。", 422)

    @app.exception_handler(QualityError)
    async def quality_error(request: Request, exc: QualityError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message, "details": exc.details}}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return error(code, "请求无法完成，请检查地址和操作方式。", exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return error("INTERNAL_ERROR", "服务遇到错误，请稍后重试。", 500)

    @app.get("/api/v1/health")
    def health():
        with connect(path) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        return {"status": "ok", "database": "sqlite", "journal_mode": mode,
                "capabilities": {"projects": True, "agent_registration": True, "agent_check": True,
                    "dataset_quality_handoff": True, "external_agent_tools": True, "skill_catalog": True, "evaluation_execution": False}}

    app.include_router(projects.router)
    app.include_router(agents.router)
    app.include_router(quality_routes.router)
    app.include_router(skills.router)
    app.include_router(integration.router)
    return app

app = create_app()

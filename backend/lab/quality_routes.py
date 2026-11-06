"""HTTP entrypoints shared by the browser and MCP adapter."""
from fastapi import APIRouter, Request

from . import datasets
from .quality_schemas import DecisionInput, DraftInput, ReportInput

router = APIRouter(prefix="/api/v1")


@router.post("/dataset-drafts", status_code=201)
def create_draft(payload: DraftInput, request: Request):
    return datasets.create_draft(request.app.state.db_path, payload)


@router.get("/projects/{project_id}/dataset-drafts")
def list_drafts(project_id: str, request: Request):
    return datasets.list_drafts(request.app.state.db_path, project_id)


@router.get("/dataset-drafts/{draft_id}")
def get_draft(draft_id: str, request: Request):
    return datasets.get_draft(request.app.state.db_path, draft_id)


@router.post("/dataset-drafts/{draft_id}/reports", status_code=201)
def add_report(draft_id: str, payload: ReportInput, request: Request):
    return datasets.add_report(request.app.state.db_path, draft_id, payload)


@router.get("/dataset-drafts/{draft_id}/reports/{report_id}")
def get_report(draft_id: str, report_id: str, request: Request):
    return datasets.get_report(request.app.state.db_path, draft_id, report_id)


@router.post("/dataset-drafts/{draft_id}/decision")
def decide(draft_id: str, payload: DecisionInput, request: Request):
    return datasets.decide(request.app.state.db_path, draft_id, payload)


@router.get("/projects/{project_id}/dataset-versions")
def list_versions(project_id: str, request: Request):
    return datasets.list_versions(request.app.state.db_path, project_id)


@router.get("/dataset-versions/{version_id}")
def get_version(version_id: str, request: Request):
    return datasets.get_version(request.app.state.db_path, version_id)

"""Read materials and receive external reports; no background agent runner."""
from fastapi import APIRouter, Query, Request
from ..db import connect
from ..datasets import QualityError
from . import materials, schemas, service

router = APIRouter(prefix="/api/v1/comparisons")


@router.get("/contract")
def contract():
    return schemas.contract()


@router.get("")
def list_comparisons(request: Request, project_id: str | None = None):
    with connect(request.app.state.db_path) as conn:
        rows = conn.execute("SELECT * FROM comparisons ORDER BY created_at DESC,id DESC").fetchall()
        items = []
        for row in rows:
            if project_id and row["project_id"] != project_id:
                continue
            _, snapshot = service.require(conn, row["id"])
            value = service.detail(conn, request, row, snapshot)
            items.append({k: v for k, v in value.items() if k not in ("latest_report", "queue")})
        return {"items": items, "simulations": [{"id": materials.FIXTURE_ID, "name": "U05 模拟B · 仅离线验证", "case_ids": [materials.U05]}]}


@router.post("", status_code=201)
def create(payload: schemas.ComparisonInput, request: Request):
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.create(conn, request, payload)


@router.get("/{identity}")
def detail(identity: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        row, snapshot = service.require(conn, identity)
        return service.detail(conn, request, row, snapshot)


@router.get("/{identity}/cases/{cid}")
def case_context(identity: str, cid: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        return service.case_context(conn, request, identity, cid)


@router.get("/{identity}/cases/{cid}/materials/{material_id}")
def evidence(identity: str, cid: str, material_id: str, request: Request,
             start_line: int = Query(1, ge=1), line_count: int = Query(40, ge=1, le=200)):
    with connect(request.app.state.db_path) as conn:
        _, snapshot = service.require(conn, identity)
        return materials.excerpt(request, snapshot, cid, material_id, start_line, line_count)


@router.post("/{identity}/cases/{cid}/analyses", status_code=201)
def submit_case(identity: str, cid: str, payload: schemas.CaseAnalysisInput, request: Request):
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.submit_case(conn, request, identity, cid, payload)


@router.post("/{identity}/reports", status_code=201)
def submit_report(identity: str, payload: schemas.FinalReportInput, request: Request):
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.submit_report(conn, request, identity, payload)


@router.get("/{identity}/reports/{report_id}")
def get_report(identity: str, report_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        _, snapshot = service.require(conn, identity)
        row = conn.execute("SELECT * FROM comparison_reports WHERE id=? AND comparison_id=?", (report_id, identity)).fetchone()
        if not row:
            raise QualityError("COMPARISON_REPORT_NOT_FOUND", "找不到该对比报告。", 404)
        return service.report_object(request, row, snapshot)

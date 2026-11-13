"""Read materials and receive external reports; no background agent runner."""
from fastapi import APIRouter, Query, Request
from ..db import connect
from ..datasets import QualityError
from . import materials, schemas, service
from . import review
from .review_schemas import ReviewSubmission
from typing import Literal

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
            items.append(service.summary(conn, row, snapshot))
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


def record_source_check(request, identity):
    # Commit the verification result even when a subsequent strict read/write is rejected.
    # The actual file scan is shared only within this request.
    with connect(request.app.state.db_path) as conn:
        return service.verify_sources(conn, request, identity)


@router.post("/{identity}/verify")
def verify_sources(identity: str, request: Request):
    return record_source_check(request, identity)


@router.get("/{identity}/cases/{cid}")
def case_context(identity: str, cid: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        return service.case_context(conn, request, identity, cid)


@router.get("/{identity}/review-materials")
def prepare_review(identity: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        return review.prepare(conn, identity)


@router.get("/{identity}/review-material")
def read_review_material(identity: str, request: Request, case_id: str, path: str,
                         side: Literal["baseline", "candidate"], start_line: int = Query(1, ge=1),
                         line_count: int = Query(40, ge=1, le=200)):
    record_source_check(request, identity)
    with connect(request.app.state.db_path) as conn:
        _, snapshot = service.require(conn, identity)
        return review.read_material(request, snapshot, case_id, side, path, start_line, line_count)


@router.get("/{identity}/review-catalog")
def review_catalog(identity: str, request: Request, case_id: str, side: Literal["baseline", "candidate"],
                   query: str = Query("", max_length=500), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    with connect(request.app.state.db_path) as conn:
        _, snapshot = service.require(conn, identity)
        return review.catalog(snapshot, case_id, side, query, offset, limit)


@router.post("/{identity}/review", status_code=201)
def submit_review(identity: str, payload: ReviewSubmission, request: Request):
    # Resolve an acknowledged submission before scanning files or acquiring the write lock.
    with connect(request.app.state.db_path) as conn:
        saved = review.previous(conn, identity, payload)
        if saved:
            return saved
    record_source_check(request, identity)
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return review.submit(conn, request, identity, payload)


@router.get("/{identity}/cases/{cid}/materials/{material_id}")
def evidence(identity: str, cid: str, material_id: str, request: Request,
             start_line: int = Query(1, ge=1), line_count: int = Query(40, ge=1, le=200)):
    record_source_check(request, identity)
    with connect(request.app.state.db_path) as conn:
        _, snapshot = service.require(conn, identity)
        return materials.excerpt(request, snapshot, cid, material_id, start_line, line_count)


@router.post("/{identity}/cases/{cid}/analyses", status_code=201)
def submit_case(identity: str, cid: str, payload: schemas.CaseAnalysisInput, request: Request):
    record_source_check(request, identity)
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.submit_case(conn, request, identity, cid, payload)


@router.post("/{identity}/reports", status_code=201)
def submit_report(identity: str, payload: schemas.FinalReportInput, request: Request):
    record_source_check(request, identity)
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.submit_report(conn, request, identity, payload)


@router.get("/{identity}/reports/{report_id}")
def get_report(identity: str, report_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        service.require(conn, identity)
        row = conn.execute("SELECT * FROM comparison_reports WHERE id=? AND comparison_id=?", (report_id, identity)).fetchone()
        if not row:
            raise QualityError("COMPARISON_REPORT_NOT_FOUND", "找不到该对比报告。", 404)
        return service.report_object(row, service.source_status(conn, identity))

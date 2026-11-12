"""Trusted checker bindings and separate saved-delivery checking records."""
import hashlib
import json
from pathlib import Path
import uuid
from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, ConfigDict
from .archive import CASE_ID, snapshot
from .checker import package, disk_content_hash
from .worker import execute
from ..datasets import QualityError
from ..db import connect
from ..evaluation_imports import read_run
from ..projects import now
from ..quality_checks import canonical, digest
from ..quality_schemas import Identifier, ShortText

router = APIRouter(prefix="/api/v1/evaluation-runs")

class BindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: Identifier
    package_id: ShortText
    package_version: ShortText

class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: Identifier
    binding_id: Identifier

def binding_object(row):
    return {"id": row["id"], "run_id": row["run_id"], "case_id": row["case_id"],
            "created_at": row["created_at"], "snapshot": json.loads(row["snapshot"])}

def binding(conn, run_id, binding_id):
    row = conn.execute("SELECT * FROM checker_bindings WHERE id=? AND run_id=?", (binding_id, run_id)).fetchone()
    if row is None:
        raise QualityError("BINDING_NOT_FOUND", "找不到这份检查绑定。", 404)
    return row

def validate(request, run_id, row):
    frozen = json.loads(row["snapshot"])
    data = snapshot(*read_run(request, run_id), row["case_id"])
    if (data["source_hash"] != frozen["source_hash"] or data["input_hash"] != frozen["input_hash"]
            or data["task"] != frozen["task"]):
        raise QualityError("CHECK_INPUT_CHANGED", "原归档或任务已变化，不能沿用这份绑定。")
    return frozen

def check_object(row):
    return {**{key: row[key] for key in ("id", "run_id", "binding_id", "status", "created_at")},
            "report": json.loads(row["report"]) if row["report"] else None,
            "error": json.loads(row["error"]) if row["error"] else None}

@router.get("/{run_id}/cases/{case_id}/checker")
def context(run_id: str, case_id: str, request: Request):
    _, run = read_run(request, run_id)
    if not any(c["id"] == case_id for c in run["cases"]):
        raise QualityError("CASE_NOT_FOUND", "找不到这道题。", 404)
    with connect(request.app.state.db_path) as conn:
        bindings = [binding_object(row) for row in conn.execute(
            "SELECT * FROM checker_bindings WHERE run_id=? AND case_id=? ORDER BY created_at DESC,id DESC", (run_id, case_id))]
        rows = conn.execute("""SELECT j.* FROM check_runs j JOIN checker_bindings b ON b.id=j.binding_id
                               WHERE j.run_id=? AND b.case_id=? ORDER BY j.created_at DESC,j.id DESC""", (run_id, case_id))
        runs = [{k: row[k] for k in ("id", "binding_id", "status", "created_at")} for row in rows]
    return {"available": [package()] if case_id == CASE_ID else [], "bindings": bindings, "runs": runs}

@router.post("/{run_id}/cases/{case_id}/checker-bindings", status_code=201)
def bind(run_id: str, case_id: str, payload: BindRequest, request: Request):
    folder, run = read_run(request, run_id)
    with connect(request.app.state.db_path) as conn:
        previous = conn.execute("SELECT * FROM checker_bindings WHERE run_id=? AND request_id=?",
                                (run_id, payload.request_id)).fetchone()
        request_hash = digest({"case_id": case_id, **payload.model_dump()})
        if previous:
            if previous["request_hash"] != request_hash:
                raise QualityError("REQUEST_CONFLICT", "同一请求编号的绑定内容发生变化。")
            return binding_object(previous)
    registered = package()
    if disk_content_hash() != registered["content_hash"]:
        raise QualityError("CHECKER_UPDATED", "检查程序文件已更新，请重启本地 API 后建立新绑定。")
    if payload.package_id != registered["id"] or payload.package_version != registered["version"]:
        raise QualityError("CHECKER_UNSUPPORTED", "检查程序没有登记或版本不匹配。", 422)
    data = snapshot(folder, run, case_id)
    if data["task"]["content_hash"] != registered["task_content_hash"]:
        raise QualityError("CHECKER_TASK_MISMATCH", "这份任务的内容与检查程序支持的版本不一致。", 422)
    try:
        environment = request.app.state.recheck_executor.identity()
    except Exception as exc:
        raise QualityError("CHECK_ENVIRONMENT_UNAVAILABLE", str(exc), 409) from exc
    frozen = {key: data[key] for key in ("task", "source_hash", "input_hash")}
    frozen.update({"package": registered, "environment": environment,
                   "checks": data["definition"]["checks"]})
    with connect(request.app.state.db_path) as conn:
        identity = str(uuid.uuid4())
        conn.execute("INSERT INTO checker_bindings VALUES (?,?,?,?,?,?,?) ON CONFLICT(run_id,request_id) DO NOTHING",
                     (identity, run_id, case_id, payload.request_id, request_hash, canonical(frozen), now()))
        stored = conn.execute("SELECT * FROM checker_bindings WHERE run_id=? AND request_id=?", (run_id, payload.request_id)).fetchone()
        if stored["request_hash"] != request_hash:
            raise QualityError("REQUEST_CONFLICT", "同一请求编号的绑定内容发生变化。")
        return binding_object(stored)

@router.post("/{run_id}/check-runs", status_code=201)
def start(run_id: str, payload: CheckRequest, request: Request, background: BackgroundTasks):
    with connect(request.app.state.db_path) as conn:
        b = binding(conn, run_id, payload.binding_id)
        validate(request, run_id, b)
        previous = conn.execute("SELECT * FROM check_runs WHERE run_id=? AND request_id=?",
                                (run_id, payload.request_id)).fetchone()
        request_hash = digest(payload.model_dump())
        if previous:
            if previous["request_hash"] != request_hash:
                raise QualityError("REQUEST_CONFLICT", "同一请求编号的重新检查内容发生变化。")
            return check_object(previous)
        identity = str(uuid.uuid4())
        inserted = conn.execute("INSERT INTO check_runs VALUES (?,?,?,?,?,'queued',NULL,NULL,?) ON CONFLICT(run_id,request_id) DO NOTHING",
                     (identity, run_id, payload.binding_id, payload.request_id, request_hash, now()))
        row = conn.execute("SELECT * FROM check_runs WHERE run_id=? AND request_id=?", (run_id, payload.request_id)).fetchone()
        if row["request_hash"] != request_hash:
            raise QualityError("REQUEST_CONFLICT", "同一请求编号的重新检查内容发生变化。")
        result = check_object(row)
        if not inserted.rowcount:
            return result
    background.add_task(execute, request.app.state.db_path, request, run_id, identity)
    return result

@router.get("/{run_id}/check-runs/{job_id}")
def get(run_id: str, job_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        row = conn.execute("SELECT * FROM check_runs WHERE id=? AND run_id=?", (job_id, run_id)).fetchone()
        if row is None:
            raise QualityError("CHECK_NOT_FOUND", "找不到这次检查。", 404)
        saved = check_object(row)
        try:
            validate(request, run_id, binding(conn, run_id, row["binding_id"]))
            saved.update(source_state="unchanged", source_warning=None)
        except Exception:
            saved.update(source_state="changed", source_warning="原归档已变化或无法读取；下方是当时保存的检查记录，不能代表当前文件。")
        return saved

@router.get("/{run_id}/check-runs/{job_id}/artifact")
def evidence(run_id: str, job_id: str, path: str, request: Request):
    result = get(run_id, job_id, request)
    ref = next((ref for ref in (result.get("report") or {}).get("evidence", []) if ref["path"] == path), None)
    if ref is None or path not in ("public.json", "external.json"):
        raise QualityError("ARTIFACT_NOT_FOUND", "找不到该检查证据。", 404)
    target = Path(request.app.state.db_path).parent / "check-runs" / job_id / path
    raw = target.read_bytes()
    if len(raw) != ref["bytes"] or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise QualityError("EVIDENCE_CHANGED", "检查证据发生变化。")
    return {"content": raw.decode("utf-8"), **ref}

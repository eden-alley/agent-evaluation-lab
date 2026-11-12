"""Offline evidence-driven grading with immutable reports and append-only reviews."""
import json
import uuid
import re
from pathlib import PurePosixPath
from fastapi import APIRouter, BackgroundTasks, Request
from .db import connect
from .datasets import QualityError
from .projects import now
from .quality_checks import canonical, digest
from .skills import validate_sources
from .evaluation_imports import read_run, read_artifact
from .judge_contracts import JudgeRequest, HumanReview

router = APIRouter(prefix="/api/v1/evaluation-runs")
LABELS = {
    "result": "任务结果未达到完成标准",
    "delivery": "必要交付物或说明缺失",
    "self_test": "最终修改缺少成功自测",
    "localization": "交付的定位依据不满足要求",
    "minimality": "修改引入了额外行为",
    "efficiency": "重复操作缺少新的信息",
    "scope": "修改超出允许范围",
    "conflict": "编辑冲突恢复未达到要求",
    "compare": "结果内容存在偏差",
}
EVIDENCE_NAMES = ("reviewed-score.json", "review-evidence.md", "events.jsonl", "scores.json", "CASE.md")


def source_hash(folder, run):
    return digest({"run": run, "manifest": json.loads((folder / "manifest.json").read_text(encoding="utf-8-sig"))})


def require_job(conn, run_id, job_id):
    row = conn.execute("SELECT * FROM judgments WHERE id=? AND run_id=?", (job_id, run_id)).fetchone()
    if not row:
        raise QualityError("JUDGMENT_NOT_FOUND", "找不到这份评审。", 404)
    return row


def case_evidence(folder, case, shared_files=()):
    refs = []
    mentioned = " ".join(item.get("evidence", "") for item in case.get("checks", []))
    filenames = re.findall(r"[A-Za-z0-9_./-]+\.(?:jsonl|json|md|py)", mentioned)
    names = dict.fromkeys([*filenames, *EVIDENCE_NAMES])
    for name in names:
        matches = [f for f in case.get("files", []) if f["path"].endswith("/" + name) or f["path"] == name]
        if not matches and name not in EVIDENCE_NAMES:
            shared = [f for f in shared_files if f["path"].endswith("/" + name) or f["path"] == name]
            if len(shared) == 1:
                matches = shared
        for file in matches:
            record, _, raw = read_artifact(folder, file["path"], max_bytes=32 * 1024 * 1024)
            content = raw.decode("utf-8-sig")
            if not any(ref["path"] == file["path"] for ref in refs):
                reference = {"path": file["path"], "sha256": record["sha256"], "label": PurePosixPath(file["path"]).name,
                             "excerpt": content[:8000], "truncated": len(content) > 8000}
                if PurePosixPath(file["path"]).name in ("reviewed-score.json", "scores.json"):
                    record_data = json.loads(content)
                    reference["recorded_checks"] = [
                        {"id": item["id"], "value": item["value"]}
                        for item in record_data.get("checks", [])]
                refs.append(reference)
    return refs


def acceptance(checks):
    required = [row for row in checks if row["required_for_task"] and row["applicable"]]
    if any(row["value"] == 0 for row in required):
        return "fail"
    if any(row["review_state"] == "pending" for row in required):
        return "pending_review"
    if not required or any(row["value"] == "unknown" for row in required):
        return "unknown"
    return "pass"


def findings_for(cases):
    findings = []
    for case in cases:
        notes = " ".join(row["reason"] for row in case["checks"])
        failed_result = any(row["id"] == "result" and row["value"] == 0 for row in case["checks"])
        unapplied = failed_result and "补丁未应用" in notes
        precision = failed_result and "int" in notes and ("小数精度" in notes or "取整" in notes)
        for row in case["checks"]:
            phenomenon = row["reason"]
            if not row["applicable"]:
                continue
            if row["review_state"] == "pending":
                owner, category, title = "unresolved", "judge_conflict", "规则与 Judge 对同一判据有分歧"
            elif row["automatic_value"] == 0 and row["value"] == 1:
                owner, category, title = "evaluator", "false_rejection", "评分规则误判了满足要求的结果"
            elif row["value"] == 0:
                if unapplied and row["id"] in ("delivery", "self_test", "localization"):
                    continue
                if precision and row["id"] == "minimality":
                    continue
                owner, category = "agent", row["id"]
                title = LABELS.get(category, row["rule"])
                if row["id"] == "result" and unapplied:
                    category, title = "edit_application", "找到问题后，没能把修复写进源码"
                    phenomenon = " ".join(item["reason"] for item in case["checks"]
                                          if item["id"] in ("localization", "minimality"))
                if row["id"] == "result" and precision:
                    category, title = "precision_loss", "修复通过原测试，却丢了小数精度"
            elif row["id"] == "delivery" and any(
                    phrase in row["reason"] for phrase in ("附注", "叙述错误", "表述不够精确")):
                owner, category, title = "agent", "report_accuracy", "交付说明和实际记录对不上"
            else:
                continue
            findings.append({"owner": owner, "category": category, "title": title,
                             "case_id": case["id"], "check_id": row["id"], "phenomenon": phenomenon,
                             "required_for_task": row["required_for_task"] if category != "report_accuracy" else False,
                             "evidence": row["evidence"]})
    return findings


def normalize_case(case, mode, evidence):
    checks = []
    for item in case.get("checks", []):
        own_records = [ref for ref in evidence if any(
            record["id"] == item["id"] and record["value"] == item["value"]
            for record in ref.get("recorded_checks", []))]
        mentioned = item.get("evidence", "")
        direct = [ref for ref in evidence if ref["label"] in mentioned or ref["path"] in mentioned]
        refs = direct + [ref for ref in own_records if ref not in direct]
        # These records inherit historical labels. Availability of an unrelated
        # attachment alone cannot establish that a criterion passed.
        automatic = item.get("automatic_value", item["value"])
        historical_review = bool(item.get("review_method"))
        value = item["value"]
        state = "historical" if historical_review else "not_required"
        proposal = value if historical_review else None
        source = item.get("review_method") or "归档中的原规则判定"
        if mode == "mock":
            # Deterministic replay substitutes for model output during offline integration.
            proposal = item["value"]
            source = "模拟 Judge 响应，取自已归档判定；模型请求为 0"
            state = "not_required"
            if automatic in (0, 1) and proposal in (0, 1) and automatic != proposal:
                state, value = "pending", "unknown"
        if not own_records:
            state, value = "missing_evidence", "unknown"
        elif value == "unknown" and state != "pending":
            state = "missing_evidence"
        checks.append({"id": item["id"], "dimension": item.get("dimension", "未分类"),
                       "rule": item["rule"], "required_for_task": item.get("required_for_task", False),
                       "applicable": item.get("applicable", True), "automatic_value": automatic,
                       "archive_value": item["value"], "judge_value": proposal, "value": value, "review_state": state,
                       "evidence_state": "conflict" if state == "pending" else
                           "insufficient" if state == "missing_evidence" else
                           "simulated" if mode == "mock" else "inherited",
                       "reason": item.get("reason", "归档未提供理由"),
                       "review_reason": "同一判据的规则与模拟 Judge 结论冲突" if state == "pending" else
                           item.get("reason", "") if state == "missing_evidence" else "",
                       "source": source, "method": item.get("method", "archive"),
                       "evidence": refs})
    return {"id": case["id"], "title": case.get("title", case["id"]), "checks": checks,
            "core_acceptance": acceptance(checks)}


def execute_job(db_path, request, run_id, job_id):
    with connect(db_path) as conn:
        changed = conn.execute("UPDATE judgments SET status='running' WHERE id=? AND status='queued'", (job_id,)).rowcount
        if not changed:
            return
        row = dict(require_job(conn, run_id, job_id))
    try:
        folder, run = read_run(request, run_id)
        if source_hash(folder, run) != row["source_hash"]:
            raise QualityError("SOURCE_CHANGED", "运行归档发生变化，请重新发起评审。", 409)
        payload = json.loads(row["payload"])
        cases = []
        for case in run["cases"]:
            if case["id"] in payload["case_ids"]:
                evidence = case_evidence(folder, case, run.get("files", []))
                cases.append(normalize_case(case, payload["mode"], evidence))
        report = {"schema_version": 1, "run_id": run_id, "dataset": run.get("dataset"),
                  "skill": payload["skill"], "skill_snapshot": payload["skill_content"],
                  "grading_method": run.get("method", "归档未记录"),
                  "mode": payload["mode"], "is_simulation": payload["mode"] == "mock",
                  "model_requests": 0, "cases": cases, "findings": findings_for(cases),
                  "provenance": "真实归档的历史判定整理" if payload["mode"] == "archive" else
                      "真实归档作为输入，模拟 Judge 响应用于离线流程验证"}
        with connect(db_path) as conn:
            conn.execute("UPDATE judgments SET status='completed',report=? WHERE id=?", (canonical(report), job_id))
    except Exception as exc:
        error = {"code": getattr(exc, "code", "JUDGE_FAILED"),
                 "message": getattr(exc, "message", "评审执行异常，请查看材料并重新发起。")}
        with connect(db_path) as conn:
            conn.execute("UPDATE judgments SET status='failed',error=? WHERE id=?", (canonical(error), job_id))


def materialize(conn, row, folder, run):
    payload = json.loads(row["payload"])
    result = {"id": row["id"], "run_id": row["run_id"], "status": row["status"],
              "mode": payload["mode"], "created_at": row["created_at"], "revision": 0,
              "report": None, "reviews": [], "error": json.loads(row["error"]) if row["error"] else None}
    if not row["report"]:
        return result
    if source_hash(folder, run) != row["source_hash"]:
        raise QualityError("SOURCE_CHANGED", "该报告绑定的归档已变化，请重新评审。", 409)
    report = json.loads(row["report"])
    checked = set()
    for case in report["cases"]:
        for item in case["checks"]:
            for ref in item["evidence"]:
                if ref["path"] not in checked:
                    read_artifact(folder, ref["path"], max_bytes=32 * 1024 * 1024)
                    checked.add(ref["path"])
    reviews = conn.execute("SELECT * FROM judgment_reviews WHERE judgment_id=? ORDER BY revision", (row["id"],)).fetchall()
    for review in reviews:
        change = json.loads(review["payload"])
        case = next(c for c in report["cases"] if c["id"] == change["case_id"])
        item = next(c for c in case["checks"] if c["id"] == change["check_id"])
        item.update(value=change["value"], review_state="resolved",
                    source="本机用户人工复核", reason=change["reason"],
                    evidence_state="insufficient" if change["value"] == "unknown" else "sufficient")
        case["core_acceptance"] = acceptance(case["checks"])
        result["reviews"].append({"revision": review["revision"], "created_at": review["created_at"], **change})
        result["revision"] = review["revision"]
    report["findings"] = findings_for(report["cases"])
    result["report"] = report
    return result


@router.post("/{run_id}/judgments", status_code=201)
def start_judgment(run_id: str, payload: JudgeRequest, request: Request, background: BackgroundTasks):
    folder, run = read_run(request, run_id)
    if not set(payload.case_ids).issubset({case["id"] for case in run["cases"]}):
        raise QualityError("CASE_NOT_FOUND", "评审范围含不存在的案例。", 404)
    data = payload.model_dump()
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        validate_sources(conn, {"skills": [data["skill"]]})
        previous = conn.execute("SELECT * FROM judgments WHERE run_id=? AND request_id=?", (run_id, payload.request_id)).fetchone()
        if previous:
            if previous["request_hash"] != digest(data):
                raise QualityError("REQUEST_CONFLICT", "同一请求编号的评审范围或方法已变化。", 409)
            return materialize(conn, previous, folder, run)
        identity = str(uuid.uuid4())
        request_hash = digest(data)
        data["skill_content"] = conn.execute("SELECT content FROM skill_versions WHERE id=?",
                                             (payload.skill.version_id,)).fetchone()["content"]
        conn.execute("INSERT INTO judgments VALUES (?,?,?,?,?,?,'queued',NULL,NULL,?)",
                     (identity, run_id, payload.request_id, request_hash, canonical(data), source_hash(folder, run), now()))
        result = materialize(conn, require_job(conn, run_id, identity), folder, run)
    background.add_task(execute_job, request.app.state.db_path, request, run_id, identity)
    return result


@router.get("/{run_id}/judgments")
def list_judgments(run_id: str, request: Request):
    read_run(request, run_id)
    with connect(request.app.state.db_path) as conn:
        rows = conn.execute("SELECT id,status,created_at,payload FROM judgments WHERE run_id=? ORDER BY created_at DESC,id", (run_id,)).fetchall()
    return {"items": [{"id": row["id"], "status": row["status"], "created_at": row["created_at"],
                       "mode": json.loads(row["payload"])["mode"]} for row in rows]}


@router.get("/{run_id}/judgments/{job_id}")
def get_judgment(run_id: str, job_id: str, request: Request):
    folder, run = read_run(request, run_id)
    with connect(request.app.state.db_path) as conn:
        return materialize(conn, require_job(conn, run_id, job_id), folder, run)


@router.post("/{run_id}/judgments/{job_id}/reviews")
def review_judgment(run_id: str, job_id: str, payload: HumanReview, request: Request):
    folder, run = read_run(request, run_id)
    data = payload.model_dump()
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = require_job(conn, run_id, job_id)
        current = materialize(conn, row, folder, run)
        previous = conn.execute("SELECT * FROM judgment_reviews WHERE judgment_id=? AND request_id=?",
                                (job_id, payload.request_id)).fetchone()
        if previous:
            if json.loads(previous["payload"]) != data:
                raise QualityError("REVIEW_CONFLICT", "同一复核请求的内容不一致。", 409)
            return current
        if current["revision"] != payload.revision:
            raise QualityError("STALE_REVIEW", "这份报告已有新的复核，请刷新后重试。", 409)
        if row["status"] != "completed":
            raise QualityError("REPORT_NOT_READY", "评审尚未完成。", 409)
        case = next((c for c in current["report"]["cases"] if c["id"] == payload.case_id), None)
        check = next((c for c in case["checks"] if c["id"] == payload.check_id), None) if case else None
        if check is None:
            raise QualityError("CHECK_NOT_FOUND", "找不到对应判据。", 404)
        conn.execute("INSERT INTO judgment_reviews(judgment_id,revision,request_id,payload,created_at) VALUES (?,?,?,?,?)",
                     (job_id, payload.revision + 1, payload.request_id, canonical(data), now()))
        return materialize(conn, row, folder, run)


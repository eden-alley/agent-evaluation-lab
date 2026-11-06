"""Dataset draft, external quality report and human-confirmed version storage."""
import json
import uuid

from .db import connect
from .projects import find_project, now
from .quality_checks import canonical, check_dataset, digest, draft_metrics, validate_report


class QualityError(Exception):
    def __init__(self, code, message, status=409, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details


def require_project(conn, project_id):
    row = find_project(conn, project_id)
    if not row:
        raise QualityError("PROJECT_NOT_FOUND", "找不到项目。", 404)
    return dict(row)


def report_object(row):
    return {"id": row["id"], "draft_id": row["draft_id"], "sequence": row["sequence"],
            "created_at": row["created_at"], "payload": json.loads(row["payload"])}


def read_draft(conn, draft_id):
    row = conn.execute("SELECT * FROM dataset_drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        raise QualityError("DRAFT_NOT_FOUND", "找不到草案。", 404)
    result = dict(row)
    for key in ("payload", "checks", "decision"):
        result[key] = json.loads(result[key]) if result[key] else None
    result.pop("request_hash")
    report = conn.execute("SELECT * FROM quality_reports WHERE draft_id=? ORDER BY sequence DESC LIMIT 1", (draft_id,)).fetchone()
    result["latest_report"] = report_object(report) if report else None
    result["report_history"] = [{"id": r["id"], "sequence": r["sequence"], "created_at": r["created_at"]}
                                for r in conn.execute("SELECT id,sequence,created_at FROM quality_reports WHERE draft_id=? ORDER BY sequence DESC", (draft_id,))]
    result["metrics"] = draft_metrics(result["payload"], result["checks"], result["latest_report"])
    return result


def get_draft(path, draft_id):
    with connect(path) as conn:
        return read_draft(conn, draft_id)


def get_report(path, draft_id, report_id):
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM quality_reports WHERE id=? AND draft_id=?", (report_id, draft_id)).fetchone()
        if not row:
            raise QualityError("REPORT_NOT_FOUND", "找不到此草案的质量报告。", 404)
        return report_object(row)


def latest_version(conn, dataset_id):
    return conn.execute("SELECT * FROM dataset_versions WHERE dataset_id=? ORDER BY version DESC LIMIT 1", (dataset_id,)).fetchone()


def check_base(conn, dataset_id, base_id):
    current = latest_version(conn, dataset_id)
    if (current["id"] if current else None) != base_id:
        raise QualityError("STALE_BASE_VERSION", "基准版本已变化或不属于此数据集，请读取最新版本后重新提交草案。")


def create_draft(path, model):
    from .skills import validate_sources
    payload = model.model_dump()
    request_hash = digest(payload)
    content = {k: payload[k] for k in ("name", "task_description", "requirements", "cases")}
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        require_project(conn, model.project_id)
        previous = conn.execute("SELECT id,request_hash FROM dataset_drafts WHERE project_id=? AND request_id=?", (model.project_id, model.request_id)).fetchone()
        if previous:
            if previous["request_hash"] != request_hash:
                raise QualityError("IDEMPOTENCY_CONFLICT", "同一请求编号已用于不同内容，请使用新的 request_id。")
            return read_draft(conn, previous["id"])
        validate_sources(conn, payload["source"])
        collection = conn.execute("SELECT * FROM dataset_collections WHERE project_id=? AND name=?", (model.project_id, model.name)).fetchone()
        dataset_id = collection["id"] if collection else str(uuid.uuid4())
        check_base(conn, dataset_id, model.base_version_id)
        timestamp, draft_id = now(), str(uuid.uuid4())
        if not collection:
            conn.execute("INSERT INTO dataset_collections VALUES (?,?,?,?)", (dataset_id, model.project_id, model.name, timestamp))
        conn.execute("""INSERT INTO dataset_drafts
            (id,project_id,dataset_id,base_version_id,request_id,request_hash,content_hash,payload,checks,status,decision,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,'pending',NULL,?)""",
            (draft_id, model.project_id, dataset_id, model.base_version_id, model.request_id, request_hash,
             digest(content), canonical(payload), canonical(check_dataset(payload)), timestamp))
        return read_draft(conn, draft_id)


def add_report(path, draft_id, model):
    from .skills import validate_sources
    payload = model.model_dump()
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        draft = read_draft(conn, draft_id)
        previous = conn.execute("SELECT * FROM quality_reports WHERE draft_id=? AND request_id=?", (draft_id, model.request_id)).fetchone()
        if previous:
            if previous["request_hash"] != digest(payload):
                raise QualityError("IDEMPOTENCY_CONFLICT", "报告请求编号已用于不同内容。")
            return report_object(previous)
        if draft["status"] != "pending":
            raise QualityError("DRAFT_CLOSED", "已审阅草案不能追加报告；修改内容请提交新草案。")
        if draft["content_hash"] != model.draft_hash:
            raise QualityError("HASH_MISMATCH", "报告绑定的内容哈希不匹配，请重新读取此草案。")
        validate_sources(conn, payload["source"])
        issue = validate_report(draft["payload"], payload)
        if issue:
            raise QualityError("INVALID_REPORT_REFERENCE", issue[1], 422, [{"field": issue[0], "message": issue[1]}])
        identity, timestamp = str(uuid.uuid4()), now()
        sequence = (draft["latest_report"]["sequence"] if draft["latest_report"] else 0) + 1
        conn.execute("INSERT INTO quality_reports VALUES (?,?,?,?,?,?,?)", (identity, draft_id, sequence, model.request_id, digest(payload), canonical(payload), timestamp))
        return report_object(conn.execute("SELECT * FROM quality_reports WHERE id=?", (identity,)).fetchone())


def publication_issues(draft):
    report, metrics = draft["latest_report"], draft["metrics"]
    if not report:
        return "尚未收到外部质量报告。"
    if metrics["reviewed_cases"] != metrics["total_cases"]:
        return "质量报告尚未检查全部案例。"
    if metrics["blockers"]:
        return "草案仍含阻断问题，请修订后重新提交。"
    return None


def decide(path, draft_id, model):
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        draft = read_draft(conn, draft_id)
        if draft["status"] != "pending":
            old = draft["decision"]
            if all(old.get(k) == v for k, v in model.model_dump().items()):
                row = conn.execute("SELECT snapshot FROM dataset_versions WHERE draft_id=?", (draft_id,)).fetchone()
                return {"draft": draft, "version": json.loads(row["snapshot"]) if row else None}
            raise QualityError("DRAFT_CLOSED", "此草案已有审阅结论，请刷新。")
        latest = draft["latest_report"]
        if model.report_id != (latest["id"] if latest else None):
            raise QualityError("STALE_REPORT", "质量报告已更新，请刷新并审阅最新报告。")
        version = None
        timestamp = now()
        if model.decision == "approve":
            issue = publication_issues(draft)
            if issue:
                raise QualityError("PUBLICATION_BLOCKED", issue)
            needs_note = draft["metrics"]["warnings"] > 0 or any(c["status"] != "covered" for c in latest["payload"]["coverage"])
            if needs_note and not model.note:
                raise QualityError("ACKNOWLEDGEMENT_REQUIRED", "存在警告或覆盖缺口，请填写接受说明。")
            check_base(conn, draft["dataset_id"], draft["base_version_id"])
            current = latest_version(conn, draft["dataset_id"])
            version = {"id": str(uuid.uuid4()), "project_id": draft["project_id"], "dataset_id": draft["dataset_id"],
                       "draft_id": draft_id, "version": current["version"] + 1 if current else 1,
                       "content_hash": draft["content_hash"], "payload": draft["payload"], "checks": draft["checks"],
                       "quality_report": latest, "decision": {**model.model_dump(), "decided_at": timestamp}, "created_at": timestamp}
            conn.execute("INSERT INTO dataset_versions VALUES (?,?,?,?,?,?,?)", (
                version["id"], draft["project_id"], draft["dataset_id"], draft_id, version["version"], canonical(version), timestamp))
        elif not model.note:
            raise QualityError("REJECTION_REASON_REQUIRED", "请填写退回原因。", 422)
        conn.execute("UPDATE dataset_drafts SET status=?,decision=? WHERE id=?", (
            "approved" if version else "rejected", canonical({**model.model_dump(), "decided_at": timestamp}), draft_id))
        return {"draft": read_draft(conn, draft_id), "version": version}


def list_drafts(path, project_id):
    with connect(path) as conn:
        require_project(conn, project_id)
        ids = conn.execute("SELECT id FROM dataset_drafts WHERE project_id=? ORDER BY created_at DESC,id", (project_id,)).fetchall()
        items = []
        for row in ids:
            draft = read_draft(conn, row["id"])
            items.append({k: draft[k] for k in ("id", "project_id", "dataset_id", "content_hash", "status", "created_at", "metrics")} | {
                "name": draft["payload"]["name"], "source": draft["payload"]["source"], "base_version_id": draft["base_version_id"]})
        return {"items": items}


def list_versions(path, project_id):
    with connect(path) as conn:
        require_project(conn, project_id)
        items = []
        for row in conn.execute("SELECT snapshot FROM dataset_versions WHERE project_id=? ORDER BY created_at DESC", (project_id,)):
            value = json.loads(row["snapshot"])
            items.append({k: value[k] for k in ("id", "dataset_id", "draft_id", "version", "content_hash", "created_at")} | {
                "name": value["payload"]["name"], "case_count": len(value["payload"]["cases"])})
        return {"items": items}


def get_version(path, version_id):
    with connect(path) as conn:
        row = conn.execute("SELECT snapshot FROM dataset_versions WHERE id=?", (version_id,)).fetchone()
        if not row:
            raise QualityError("VERSION_NOT_FOUND", "找不到数据集版本。", 404)
        return json.loads(row["snapshot"])

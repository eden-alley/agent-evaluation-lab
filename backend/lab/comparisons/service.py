"""Append-only external analyses; validate lineage, not analytical truth."""
import json
import uuid
from ..datasets import QualityError
from ..projects import now
from ..quality_checks import canonical, digest
from ..skills import validate_sources
from . import materials


def require(conn, identity):
    row = conn.execute("SELECT * FROM comparisons WHERE id=?", (identity,)).fetchone()
    if not row:
        raise QualityError("COMPARISON_NOT_FOUND", "找不到该对比。", 404)
    return row, json.loads(row["snapshot"])


def analysis_object(row):
    return {"id": row["id"], "case_id": row["case_id"], "revision": row["revision"],
            "created_at": row["created_at"], "content": json.loads(row["content"])}


def latest_analyses(conn, identity):
    rows = conn.execute("SELECT * FROM comparison_case_reports WHERE comparison_id=? ORDER BY revision DESC", (identity,)).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["case_id"], analysis_object(row))
    return result


def task_identity(task):
    if not isinstance(task, dict):
        return digest(task)
    identity = {key: value for key, value in task.items() if key != "difficulty_basis"}
    if isinstance(identity.get("controls"), dict):
        identity["controls"] = {key: value for key, value in identity["controls"].items()
                                if key != "requests_per_case_cap"}
    return digest(identity)


def task_state(snapshot, cid):
    a, b = snapshot["baseline"]["cases"].get(cid), (snapshot.get("candidate") or {}).get("cases", {}).get(cid)
    if not a or not b:
        return "missing_pair"
    if not a["case"].get("task") or not b["case"].get("task"):
        return "unknown_task"
    return "same" if task_identity(a["case"]["task"]) == task_identity(b["case"]["task"]) else "changed_task"


def progress(snapshot, cases):
    observations = [o for c in cases.values() for o in c["content"]["observations"]]
    return {"planned": len(snapshot["case_ids"]), "received": len(cases),
            "collection_complete": len(cases) == len(snapshot["case_ids"]),
            "observations": len(observations),
            "assessed": sum(o["outcome"] not in ("insufficient", "not_covered") for o in observations),
            "unknown": sum(o["outcome"] == "insufficient" for o in observations),
            "not_covered": sum(o["outcome"] == "not_covered" for o in observations)}


def source_status(conn, identity):
    row = conn.execute("SELECT source_state,checked_at FROM comparison_source_checks WHERE comparison_id=?", (identity,)).fetchone()
    return {"source_state": row["source_state"] if row else "unchecked",
            "source_checked_at": row["checked_at"] if row else None,
            "source_state_scope": "last_full_verification"}


def verify_sources(conn, request, identity, snapshot=None):
    if snapshot is None:
        _, snapshot = require(conn, identity)
    state, checked_at = materials.source_state(request, snapshot), now()
    conn.execute("""INSERT INTO comparison_source_checks VALUES (?,?,?)
        ON CONFLICT(comparison_id) DO UPDATE SET source_state=excluded.source_state,checked_at=excluded.checked_at
        WHERE excluded.checked_at >= comparison_source_checks.checked_at""",
                 (identity, state, checked_at))
    return source_status(conn, identity)


def report_object(row, verification):
    return {"id": row["id"], "created_at": row["created_at"], **json.loads(row["content"]), **verification}


def report_summaries(conn, identity):
    return conn.execute("""SELECT id,created_at,json_extract(content,'$.case_report_ids') AS case_report_ids
        FROM comparison_reports WHERE comparison_id=? ORDER BY created_at DESC,id DESC""", (identity,)).fetchall()


def overview(row, snapshot, analyses, reports, verification):
    p = progress(snapshot, analyses)
    source = lambda v: {k: value for k, value in v.items() if k != "cases"} if v else None
    state = "waiting_candidate" if not snapshot.get("candidate") else "reported" if reports else "ready" if p["collection_complete"] else "collecting"
    return {"id": row["id"], "project_id": row["project_id"], "created_at": row["created_at"],
            "name": snapshot["name"], "objective": snapshot["objective"], "workflow": snapshot["workflow"],
            "analyst": snapshot["analyst"], "baseline": source(snapshot["baseline"]), "candidate": source(snapshot.get("candidate")),
            "is_simulation": snapshot["is_simulation"], **verification,
            "progress": p, "state": state,
            "reports": [{"id": r["id"], "created_at": r["created_at"]} for r in reports],
            "has_unreported_changes": bool(reports and set(json.loads(reports[0]["case_report_ids"])) != {a["id"] for a in analyses.values()})}


def summary(conn, row, snapshot):
    return overview(row, snapshot, latest_analyses(conn, row["id"]),
                    report_summaries(conn, row["id"]), source_status(conn, row["id"]))


def detail(conn, request, row, snapshot):
    analyses = latest_analyses(conn, row["id"])
    reports = report_summaries(conn, row["id"])
    verification = source_status(conn, row["id"])
    queue = []
    for cid in snapshot["case_ids"]:
        case = (snapshot["baseline"]["cases"].get(cid) or (snapshot.get("candidate") or {}).get("cases", {}).get(cid))["case"]
        current = analyses.get(cid)
        queue.append({"case_id": cid, "title": case.get("title", cid), "task_state": task_state(snapshot, cid),
                      "analysis_id": current["id"] if current else None, "revision": current["revision"] if current else 0})
    latest = conn.execute("SELECT * FROM comparison_reports WHERE id=?", (reports[0]["id"],)).fetchone() if reports else None
    return {**overview(row, snapshot, analyses, reports, verification), "queue": queue,
            "latest_report": report_object(latest, verification) if latest else None}


def create(conn, request, payload):
    data = payload.model_dump()
    baseline = materials.snapshot_run(request, payload.baseline_run_id, payload.case_ids, "baseline")
    previous = conn.execute("SELECT * FROM comparisons WHERE project_id=? AND request_id=?",
                            (baseline["project_id"], payload.request_id)).fetchone()
    if previous:
        if previous["request_hash"] != digest(data):
            raise QualityError("REQUEST_CONFLICT", "同一对比请求编号的内容不同。", 409)
        return detail(conn, request, previous, json.loads(previous["snapshot"]))
    validate_sources(conn, {"skills": [data["workflow"]]})
    if payload.candidate.kind == "run":
        candidate = materials.snapshot_run(request, payload.candidate.run_id, payload.case_ids, "candidate")
        if candidate["project_id"] != baseline["project_id"]:
            raise QualityError("PROJECT_MISMATCH", "前后运行必须属于同一项目。", 422)
    elif payload.candidate.kind == "simulation":
        if payload.candidate.fixture_id != materials.FIXTURE_ID:
            raise QualityError("SIMULATION_NOT_FOUND", "找不到登记的离线模拟情景。", 404)
        candidate = materials.simulation(baseline, payload.case_ids)
    else:
        candidate = None
    if not set(payload.case_ids).issubset(set(baseline["cases"]) | set((candidate or {}).get("cases", {}))):
        raise QualityError("CASE_NOT_FOUND", "比较清单含不存在的案例。", 404)
    version = conn.execute("SELECT content FROM skill_versions WHERE id=?", (payload.workflow.version_id,)).fetchone()
    snapshot = {**data, "baseline": baseline, "candidate": candidate, "workflow_content": version["content"],
                "is_simulation": baseline["is_simulation"] or bool(candidate and candidate["is_simulation"])
                                 or payload.analyst.kind == "offline_fixture"}
    identity = str(uuid.uuid4())
    conn.execute("INSERT INTO comparisons VALUES (?,?,?,?,?,?)",
                 (identity, baseline["project_id"], payload.request_id, digest(data), canonical(snapshot), now()))
    verify_sources(conn, request, identity, snapshot)
    row, snapshot = require(conn, identity)
    return detail(conn, request, row, snapshot)


def case_context(conn, request, identity, cid):
    _, snapshot = require(conn, identity)
    if cid not in snapshot["case_ids"]:
        raise QualityError("CASE_NOT_FOUND", "该题不在比较清单中。", 404)
    def side(name):
        source = snapshot.get(name)
        case = (source or {}).get("cases", {}).get(cid)
        if not case:
            return None
        return {**case, "is_simulation": source["is_simulation"],
                "materials": [{k: v for k, v in m.items() if k != "content"} for m in case["materials"]]}
    return {"case_id": cid, "task_state": task_state(snapshot, cid), **source_status(conn, identity),
            "baseline": side("baseline"), "candidate": side("candidate"),
            "workflow": snapshot["workflow"], "is_simulation": snapshot["is_simulation"],
            "latest_analysis": latest_analyses(conn, identity).get(cid)}


def submit_case(conn, request, identity, cid, payload, *, explanation=None):
    _, snapshot = require(conn, identity)
    if cid not in snapshot["case_ids"]:
        raise QualityError("CASE_NOT_FOUND", "该题不在比较清单中。", 404)
    data = payload.model_dump()
    if explanation is not None:
        data["explanation"] = explanation
    request_hash = digest(data)
    previous = conn.execute("SELECT * FROM comparison_case_reports WHERE comparison_id=? AND request_id=?", (identity, payload.request_id)).fetchone()
    if previous:
        if previous["case_id"] != cid or previous["request_hash"] != request_hash:
            raise QualityError("REQUEST_CONFLICT", "逐题报告请求编号已有不同内容。", 409)
        return analysis_object(previous)
    materials.assert_current(request, snapshot)
    current = latest_analyses(conn, identity).get(cid)
    if payload.revision != (current["revision"] if current else 0):
        raise QualityError("STALE_ANALYSIS", "该题已有新分析，请刷新修订号。", 409)
    for observation in data["observations"]:
        refs = []
        for ref in observation["evidence"]:
            found = materials.excerpt(request, snapshot, cid, ref["material_id"], ref["start_line"], ref["line_count"])
            if found["sha256"] != ref["sha256"]:
                raise QualityError("EVIDENCE_CHANGED", "证据引用摘要不一致。", 409)
            refs.append(found)
        if observation["outcome"] not in ("insufficient", "not_covered"):
            if task_state(snapshot, cid) != "same" or {r["source"] for r in refs} != {"baseline", "candidate"}:
                raise QualityError("UNSUPPORTED_CONCLUSION", "变化结论需要同题前后证据；缺失或变化题目请记录证据不足。", 422)
        observation["evidence"] = refs
    rid = str(uuid.uuid4())
    conn.execute("INSERT INTO comparison_case_reports VALUES (?,?,?,?,?,?,?,?)", (rid, identity, cid,
                 payload.revision + 1, payload.request_id, request_hash, canonical(data), now()))
    return analysis_object(conn.execute("SELECT * FROM comparison_case_reports WHERE id=?", (rid,)).fetchone())


def submit_report(conn, request, identity, payload):
    _, snapshot = require(conn, identity)
    data = payload.model_dump()
    previous = conn.execute("SELECT * FROM comparison_reports WHERE comparison_id=? AND request_id=?", (identity, payload.request_id)).fetchone()
    if previous:
        if previous["request_hash"] != digest(data):
            raise QualityError("REQUEST_CONFLICT", "整体报告请求编号已有不同内容。", 409)
        return report_object(previous, source_status(conn, identity))
    materials.assert_current(request, snapshot)
    cases = latest_analyses(conn, identity)
    if set(cases) != set(snapshot["case_ids"]) or {a["id"] for a in cases.values()} != set(payload.case_report_ids):
        raise QualityError("INCOMPLETE_OR_STALE_REPORT", "请提交清单内全部题目的最新分析；不能漏题或混入过期版本。", 409)
    observations = {(cid, o["id"]): o for cid, a in cases.items() for o in a["content"]["observations"]}
    for item in [*data["findings"], *data["recommendations"]]:
        referenced = []
        for ref in item["refs"]:
            found = observations.get((ref["case_id"], ref["observation_id"]))
            if found is None:
                raise QualityError("OBSERVATION_NOT_FOUND", "汇总或建议引用了不存在的逐题观察。", 422)
            referenced.append(found)
        if "outcome" in item and item["outcome"] != "mixed" and any(o["outcome"] != item["outcome"] for o in referenced):
            raise QualityError("INCONSISTENT_FINDING", "汇总结论与引用的逐题观察不一致。", 422)
    content = {**data, "is_simulation": snapshot["is_simulation"], "analyst": snapshot["analyst"],
               "workflow": snapshot["workflow"], "case_analyses": list(cases.values()), "progress": progress(snapshot, cases),
               "validation_scope": "平台检查范围、版本和证据引用；未独立验证外部分析的语义或因果结论。"}
    content["report_hash"] = digest(content)
    rid = str(uuid.uuid4())
    conn.execute("INSERT INTO comparison_reports VALUES (?,?,?,?,?,?)", (rid, identity, payload.request_id, digest(data), canonical(content), now()))
    return report_object(conn.execute("SELECT * FROM comparison_reports WHERE id=?", (rid,)).fetchone(), source_status(conn, identity))

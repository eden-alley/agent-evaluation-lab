"""Recorded method delivery and deterministic output checks, never a model judge."""
import json
import re
import uuid

from ..datasets import QualityError
from ..projects import now
from ..quality_checks import canonical, digest
from . import explanations, key_cases


def method_version(content):
    match = re.search(r'(?m)^\s*version:\s*([\d.]+)', content)
    return (tuple(map(int, match.group(1).split('.'))) + (0, 0))[:3] if match else (0, 0, 0)


def issue(conn, request, identity, packet, explain_case_ids=None, review_scope='focused'):
    workflow = packet["workflow"]
    row = conn.execute("""SELECT s.name,v.content FROM skill_versions v
        JOIN skills s ON s.id=v.skill_id WHERE v.id=? AND v.skill_id=?""",
        (workflow["version_id"], workflow["skill_id"])).fetchone()
    if not row or digest({"content": row["content"]}) != workflow["content_hash"]:
        raise QualityError("INVALID_SKILL_SOURCE", "方法正文与固定版本不一致。", 409)
    version = re.search(r"(?m)^\s*version:\s*([\d.]+)", row["content"])
    version_numbers = method_version(row['content'])
    complete_review = version_numbers >= (0, 6, 0)
    selective_review = version_numbers >= (0, 7, 0)
    candidates = key_cases.candidates(packet['metric_report']) if selective_review else []
    ids = [c["case_id"] for c in packet["metric_report"]["cases"]]
    if explain_case_ids is None:
        regressions = [cid for m in packet["metric_report"]["quality"] for cid in m["regressed_cases"]]
        failures = [c["case_id"] for c in packet["metric_report"]["cases"]
                    if (c["candidate"] or c["baseline"] or {}).get("core_acceptance") == "fail"]
        explain_case_ids = [] if selective_review else ids if complete_review else (regressions or failures or ids)[:1]
    if len(set(explain_case_ids)) != len(explain_case_ids) or any(cid not in ids for cid in explain_case_ids):
        raise QualityError("INVALID_EXPLANATION_CASES", "需讲解的题目必须属于本次对比且不能重复。", 422)
    record = {"id": str(uuid.uuid4()), "comparison_id": identity,
        "packet_hash": packet["packet_hash"], "base_report_id": packet["base_report_id"],
        "case_revisions": packet["case_revisions"], "provided_at": now(),
        "channel": request.headers.get("x-lab-client", "http")[:160],
        "skill": {**workflow, "name": row["name"], "content": row["content"],
                  "method_version": version.group(1) if version else None},
        "read_status": "not_verified",
        "requirements": {"explanation_case_ids": explain_case_ids, "advice_evidence_required": True,
                         "no_advice_reason_required": False, "advice_priority_reason_required": complete_review},
        "scope": "程序已提供方法正文；未验证分析者阅读或模型遵循。"}
    if selective_review:
        record['key_case_candidates'] = candidates
        record['requirements'].update(explanation_policy='key_cases', advice_case_explanations_required=True)
    if version_numbers >= (0, 9, 0):
        formal = review_scope == 'formal_batch' and len(ids) > 3
        record['review_policy'] = {'mode': 'formal_batch' if formal else 'focused',
            'label': '正式整批评测' if formal else '小范围验证', 'case_count': len(ids),
            'recommendations_allowed': formal}
        record['requirements']['recommendations_allowed'] = formal
    conn.execute("INSERT INTO review_preparations VALUES (?,?,?,?)",
                 (record["id"], identity, canonical(record), record["provided_at"]))
    return {**packet, "packet_version": "0.9.0" if 'review_policy' in record else "0.7.0" if selective_review else "0.6.0",
            **({'key_case_candidates': candidates} if selective_review else {}),
            **({'review_policy': record['review_policy']} if 'review_policy' in record else {}),
            "delivery_id": record["id"], "skill_delivery": record}


def validate(conn, identity, packet, payload):
    if not payload.delivery_id:
        row = conn.execute('SELECT content FROM skill_versions WHERE id=?', (packet['workflow']['version_id'],)).fetchone()
        if row and method_version(row['content']) >= (0, 9, 0):
            raise QualityError('METHOD_DELIVERY_REQUIRED', '请先准备本次材料，固定分析用途和Skill正文后再提交。', 422)
        return None
    row = conn.execute("SELECT content FROM review_preparations WHERE id=? AND comparison_id=?",
                       (payload.delivery_id, identity)).fetchone()
    if not row:
        raise QualityError("METHOD_DELIVERY_NOT_FOUND", "本次对比没有这条方法提供记录，请重新准备材料。", 422)
    record = json.loads(row["content"])
    keys = ("packet_hash", "base_report_id", "case_revisions")
    if any(record[k] != packet[k] for k in keys) or any(record["skill"][k] != packet["workflow"][k]
            for k in ("skill_id", "version_id", "content_hash")):
        raise QualityError("METHOD_DELIVERY_MISMATCH", "方法提供记录与本次材料或版本不一致。", 409)
    if record['requirements'].get('recommendations_allowed') is False and payload.analysis.recommendations:
        raise QualityError('ADVICE_OUTSIDE_REVIEW_SCOPE', '本次为小范围验证，只提交指标与关键过程；开发建议仅用于正式整批评测。', 422)
    expected = set(record["requirements"]["explanation_case_ids"])
    actual = {e.case_id for e in payload.analysis.case_explanations}
    if record['requirements'].get('explanation_policy') == 'key_cases':
        supporting = {cid for a in payload.analysis.recommendations for cid in a.case_ids}
        expected |= supporting
        eligible = expected | {c['case_id'] for c in record['key_case_candidates']}
        if actual - eligible:
            raise QualityError('OUTPUT_CHECK_FAILED', '只需讲解关键题；其他对照题请在准备时明确指定。', 422,
                               [{'non_key_case_ids': sorted(actual - eligible)}])
    if expected - actual:
        raise QualityError("OUTPUT_CHECK_FAILED", "缺少本次要求的任务过程讲解。", 422,
                           [{"missing_case_ids": sorted(expected - actual)}])
    for advice in payload.analysis.recommendations:
        if record["requirements"].get("advice_priority_reason_required") and not advice.priority_reason:
            raise QualityError("OUTPUT_CHECK_FAILED", "每条开发建议必须说明优先处理的理由。", 422)
        if {p.case_id for p in advice.evidence} != set(advice.case_ids):
            raise QualityError("OUTPUT_CHECK_FAILED", "每条建议必须提供所引用题目的直接依据。", 422)
    return record


def advice_evidence(request, snapshot, advice, cache):
    result = []
    for pointer in advice.evidence:
        if pointer.case_id not in advice.case_ids:
            raise QualityError("INVALID_ADVICE_EVIDENCE", "建议依据不属于其声明的题目。", 422)
        result.append(explanations.resolve_reference(request, snapshot, pointer.case_id, pointer, cache))
    return result


def output_checks(record, case_explanations, advice_refs):
    return {"status": "passed", "semantic_status": "not_evaluated", "model_compliance": "not_verified",
        "checks": [{"id": "method", "title": "方法版本与提供记录一致", "status": "passed"},
                   {"id": "explanations", "title": "指定任务讲解与引用完整", "status": "passed",
                    "case_ids": list(case_explanations) if record['requirements'].get('explanation_policy') == 'key_cases'
                    else record["requirements"]["explanation_case_ids"]},
                   *([{"id": "advice", "title": "开发建议字段与题目依据完整", "status": "passed",
                    "evidence_count": sum(len(refs) for refs in advice_refs)}] if advice_refs else [])],
        "scope": "仅检查字段、题目范围与原件引用。事实解释、建议有效性、原因正确性及模型遵循尚未验证。"}

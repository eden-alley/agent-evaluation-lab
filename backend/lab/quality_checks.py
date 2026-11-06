"""Deterministic checks and evidence-reference validation, without model calls."""
import hashlib
import json


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def check_dataset(payload):
    findings, seen = [], {}
    def add(category, severity, case_ids, requirement_ids, message):
        findings.append({"id": f"check-{len(findings)+1}", "category": category, "severity": severity,
                         "case_ids": case_ids, "requirement_ids": requirement_ids, "message": message,
                         "origin": "deterministic"})
    for case in payload["cases"]:
        key = canonical(case["input"])
        if key in seen:
            previous = seen[key]
            conflict = canonical(previous["expected"]) != canonical(case["expected"]) or previous["grading_notes"] != case["grading_notes"]
            add("conflicting_expectation" if conflict else "duplicate_input", "blocker" if conflict else "warning",
                [previous["case_id"], case["case_id"]], [],
                "相同输入对应不同预期或评分说明，请拆清上下文。" if conflict else "输入完全相同，请确认是否需要重复案例。")
        else:
            seen[key] = case
        if case["expected"] is None and not case["grading_notes"]:
            add("missing_expectation", "warning", [case["case_id"]], [], "缺少预期结果与评分说明，尚无法判断完成条件。")
        if not case["requirement_ids"]:
            add("unmapped_case", "warning", [case["case_id"]], [], "案例没有关联需求。")
    mapped = {r for c in payload["cases"] for r in c["requirement_ids"]}
    for requirement in payload["requirements"]:
        if requirement["id"] not in mapped:
            add("unmapped_requirement", "warning", [], [requirement["id"]], "此需求尚未关联任何案例。")
    return findings


def validate_report(payload, report):
    """Return a field error; matching a quote verifies reference integrity, not truth."""
    cases = {c["case_id"]: c for c in payload["cases"]}
    requirements = {r["id"]: r for r in payload["requirements"]}
    reviewed = report["reviewed_case_ids"]
    if len(set(reviewed)) != len(reviewed) or not set(reviewed) <= cases.keys():
        return "reviewed_case_ids", "已检查案例存在重复或不属于本草案。"
    coverage_ids = [c["requirement_id"] for c in report["coverage"]]
    if len(set(coverage_ids)) != len(coverage_ids) or set(coverage_ids) != requirements.keys():
        return "coverage", "覆盖矩阵须逐项列出本草案的全部需求，不能重复或遗漏。"
    for item in report["coverage"]:
        ids = item["case_ids"]
        if len(set(ids)) != len(ids) or not set(ids) <= set(reviewed):
            return "coverage.case_ids", "覆盖依据必须来自已检查案例。"
        if any(item["requirement_id"] not in cases[i]["requirement_ids"] for i in ids):
            return "coverage.case_ids", "覆盖案例未关联该需求。"
        if (item["status"] in {"covered", "partial"}) != bool(ids):
            return "coverage.status", "已覆盖或部分覆盖须列出案例；缺失或未检查时不得声明案例覆盖。"
    finding_ids = [f["id"] for f in report["findings"]]
    if len(set(finding_ids)) != len(finding_ids):
        return "findings", "问题编号不能重复。"
    for finding in report["findings"]:
        if not set(finding["case_ids"]) <= set(reviewed) or not set(finding["requirement_ids"]) <= requirements.keys():
            return "findings", "问题只能引用已检查案例或本草案需求。"
        for evidence in finding["evidence"]:
            target, field, identity = evidence["target_type"], evidence["field"], evidence["target_id"]
            if target == "case":
                if identity not in finding["case_ids"] or field not in {"input", "expected", "title", "grading_notes", "requirement_ids"}:
                    return "findings.evidence", "案例证据须属于当前问题关联的案例与可引用字段。"
                value = cases[identity][field]
            elif target == "requirement":
                if identity not in finding["requirement_ids"] or field != "description":
                    return "findings.evidence", "需求证据须属于当前问题关联的需求描述。"
                value = requirements[identity][field]
            else:
                if identity is not None or field != "task_description":
                    return "findings.evidence", "任务证据只能引用任务描述。"
                value = payload["task_description"]
            text = value if isinstance(value, str) else canonical(value)
            if evidence["quote"] not in text:
                return "findings.evidence.quote", "引用片段与草案字段原文不匹配。"
    return None


def draft_metrics(payload, checks, report):
    findings = checks + (report["payload"]["findings"] if report else [])
    return {"total_cases": len(payload["cases"]), "requirements": len(payload["requirements"]),
            "structurally_checked_cases": len(payload["cases"]),
            "reviewed_cases": len(report["payload"]["reviewed_case_ids"]) if report else 0,
            "covered_requirements": sum(c["status"] == "covered" for c in report["payload"]["coverage"]) if report else 0,
            "blockers": sum(f["severity"] == "blocker" for f in findings),
            "warnings": sum(f["severity"] == "warning" for f in findings)}

"""Versioned projections of saved checks. Never execute or replace a scorer."""
import json
from pathlib import PurePosixPath
from .materials import number
from .service import task_state
from . import repetition

VERSION = "saved-checks-0.3.0"
QUALITY = (
    ("completion", "原任务整体完成", ("core_acceptance",)),
    ("independent", "代码任务独立回归", ("independent",)),
    ("self_test", "最终代码有效自测", ("agent_tested_final_change", "agent_tested_final")),
    ("scope", "任务修改范围遵守", ("scope", "protected_files")),
    ("delivery", "明确报告交付", ("delivery", "report", "change_report")),
    ("localization", "显式定位说明", ("localization",)),
)
RESOURCES = (
    ("model_requests", "模型请求", "次"), ("tool_calls", "归档工具调用", "次"),
    ("tool_errors", "归档工具错误", "次"), ("total_tokens", "累计 tokens", "tokens"),
    ("elapsed_seconds", "题级耗时之和", "秒"),
)
UNASSESSED = (
    ("context_quality", "上下文管理质量", "计数不能证明关键信息保留质量；旧版与新版整理机制的判据和事件口径需要单独核对。"),
    ("cross_tool_repetition", "跨工具等价重复", "原样重复已单独统计；换工具、改变命令写法的等价重复仍未评估。"),
    ("recovery_quality", "错误恢复总体能力", "缺少统一的恢复机会与成功口径，反馈条件也需一致；不能用工具错误数代替恢复能力。"),
    ("conciseness", "简洁度与最小改动", "尚无已确认的评分分档；输出长度和代码行数不能直接替代质量判断。"),
    ("tool_strategy", "工具选择与调用策略", "本次只有调用及错误计数，尚未依据语义和任务需要逐次判断调用是否合理。"),
)


def direction(before, after, gains, losses):
    if after > before:
        return "improved"
    if after < before:
        return "regressed"
    return "mixed" if gains or losses else "unchanged"


def section_ref(material, key=None, check_id=None):
    """Resolve line ranges in the pinned embedded JSON, never from a clipped response."""
    lines = material.get("content", "").splitlines()
    needle = f'"id": {json.dumps(check_id, ensure_ascii=False)}' if check_id else f'"{key}":'
    found = next((i for i, line in enumerate(lines) if needle in line), 0)
    start = max(0, found - 2)
    if check_id:
        # A check is a top-level member of the record's checks array.
        start = next((i for i in range(found, -1, -1) if lines[i] == "    {"), start)
        end = next((i + 1 for i in range(found, len(lines)) if lines[i] in ("    },", "    }")), found + 8)
    else:
        end = found + 18
    return {"material_id": material["id"], "sha256": material["sha256"],
            "start_line": start + 1, "line_count": min(200, max(1, end - start))}


def evidence(entry, side, selected=None, resource=False):
    if not entry:
        return []
    kind = "observed_metrics" if resource else "case_record"
    material = next((m for m in entry["materials"] if m["kind"] == kind), None)
    material = material or next((m for m in entry["materials"] if m["kind"] == "case_record"), None)
    if not material:
        return []
    checks = [c for c in entry["case"].get("checks", []) if c.get("id") in (selected or ())]
    if checks:
        return [{**section_ref(material, check_id=c["id"]), "source": side, "path": material["path"],
                 "check": {k: c.get(k) for k in ("id", "value", "rule", "reason", "evidence", "invalid")}} for c in checks]
    return [{**section_ref(material, key="metrics" if resource else "core_acceptance"),
             "source": side, "path": material["path"]}]


def checks(entry, ids):
    items = [c for c in entry["case"].get("checks", []) if c.get("id") in ids]
    return {c["id"]: c for c in items}, len(items)


def quality_pair(snapshot, cid, identity, ids):
    a = snapshot["baseline"]["cases"].get(cid)
    b = (snapshot.get("candidate") or {}).get("cases", {}).get(cid)
    refs = [*evidence(a, "baseline", ids), *evidence(b, "candidate", ids)]
    if identity == "completion":
        av = a["case"].get("core_acceptance") if a else None
        bv = b["case"].get("core_acceptance") if b else None
        reason = "原记录不是明确 pass/fail；unknown 或无效判据不算失败。"
        valid = av in ("pass", "fail") and bv in ("pass", "fail")
        def required_rules(entry):
            return sorted((c["id"], c.get("rule")) for c in (entry or {}).get("case", {}).get("checks", []) if c.get("required_for_task"))
        ar, br = required_rules(a), required_rules(b)
        valid = valid and bool(ar) and ar == br and all(rule for _, rule in ar)
        if ar != br or not ar or not all(rule for _, rule in ar):
            reason = "原完成判定的必需检查口径缺失或改变，不能直接合并通过率。"
        before, after = int(av == "pass") if av in ("pass", "fail") else None, int(bv == "pass") if bv in ("pass", "fail") else None
    else:
        ac, an = checks(a, ids) if a else ({}, 0)
        bc, bn = checks(b, ids) if b else ({}, 0)
        if not ac and not bc:
            return None
        def verdict(items):
            return int(all(c.get("value") == 1 for c in items.values())) if items and all(
                type(c.get("value")) in (int, float) and c["value"] in (0, 1) and not c.get("invalid") for c in items.values()) else None
        before, after = verdict(ac), verdict(bc)
        valid = (bool(ac) and set(ac) == set(bc) and an == len(ac) and bn == len(bc)
                 and before is not None and after is not None and all(
                     ac[k].get("rule") and ac[k]["rule"] == bc[k].get("rule")
                     and ac[k].get("required_for_task") == bc[k].get("required_for_task") for k in ac))
        reason = "检查缺失、判据改变、值不确定或标记无效，未计入共同分母。"
    state = task_state(snapshot, cid)
    valid = valid and state == "same"
    if state != "same":
        reason = "缺少同题前后记录，或任务要求改变，无法直接判定升降。"
    return {"case_id": cid, "before": before, "after": after, "comparable": bool(valid),
            "reason": "两版同题同判据；只读归并原记录。" if valid else reason, "evidence": refs}


def aggregate(snapshot):
    quality, resources = [], []
    for identity, name, ids in QUALITY:
        items = [p for cid in snapshot["case_ids"] if (p := quality_pair(snapshot, cid, identity, ids)) is not None]
        pairs = [p for p in items if p["comparable"]]
        before, after = sum(p["before"] for p in pairs), sum(p["after"] for p in pairs)
        gains = [p["case_id"] for p in pairs if p["after"] > p["before"]]
        losses = [p["case_id"] for p in pairs if p["after"] < p["before"]]
        quality.append({"id": identity, "name": name, "check_ids": list(ids), "before": before if pairs else None,
            "after": after if pairs else None, "paired_cases": len(pairs), "applicable_cases": len(items),
            "delta_percentage_points": 100 * (after - before) / len(pairs) if pairs else None,
            "direction": direction(before, after, gains, losses) if pairs else "insufficient",
            "improved_cases": gains, "regressed_cases": losses,
            "case_evidence": items, "excluded": [{k: p[k] for k in ("case_id", "reason", "before", "after")} for p in items if not p["comparable"]],
            "definition": "每题每指标计一次；多个对应检查全部通过才计通过。仅合并两版相同的有效判据，不新增评分。"})
    for identity, name, unit in RESOURCES:
        pairs, excluded = [], []
        for cid in snapshot["case_ids"]:
            entries = [snapshot["baseline"]["cases"].get(cid), (snapshot.get("candidate") or {}).get("cases", {}).get(cid)]
            values = [number(e.get("metrics", {}).get(identity)) if e else None for e in entries]
            if any(v is None or v < 0 for v in values) or task_state(snapshot, cid) != "same":
                excluded.append({"case_id": cid, "reason": "缺少同题可比较的有效计数。"})
                continue
            pairs.append({"case_id": cid, "before": values[0], "after": values[1],
                "evidence": [*evidence(entries[0], "baseline", resource=True), *evidence(entries[1], "candidate", resource=True)]})
        before, after = sum(p["before"] for p in pairs), sum(p["after"] for p in pairs)
        resources.append({"id": identity, "name": name, "unit": unit, "before": before if pairs else None,
            "after": after if pairs else None, "paired_cases": len(pairs), "case_evidence": pairs, "excluded": excluded,
            "relative_change_pct": 100 * (after - before) / before if pairs and before else None,
            "direction": ("increased" if after > before else "decreased" if after < before else "unchanged") if pairs else "insufficient"})
    cases = []
    for cid in snapshot["case_ids"]:
        def compact(side):
            item = (snapshot.get(side) or {}).get("cases", {}).get(cid)
            if not item:
                return None
            focal = {"events.jsonl", "test-results.json", "grade.json", "result.json", "phases.json", "report.md", "题面.md", "CASE.md"}
            catalog = [{"path": m["path"], "kind": m["kind"]} for m in item["materials"]
                       if m["kind"] != "archive" or PurePosixPath(m["path"]).name in focal][:32]
            # Input trees can contain megabytes of code. Fetch them only on demand.
            return {"title": item["case"].get("title", cid), "task_turns": (item["case"].get("task") or {}).get("turns", []),
                "core_acceptance": item["case"].get("core_acceptance"),
                "checks": [{k: c.get(k) for k in ("id", "value", "rule", "reason", "invalid")} for c in item["case"].get("checks", [])],
                "metrics": item["metrics"], "materials": catalog, "material_count": len(item["materials"]),
                "catalog_hint": "这里只列常用证据；用文件目录查询按名称/路径搜索其他归档材料。"}
        cases.append({"case_id": cid, "task_state": task_state(snapshot, cid), "baseline": compact("baseline"), "candidate": compact("candidate")})
    unassessed = [{"id": identity, "name": name, "direction": "insufficient", "reason": reason} for identity, name, reason in UNASSESSED]
    return {"registry_version": VERSION, "quality": quality, "resources": resources, "unassessed": unassessed,
        "repetition": repetition.aggregate(snapshot),
        "coverage": {"quality_assessed": sum(m["paired_cases"] > 0 for m in quality), "quality_total": len(quality),
                     "resource_assessed": sum(m["paired_cases"] > 0 for m in resources), "resource_total": len(resources),
                     "unassessed": len(unassessed)}, "cases": cases,
        "limits": ["仅描述本次归档表现；不能据此证明稳定能力变化或单点改动的因果。",
            "各指标适用题目不同，分母必须分别阅读，不合成跨维度总分。",
            "资源消耗与工具计数不等于能力分数；题级耗时之和不是批次挂钟时间，累计 tokens 不是峰值上下文。",
            "上下文、策略、简洁度等缺少确认判据的维度保持未评估，未评估不记零分。"]}

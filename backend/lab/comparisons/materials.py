"""Pinned material catalog and hash-verified excerpts, never execute artifacts."""
import copy
import hashlib
import json
import math
from pathlib import Path
from ..datasets import QualityError
from ..db import connect
from ..evaluation_imports import read_run, read_artifact
from ..quality_checks import canonical, digest

FIXTURE_ID = "u05-offline-v1"
U05 = "U05-click-default-help"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def number(value):
    try:
        return float(value) if not isinstance(value, bool) and value is not None and math.isfinite(float(value)) else None
    except (ValueError, TypeError):
        return None


def embedded(side, case_id, kind, path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2)
    return {"id": "m-" + digest([side, case_id, kind, path])[:24], "source": side,
            "case_id": case_id, "kind": kind, "path": path, "sha256": sha(content.encode()),
            "bytes": len(content.encode()), "content": content}


def snapshot_run(request, run_id, case_ids, side):
    folder, run = read_run(request, run_id)
    run_raw = (folder / "run.json").read_bytes()
    manifest_raw = (folder / "manifest.json").read_bytes()
    if json.loads(run_raw.decode("utf-8-sig")) != run:
        raise QualityError("EVIDENCE_CHANGED", "读取期间运行记录变化，请重试。", 409)
    manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    index = {m["path"]: m for m in manifest["files"]}
    if len(index) != len(manifest["files"]):
        raise QualityError("INVALID_IMPORT", "归档证据路径重复。", 409)
    source = {"kind": "run", "run_id": run_id, "project_id": run["project_id"],
              "name": run.get("name", run_id), "model": run.get("model"), "dataset": run.get("dataset"),
              "is_simulation": bool(run.get("is_simulation", False)),
              "run_hash": sha(run_raw), "manifest_hash": sha(manifest_raw), "cases": {}}
    for case in run.get("cases", []):
        if case["id"] not in case_ids:
            continue
        cid = case["id"]
        record = copy.deepcopy(case)
        catalog = [embedded(side, cid, "case_record", "case-record.json", record),
                   embedded(side, cid, "run_metadata", "run-metadata.json",
                            {k: v for k, v in run.items() if k not in ("cases", "files")})]
        for file in case.get("files", []):
            if file["path"] not in index:
                continue
            entry = index[file["path"]]
            catalog.append({**entry, "id": "m-" + digest([side, cid, "archive", entry["path"]])[:24],
                            "source": side, "case_id": cid, "kind": "archive"})
        with connect(request.app.state.db_path) as conn:
            checks = conn.execute("""SELECT c.id,c.report FROM check_runs c JOIN checker_bindings b ON b.id=c.binding_id
                WHERE c.run_id=? AND b.case_id=? AND c.status='completed' ORDER BY c.created_at DESC,c.id LIMIT 1""",
                                  (run_id, cid)).fetchall()
        for check in checks:
            catalog.append(embedded(side, cid, "saved_check", "saved-check/" + check["id"] + ".json", json.loads(check["report"])))
        metrics = {k: number(case.get("metrics", {}).get(k)) for k in
                   ("model_requests", "prompt_tokens", "completion_tokens", "elapsed_seconds", "estimated_usd")}
        metrics["total_tokens"] = (metrics["prompt_tokens"] + metrics["completion_tokens"]
                                    if metrics["prompt_tokens"] is not None and metrics["completion_tokens"] is not None else None)
        metrics.update(tool_calls=None, tool_errors=None, context_compactions=None)
        trace = next((m for m in catalog if m["kind"] == "archive" and Path(m["path"]).name == "events.jsonl"), None)
        if trace:
            _, _, raw = read_artifact(folder, trace["path"], max_bytes=32 * 1024 * 1024)
            try:
                events = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
                if events:
                    metrics["tool_calls"] = sum(e.get("type") == "tool_call" for e in events)
                    metrics["tool_errors"] = sum(e.get("type") == "tool_result" and e.get("ok") is False for e in events)
                    metrics["context_compactions"] = sum(e.get("type") == "context_compacted" for e in events)
            except (ValueError, TypeError, AttributeError):
                pass  # Missing parseable telemetry remains unknown, never a zero.
        catalog.append(embedded(side, cid, "observed_metrics", "recorded-metrics.json",
                                {"metrics": metrics, "trace_sha256": trace["sha256"] if trace else None,
                                 "scope": "保存的资源与事件计数，不是能力分数。"}))
        source["cases"][cid] = {"case": record, "task_hash": digest(case.get("task", {})),
                                "metrics": metrics, "materials": catalog}
    return source


def simulation(baseline, case_ids):
    if case_ids != [U05] or U05 not in baseline["cases"]:
        raise QualityError("UNSUPPORTED_SIMULATION", "离线模拟B仅支持单题U05。", 422)
    record = copy.deepcopy(baseline["cases"][U05]["case"])
    record["files"] = []
    record["simulation_notice"] = "模拟B：假设修复落地并完成验证；未运行Agent、模型或测试。"
    for check in record.get("checks", []):
        check["value"] = 1 if check["id"] in ("result", "scope", "delivery", "self_test", "localization") else "unknown"
        check["reason"] = "离线情景假设，不是测量或独立评分。"
    metrics = {"model_requests": 22, "tool_calls": 25, "tool_errors": 0,
               "prompt_tokens": 307000, "completion_tokens": 5000, "total_tokens": 312000,
               "elapsed_seconds": 91.2, "estimated_usd": None, "context_compactions": None}
    record["metrics"] = metrics
    scenario = {"is_simulation": True, "execution": "not_executed", "assumptions": record["simulation_notice"],
                "resource_values": metrics, "note": "请求减少但累计tokens和耗时增加，用于验证取舍展示。"}
    return {"kind": "simulation", "fixture_id": FIXTURE_ID, "name": "模拟B · 未执行Agent", "is_simulation": True,
            "project_id": baseline["project_id"], "model": "模拟情景（非模型运行）", "cases": {U05: {
                "case": record, "task_hash": baseline["cases"][U05]["task_hash"], "metrics": metrics,
                "materials": [embedded("candidate", U05, "case_record", "case-record.json", record),
                              embedded("candidate", U05, "simulation", "simulation.json", scenario)]}}}


def source_state(request, snapshot):
    # Cache only within this HTTP request, for the exact pinned sources/scope.
    # Original files are checked afresh on the next strict request.
    state = getattr(request, "state", None)
    if state is None:
        return _scan_sources(request, snapshot)
    key = tuple((name, source["run_id"], source["run_hash"], source["manifest_hash"],
                 tuple((m["path"], m["bytes"], m["sha256"])
                       for case in source["cases"].values() for m in case["materials"] if m["kind"] == "archive"))
                for name in ("baseline", "candidate")
                if (source := snapshot.get(name)) and source["kind"] == "run")
    cache = getattr(state, "comparison_source_checks", None)
    if cache is None:
        cache = state.comparison_source_checks = {}
    if key not in cache:
        cache[key] = _scan_sources(request, snapshot)
    return cache[key]


def _scan_sources(request, snapshot):
    for side in ("baseline", "candidate"):
        source = snapshot.get(side)
        if not source or source["kind"] != "run":
            continue
        folder = Path(request.app.state.db_path).parent / "evaluation-runs" / source["run_id"]
        try:
            resolved_folder = folder.resolve()
            if (sha((folder / "run.json").read_bytes()) != source["run_hash"]
                    or sha((folder / "manifest.json").read_bytes()) != source["manifest_hash"]):
                return "changed"
            seen = set()
            for case in source["cases"].values():
                for material in case["materials"]:
                    if material["kind"] != "archive" or material["path"] in seen:
                        continue
                    seen.add(material["path"])
                    target = (folder / material["path"]).resolve()
                    if not target.is_relative_to(resolved_folder) or not target.is_file():
                        return "changed"
                    raw = target.read_bytes()
                    if len(raw) != material["bytes"] or sha(raw) != material["sha256"]:
                        return "changed"
        except OSError:
            return "changed"
    return "unchanged"


def assert_current(request, snapshot):
    if source_state(request, snapshot) != "unchanged":
        raise QualityError("COMPARISON_SOURCE_CHANGED", "原材料版本已变化；历史报告保留，请为新材料创建新对比。", 409)


def catalog_for(snapshot, case_id):
    return [m for side in ("baseline", "candidate") for m in
            ((snapshot.get(side) or {}).get("cases", {}).get(case_id, {}).get("materials", []))]


def excerpt(request, snapshot, case_id, material_id, start_line=1, line_count=40):
    material = next((m for m in catalog_for(snapshot, case_id) if m["id"] == material_id), None)
    if not material:
        raise QualityError("MATERIAL_NOT_FOUND", "该证据不属于本题的固定材料。", 404)
    assert_current(request, snapshot)
    if material["kind"] == "archive":
        source = snapshot[material["source"]]
        folder = Path(request.app.state.db_path).parent / "evaluation-runs" / source["run_id"]
        _, _, raw = read_artifact(folder.resolve(), material["path"], max_bytes=32 * 1024 * 1024)
        if sha(raw) != material["sha256"]:
            raise QualityError("EVIDENCE_CHANGED", "证据摘要与对比快照不同。", 409)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise QualityError("BINARY_MATERIAL", "该材料不是可引用的文本。", 415) from exc
    else:
        text = material["content"]
    lines = text.splitlines()
    if start_line > len(lines):
        raise QualityError("INVALID_EVIDENCE_RANGE", "证据起始行超出文件。", 422)
    count = min(200, max(1, line_count))
    selected = "\n".join(lines[start_line - 1:start_line - 1 + count])
    return {**{k: v for k, v in material.items() if k != "content"}, "start_line": start_line,
            "line_count": min(count, len(lines) - start_line + 1), "total_lines": len(lines),
            "excerpt": selected[:16000], "truncated": len(selected) > 16000,
            "is_simulation": snapshot[material["source"]]["is_simulation"]}

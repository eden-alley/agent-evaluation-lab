"""Read only manifest-verified input bytes; never execute archived grader code."""
import hashlib
import json
from pathlib import PurePosixPath
from ..datasets import QualityError
from ..evaluation_imports import read_artifact
from ..quality_checks import digest

CASE_ID = "U05-click-default-help"

def source_digest(folder, run):
    return digest({"run": run, "manifest": json.loads((folder / "manifest.json").read_text(encoding="utf-8-sig"))})

def snapshot(folder, run, case_id):
    case = next((c for c in run["cases"] if c["id"] == case_id), None)
    if not case:
        raise QualityError("CASE_NOT_FOUND", "找不到这道题。", 404)
    if case_id != CASE_ID:
        raise QualityError("CHECKER_UNSUPPORTED", "这道题还没有登记可执行的检查程序。", 422)
    paths = {f["path"] for f in case.get("files", [])}
    def ending(suffix):
        matches = [p for p in paths if p.endswith(suffix)]
        if len(matches) != 1:
            raise QualityError("INCOMPLETE_SNAPSHOT", "归档缺少完整的任务或末态快照。")
        return matches[0]
    task_path = ending(f"/{case_id}/case.json")
    result_path = ending(f"/{case_id}/result.json")
    prefix = result_path.rsplit("/", 1)[0]
    inputs = {}
    for path in sorted(paths):
        _, _, raw = read_artifact(folder, path, max_bytes=32 * 1024 * 1024)
        inputs[path] = raw
    definition = json.loads(inputs[task_path])
    result = json.loads(inputs[result_path])
    workspace_prefix = prefix + "/workspace/"
    workspace = {p[len(workspace_prefix):]: raw for p, raw in inputs.items() if p.startswith(workspace_prefix)}
    actual = {p: hashlib.sha256(raw).hexdigest() for p, raw in workspace.items()}
    if not actual or actual != result.get("final_files") or result.get("id") != case_id:
        raise QualityError("INCOMPLETE_SNAPSHOT", "末态工作区与原执行的文件清单不一致。")
    for path in workspace:
        rel = PurePosixPath(path)
        if rel.is_absolute() or ".." in rel.parts or ":" in path or "\\" in path:
            raise QualityError("INVALID_SNAPSHOT", "归档内文件路径不合法。")
    checks = definition["checks"]
    if len({c["id"] for c in checks}) != len(checks):
        raise QualityError("INVALID_CHECKS", "任务判据编号重复。")
    required = {"result", "scope", "delivery", "self_test", "localization", "repeatable"}
    if not required.issubset({c["id"] for c in checks}):
        raise QualityError("INVALID_CHECKS", "任务缺少本检查程序需要的判据。")
    trace_path = prefix + "/events.jsonl"
    events = [json.loads(line) for line in inputs.get(trace_path, b"").decode("utf-8-sig").splitlines() if line.strip()]
    initial = {item["path"]: item["sha256"] for item in definition["files"]}
    return {"case": case, "definition": definition, "result": result, "workspace": workspace, "events": events,
            "task_path": task_path, "trace_path": trace_path, "result_path": result_path,
            "workspace_prefix": workspace_prefix, "initial": initial,
            "task": {"case_id": case_id, "dataset": run.get("dataset"), "content_hash": digest(definition)},
            "source_hash": source_digest(folder, run),
            "input_hash": digest({p: hashlib.sha256(raw).hexdigest() for p, raw in inputs.items()})}

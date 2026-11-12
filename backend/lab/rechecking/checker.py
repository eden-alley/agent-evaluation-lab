"""Registered Click checks. Historical labels are comparison data, never inputs to new verdicts."""
import hashlib
import json
import re
import shlex
from pathlib import Path
from .archive import CASE_ID
from ..quality_checks import digest

PACKAGE_ID = "click-help"
PACKAGE_VERSION = "1.0.0"
SUPPORTED_TASK_HASH = "3df6c578dc8df3ff6938713dceab6908917e7ff1afc50a2cfeb1ea511099f0f5"

def disk_content_hash():
    root = Path(__file__).parent
    names = ["checker.py", "archive.py", "sandbox.py", "worker.py",
             "assets/runner.py", "assets/public.py", "assets/external.py"]
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names})

LOADED_CONTENT_HASH = disk_content_hash()

def package():
    return {"id": PACKAGE_ID, "version": PACKAGE_VERSION, "name": "Click 帮助默认值检查",
            "content_hash": LOADED_CONTENT_HASH,
            "supported_case_ids": [CASE_ID], "task_content_hash": SUPPORTED_TASK_HASH,
            "timeout_seconds_per_suite": 60}

def valid_suite(result, suite):
    expected = 3 if suite == "public" else 1
    required = ("tests", "failures", "errors", "skipped")
    if any(type(result.get(key)) is not int or result[key] < 0 for key in required):
        raise RuntimeError("测试结果字段缺失或不合法。")
    import_failure = (result.get("stage") == "delivery_import" and result.get("delivery_error") is True
                      and result["tests"] == 0 and result["errors"] == 1)
    if (result["tests"] != expected and not import_failure) or result["skipped"]:
        raise RuntimeError("测试未完整执行或发生运行错误，不能计作 Agent 未通过。")
    successful = result["failures"] == result["errors"] == 0
    if type(result.get("successful")) is not bool or result["successful"] != successful:
        raise RuntimeError("测试通过标记与实际结果不一致。")
    if result.get("exit_code") != (0 if successful else 1):
        raise RuntimeError("测试进程退出码与结果不一致。")

def original_self_test(data):
    events, final = data["events"], data["result"]["final_files"]
    # A complete final event with matching inventory anchors the observed interval.
    complete = bool(events and events[-1].get("type") in ("task_stopped", "final_response")
                    and events[-1].get("files") == final
                    and [e.get("event_id") for e in events] == list(range(1, len(events) + 1)))
    business = set(data["definition"]["allowed_changed_paths"])
    calls = {(e.get("phase"), e.get("call_id")): e for e in events if e.get("type") == "tool_call"}
    matches = []
    for event in events:
        if event.get("type") != "tool_result" or event.get("tool") != "run_shell":
            continue
        call = calls.get((event.get("phase"), event.get("call_id")), {})
        try:
            command = json.loads(call.get("arguments", "{}")).get("command", "")
        except (ValueError, AttributeError):
            continue
        output = event.get("data", "")
        try:
            tokens = [t.strip("\"'").replace("\\", "/") for t in shlex.split(command, posix=False)]
        except ValueError:
            continue
        public_suite = any(t in ("-s", "--start-directory") and i + 1 < len(tokens)
                           and tokens[i + 1] in ("tests", "./tests") for i, t in enumerate(tokens))
        public_suite = public_suite or any(t in ("-stests", "--start-directory=tests", "--start-directory=./tests") for t in tokens)
        count = re.search(r"\bRan ([1-9]\d*) tests?\b", output)
        narrowed = any(t.startswith(("-p", "--pattern", "-k")) for t in tokens)
        if not ("unittest" in tokens and "discover" in tokens and public_suite
                and not narrowed and count and int(count.group(1)) >= 3 and event.get("ok") is True
                and event.get("exit_code") == 0 and re.search(r"(?m)^OK\s*$", output)
                and "FAILED" not in output):
            continue
        if all((call.get("files") or {}).get(p) == (event.get("files") or {}).get(p) == final.get(p) for p in business):
            matches.append(call.get("event_id"))
    return (1 if matches else 0 if complete else "unknown"), matches

def results(data, probes, new_evidence):
    public, external = probes
    passed = all(result["successful"] for result in probes)
    changed = [p for p, value in data["initial"].items()
               if p not in data["definition"]["allowed_changed_paths"]
               and (p not in data["workspace"] or hashlib.sha256(data["workspace"][p]).hexdigest() != value)]
    has_report = bool(data["workspace"].get("report.md", b"").strip())
    self_test, calls = original_self_test(data)
    observations = {
        "result": (int(passed), "公开行为检查和独立参数矩阵均通过。" if passed else "交付物未通过全部行为检查。", new_evidence),
        "scope": (int(not changed), "对照初始清单，受保护文件变化：" + repr(changed), [data["task_path"], data["result_path"]]),
        "delivery": ("unknown" if has_report else 0, "报告已保存，内容等待语义复核。" if has_report else "完整末态清单中没有非空 report.md。", [data["result_path"]]),
        "localization": ("unknown" if has_report else 0, "定位说明需要按原要求复核。" if has_report else "要求的报告未交付；此项不能解释为完全没有定位能力。", [data["result_path"], data["trace_path"]]),
        "self_test": (self_test, "仅检查原执行轨迹；最终源码对应的成功自测事件：" + repr(calls), [data["trace_path"], data["result_path"]]),
        "repeatable": (int(public["successful"]) if self_test == 1 else "unknown",
                       "独立重跑对照原成功公开自测。" if self_test == 1 else
                       "没有原交付的成功自测基准；本次测试失败不等于不可复现。", [data["trace_path"], *new_evidence]),
    }
    historical = {check["id"]: check for check in data["case"].get("checks", [])}
    checks = []
    for rule in data["definition"]["checks"]:
        value, reason, evidence = observations.get(rule["id"],
            ("unknown", "本检查程序不作新的语义判定，等待独立复核。", [data["trace_path"]]))
        checks.append({**rule, "value": value, "reason": reason, "evidence": evidence,
                       "historical_value": historical.get(rule["id"], {}).get("value", "unknown"),
                       "source": "independent_checker", "evidence_kind": "retest" if rule["id"] == "result" else "original_or_mixed"})
    required = [c for c in checks if c.get("applicable", True) and c.get("required_for_task")]
    acceptance = "fail" if any(c["value"] == 0 for c in required) else (
        "pass" if required and all(c["value"] == 1 for c in required) else "unknown")
    return {"case_id": data["case"]["id"], "checks": checks, "core_acceptance": acceptance,
            "agent_model_requests": 0, "judge_model_requests": 0,
            "provenance": "对保存的交付物独立检查；没有重新运行 Agent，未复制历史分数。",
            "original_model_requests": data["result"].get("requests"),
            "original_stop_reasons": [p.get("stop_reason") for p in data["result"].get("phases", [])]}

"""Conservative exact-repeat analysis of archived events and actual model inputs."""
import hashlib
import json
import re

from ..quality_checks import canonical

VERSION = "exact-repetition-0.1.1"
NAME = "无效重复调用（原样重复范围）"


def request_index(rows):
    cases = {}
    for line, row in enumerate(rows, 1):
        if not isinstance(row, dict) or row.get("kind") not in ("request", "response"):
            continue
        case = cases.setdefault(row.get("case"), {"requests": {}, "calls": {}, "visible": {}})
        number = row.get("number")
        if row["kind"] == "request":
            messages = row.get("payload", {}).get("messages", [])
            tools = {m["tool_call_id"]: m.get("content", "") for m in messages
                     if isinstance(m, dict) and m.get("role") == "tool" and m.get("tool_call_id")}
            case["requests"][number] = {"line": line, "tools": tools, "number": number}
            for cid, content in tools.items():
                case["visible"].setdefault(cid, {"line": line, "content": content})
        else:
            for choice in row.get("body", {}).get("choices", []):
                for call in (choice.get("message") or {}).get("tool_calls", []):
                    case["calls"][call.get("id")] = number
    return cases


def normalized(content):
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    return {k: v for k, v in value.items() if k != "saved_call_id"}


def ref(source, line, label, excerpt, event_id=None):
    if not source:
        return None
    return {**{k: source[k] for k in ("id", "path", "source", "case_id", "sha256")},
            "kind": source.get("kind","archive"),"bytes":source.get("bytes",0),
            "start_line": line, "line_count": 1, "label": label,
            "excerpt": excerpt[:1100], "excerpt_scope": "selected_record_fields",
            **({"event_id": event_id} if event_id else {})}


def analyze(events, inputs, event_source=None, request_source=None):
    event_lines = {id(event): line for line, event in enumerate(events, 1)}
    calls = [e for e in events if e.get("type") == "tool_call"]
    results = {}
    for e in events:
        if e.get("type") == "tool_result":
            results.setdefault(e.get("call_id"), []).append(e)
    complete = bool(events and events[0].get("type") == "task_started"
                    and events[-1].get("type") in ("task_stopped", "final_response")
                    and [e.get("event_id") for e in events] == list(range(1, len(events)+1))
                    and len({c.get("call_id") for c in calls}) == len(calls)
                    and all(len(results.get(c.get("call_id"), [])) == 1 for c in calls))
    seen, items = {}, []
    for call in calls:
        args = call.get("arguments", {})
        if isinstance(args, str):
            try: args = json.loads(args)
            except ValueError: args = {"unparsed": args}
        if not isinstance(args,dict): args = {"unparsed": args}
        key = (call.get("tool"), canonical(args))
        previous = seen.get(key); seen[key] = call
        if previous is None:
            continue
        item = {"event_id": call["event_id"], "previous_event_id": previous["event_id"],
                "tool": call.get("tool"), "arguments": {k: str(v)[:600] for k, v in args.items() if k in ("path", "command")},
                "classification": "insufficient", "reason": "现有证据不足以确认可复用结果或重复调用的作用。",
                "changed_files": [], "evidence": []}
        for e, label in [(previous, "前次调用"), (call, "本次原样重复调用")]:
            value = ref(event_source, event_lines[id(e)], label,
                        canonical({k: e.get(k) for k in ("event_id", "type", "tool", "arguments")})[:1100], e["event_id"])
            if value: item["evidence"].append(value)
        old_results, new_results = results.get(previous.get("call_id"), []), results.get(call.get("call_id"), [])
        current_input = inputs.get("requests", {}).get(inputs.get("calls", {}).get(call.get("call_id")))
        old_content = (current_input or {}).get("tools", {}).get(previous.get("call_id"))
        new_visible = inputs.get("visible", {}).get(call.get("call_id"))
        item["visible_result_hashes"]={label:hashlib.sha256(canonical(normalized(value)).encode()).hexdigest()
            for label,value in (("before",old_content),("after",(new_visible or {}).get("content"))) if normalized(value) is not None}
        cleared = isinstance(old_content,str) and old_content.strip()=="[旧工具结果已清理，如需要请重新调用工具]"
        item["previous_result_visible"] = isinstance(old_content, str) and not cleared
        if current_input and old_content is not None:
            value = ref(request_source, current_input["line"], "本次决策输入中的前次工具结果",
                        str(old_content)[:650]+("\n…\n"+str(old_content)[-200:] if len(str(old_content))>650 else ""))
            if value: item["evidence"].append(value)
        if new_visible:
            value = ref(request_source, new_visible["line"], "再次调用后模型实际收到的工具结果",
                        str(new_visible["content"])[:650]+("\n…\n"+str(new_visible["content"])[-200:] if len(str(new_visible["content"]))>650 else ""))
            if value: item["evidence"].append(value)
        before_files, after_files = previous.get("files"), call.get("files")
        before_files = before_files if isinstance(before_files,dict) else {}
        after_files = after_files if isinstance(after_files,dict) else {}
        history = [e.get("files") for e in events if previous["event_id"] <= e.get("event_id",0) <= call["event_id"]
                   and e.get("type") != "model_response"]
        if isinstance(before_files,dict) and isinstance(after_files,dict):
            item["changed_files"] = sorted(k for k in set(before_files)|set(after_files)
                if before_files.get(k)!=after_files.get(k))
        def verdict(kind, reason):
            item.update(classification=kind, reason=reason)
        if not complete or not isinstance(args,dict) or len(old_results)!=1 or len(new_results)!=1:
            item["reason"] = "执行记录不完整或调用结果不唯一，不能据此确定重复是否有效。"
        elif call.get("tool") == "read_file" and isinstance(args.get("path"),str):
            path = args["path"].replace("\\", "/")
            hashes = [fs.get(path) if isinstance(fs,dict) else None for fs in history]
            item["file_hashes"] = {"before": (before_files or {}).get(path), "after": (after_files or {}).get(path)}
            if hashes and all(h is not None for h in hashes) and len(set(hashes))>1:
                verdict("necessary", "目标文件在两次读取之间发生变化，再读有重新确认内容的依据。")
            elif cleared:
                verdict("necessary", "本次实际模型输入明确显示旧结果已清理，再次读取可恢复上下文。")
            elif (hashes and all(h is not None for h in hashes) and len(set(hashes))==1
                  and old_results[0].get("ok") is True and new_results[0].get("ok") is True
                  and normalized(old_content) is not None and new_visible
                  and normalized(old_content)==normalized(new_visible["content"])
                  and old_results[0].get("data")==new_results[0].get("data")):
                verdict("useless", "目标文件未变化，旧结果在本次模型输入中仍可见；再次返回的实际可见内容完全相同，没有补充信息。")
        elif call.get("tool") == "run_shell" and isinstance(args.get("command"),str):
            command = re.sub(r"2>\s*&1", "", args["command"]).strip()
            # Compound commands and arbitrary executables remain unjudged.
            if not any(x in command for x in ("&", "|", ";", "\n")):
                script = re.search(r"(?:^|\s)([\w./\\-]+\.py)(?:\s|$)", command)
                discovery = re.search(r"-m\s+unittest\s+discover\b", command)
                testdir = re.search(r"(?:^|\s)-s\s+([\w./\\-]+)", command)
                relevant = []
                if script: relevant = [script.group(1).replace("\\","/")]
                elif discovery and testdir:
                    prefix = testdir.group(1).replace("\\","/").rstrip("/")+"/"
                    relevant = [p for p in item["changed_files"] if p.startswith(prefix) and p.endswith(".py")]
                if relevant and isinstance(before_files,dict) and isinstance(after_files,dict) and any(
                        p in before_files and p in after_files and before_files[p]!=after_files[p] for p in relevant):
                    verdict("necessary", "被执行脚本或发现的测试输入已改变，这次重试有新的验证对象；不代表修改本身符合任务范围。")
        for result, label in [(old_results[0] if len(old_results)==1 else None,"前次实际反馈"),
                              (new_results[0] if len(new_results)==1 else None,"本次实际反馈")]:
            if result:
                value = ref(event_source, event_lines[id(result)], label,
                            canonical({k: result.get(k) for k in ("event_id","ok","exit_code","data")})[:1100], result["event_id"])
                if value: item["evidence"].append(value)
        items.append(item)
    return {"version": VERSION, "status": "complete" if complete else "incomplete", "total_calls": len(calls),
            "candidate_count": len(items), **{k:sum(i["classification"]==k for i in items)
            for k in ("necessary","useless","insufficient")}, "items": items}


def snapshot_analysis(request, folder, events, trace, catalog, cid):
    from ..evaluation_imports import read_artifact
    logs = [m for m in catalog if m["kind"] == "archive" and m["path"].endswith("/model-requests.jsonl")]
    logs = logs or [m for m in catalog if m["kind"] == "archive" and m["path"].split("/")[-1] == "requests.jsonl"]
    index, source = {}, logs[0] if len(logs)==1 else None
    if source and source.get("bytes",0) <= 32*1024*1024:
        cache = getattr(request.state, "exact_repeat_requests", None)
        if cache is None:
            cache = {}; request.state.exact_repeat_requests = cache
        key = (str(folder), source["path"], source["sha256"])
        if key not in cache:
            _, _, raw = read_artifact(folder, source["path"], max_bytes=32*1024*1024)
            try:
                cache[key] = request_index(json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip())
            except (ValueError, TypeError, AttributeError):
                cache[key] = {}
        index = cache[key].get(cid, {})
    safe_events=events if isinstance(events,list) and all(isinstance(e,dict) for e in events) else []
    return analyze(safe_events, index, trace, source)


def aggregate(snapshot):
    from .service import task_state
    rows = []
    for cid in snapshot["case_ids"]:
        a,b = [(snapshot.get(s) or {}).get("cases",{}).get(cid,{}).get("repetition") for s in ("baseline","candidate")]
        valid = bool(a and b and a.get("version")==b.get("version")==VERSION and a["status"]==b["status"]=="complete" and not a["insufficient"] and not b["insufficient"]
                     and not snapshot["is_simulation"] and task_state(snapshot,cid)=="same")
        rows.append({"case_id":cid,"baseline":a,"candidate":b,"comparable":valid,
                     "reason":"原样候选均有明确判定；仅比较本次轨迹。" if valid else "缺少固定分析、完整轨迹或明确判定；不把缺证据记为零。"})
    pairs=[r for r in rows if r["comparable"]]
    totals={s: {k:sum(r[s][k] for r in pairs) for k in ("total_calls","candidate_count","necessary","useless","insufficient")} for s in ("baseline","candidate")}
    a,b=totals["baseline"]["useless"],totals["candidate"]["useless"]
    gains=[r['case_id'] for r in pairs if r['candidate']['useless']<r['baseline']['useless']]
    losses=[r['case_id'] for r in pairs if r['candidate']['useless']>r['baseline']['useless']]
    return {"id":"useless_exact_repetition","name":NAME,"version":VERSION,"cases":rows,
            "paired_cases":len(pairs),"excluded_cases":[r["case_id"] for r in rows if not r["comparable"]],
            "before":a if pairs else None,"after":b if pairs else None,"totals":totals,
            "direction":("improved" if b<a else "regressed" if b>a else "mixed" if gains or losses else "unchanged") if pairs else "insufficient",
            "improved_cases":gains,"regressed_cases":losses,
            "cross_tool_status":"not_evaluated",
            "definition":"工具名与JSON参数完全相同，每次额外调用计1个候选；确认无效次数越少越好。跨工具等价重复未评估，结构相同不自动判无效。"}

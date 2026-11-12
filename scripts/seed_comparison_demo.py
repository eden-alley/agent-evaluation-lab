"""Replay scripted external analysis over real U05 + explicit simulated B.

No model, evaluation runner, checker or archived script is executed.
The actual MCP stdio client reads materials and submits the report.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
RUN = "harness-boundary20-20261109"
CASE = "U05-click-default-help"
SLUG = "agent-version-comparison-workflow"
RESPONSE_VERSION = "v2"


def hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


def publish_workflow(http):
    catalog = json.loads((ROOT / "skills/catalog.json").read_text(encoding="utf-8"))
    entry = next(e for e in catalog["skills"] if e["slug"] == SLUG)
    def checked(response):
        response.raise_for_status()
        return response.json()
    items = checked(http.get("/skills"))["items"]
    matches = [s for s in items if s["name"] == entry["catalog"]["name"]]
    if len(matches) > 1:
        raise RuntimeError("Workflow directory is ambiguous")
    skill = matches[0] if matches else checked(http.post("/skills", json=entry["catalog"]))
    active = skill.get("active_version")
    if not active or active["content_hash"] != entry["platform_content_hash"]:
        payload = json.loads((ROOT / "skills" / entry["payload_file"]).read_text(encoding="utf-8"))
        version = checked(http.post(f"/skills/{skill['id']}/versions", json=payload))
        skill = checked(http.post(f"/skills/{skill['id']}/versions/{version['id']}/publish"))
        active = skill["active_version"]
    if active["content_hash"] != entry["platform_content_hash"]:
        raise RuntimeError("Published workflow hash mismatch")
    return {"skill_id": skill["id"], "version_id": active["id"], "content_hash": active["content_hash"]}


async def submit_demo(api, workflow):
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "backend/run_mcp.py")],
        env={"LAB_API_URL": api, "LAB_CLIENT_NAME": "offline-workflow-validation", "PYTHONIOENCODING": "utf-8"})
    calls = []
    async with Client(params, read_timeout_seconds=30) as client:
        async def call(name, payload=None):
            result = await client.call_tool(name, payload or {})
            if result.is_error:
                raise RuntimeError(str(result))
            calls.append(name)
            return result.structured_content
        contract = await call("get_comparison_contract")
        assert contract["schema_version"] == 1
        fixed = await call("get_skill", {"skill_id": workflow["skill_id"], "version_id": workflow["version_id"]})
        assert fixed["version"]["content_hash"] == workflow["content_hash"]
        plan = await call("create_comparison", {"comparison": {
            "request_id": "u05-offline-v1-" + workflow["content_hash"][:12], "name": "U05 · 版本对比 workflow 离线验证",
            "objective": "用真实旧版与明确标注的模拟B，验证逐题分析、证据下钻和开发建议展示。",
            "baseline_run_id": RUN, "candidate": {"kind": "simulation", "fixture_id": "u05-offline-v1"},
            "case_ids": [CASE], "workflow": workflow,
            "analyst": {"kind": "offline_fixture", "name": "离线脚本模拟外部分析响应", "model": None}}})
        cid = plan["id"]
        context = await call("get_comparison_case", {"comparison_id": cid, "case_id": CASE})
        metrics = context["baseline"]["metrics"]
        request_id = f"u05-scripted-case-{RESPONSE_VERSION}"
        latest = context.get("latest_analysis")
        revision = (latest["content"]["revision"] if latest and latest["content"]["request_id"] == request_id
                    else latest["revision"] if latest else 0)
        assert metrics["model_requests"] == 30 and metrics["tool_calls"] == 33
        a_trace = next(m for m in context["baseline"]["materials"] if m["kind"] == "archive" and m["path"].endswith("/events.jsonl"))
        a_metrics = next(m for m in context["baseline"]["materials"] if m["kind"] == "observed_metrics")
        a_case = next(m for m in context["baseline"]["materials"] if m["kind"] == "case_record")
        a_check = next((m for m in context["baseline"]["materials"] if m["kind"] == "saved_check"), a_case)
        b_sim = next(m for m in context["candidate"]["materials"] if m["kind"] == "simulation")
        tail = await call("read_comparison_material", {"comparison_id": cid, "case_id": CASE, "material_id": a_trace["id"], "start_line": 97, "line_count": 2})
        assert "AssertionError" in tail["excerpt"] and "max_steps" in tail["excerpt"]
        await call("read_comparison_material", {"comparison_id": cid, "case_id": CASE, "material_id": b_sim["id"], "line_count": 40})
        def ref(m, start=1, count=40):
            return {"material_id": m["id"], "sha256": m["sha256"], "start_line": start, "line_count": count}
        check_positions = {}
        start_line = 1
        while start_line <= 2000:
            page = await call("read_comparison_material", {"comparison_id": cid, "case_id": CASE,
                "material_id": a_check["id"], "start_line": start_line, "line_count": 40})
            for offset, line in enumerate(page["excerpt"].splitlines()):
                for check_id in ("result", "scope", "self_test"):
                    if f'"id": "{check_id}"' in line:
                        check_positions[check_id] = start_line + offset
            start_line += page["line_count"]
            if start_line > page["total_lines"]:
                break
        if set(check_positions) != {"result", "scope", "self_test"}:
            raise RuntimeError("Cannot locate archived check evidence")
        check_ref = lambda identity: ref(a_check, max(1, check_positions[identity] - 3), 24)
        def observation(identity, dimension, title, outcome, before, after, reason, evidence, limits="B为模拟情景；不能据此推断真实能力提高。"):
            return {"id": identity, "dimension": dimension, "title": title, "outcome": outcome,
                    "before": before, "after": after, "reason": reason, "limits": limits, "evidence": evidence}
        observations = [
            observation("delivery", "修复与交付", "修复交付从未完成到假设完成", "improved", "真实A没有完成修复，缺少约定报告。", "模拟B假设修复落地并完成交付。", "这里只演示前后结论与证据的关联；B没有真实执行。", [check_ref("result"), ref(b_sim)]),
            observation("edit", "文件编辑可靠性", "目标修改是否实际落地", "improved", "补丁脚本匹配断言失败，业务源码未修复。", "模拟B假设目标修改成功。", "A事件97给出失败，事件98随后因步数上限停止。", [ref(a_trace, 97, 2), ref(b_sim)]),
            observation("validation", "验证行为", "原运行中的有效自测", "improved", "独立检查未找到对应最终源码的完整成功自测。", "模拟B假设修改后完成了有效验证。", "外部重检与Agent原运行自测分别保留；B的成功验证只是情景假设。", [check_ref("self_test"), ref(b_sim)]),
            observation("resources", "资源与效率", "请求减少，耗时与累计tokens增加", "mixed", f"归档题级指标：{metrics['model_requests']}次模型请求、{metrics['tool_calls']}次工具调用、约{metrics['elapsed_seconds']:.2f}秒、{metrics['total_tokens']} tokens。", "模拟值：22次请求、25次工具调用、91.2秒、312000 tokens。", "资源变化有取舍，不能仅因调用减少就判效率全面提高。", [ref(a_metrics), ref(b_sim)]),
            observation("scope", "约束遵守", "保护原有文件与测试", "unchanged", "原独立检查中scope=1。", "模拟B也假设保护范围满足。", "保持约束是独立检查项，不被其他改善抵消。", [check_ref("scope"), ref(b_sim)]),
            observation("recovery", "执行恢复", "错误恢复能力仍需额外证据", "insufficient", "A最后补丁失败后运行结束，未观察到恢复。", "模拟B假设没有发生同类错误。", "未出错不等于证明恢复能力增强；需要真实且有恢复机会的记录。", [ref(a_trace, 97, 2), ref(b_sim)], "单次A与模拟B不足以检验恢复能力。"),
            observation("context", "上下文管理", "压缩后的信息保留未覆盖", "not_covered", "A记录中context_compacted事件为0。", "模拟情景没有设置压缩后的行为验证。", "没有触发相应条件，保留未覆盖，不打满分。", [ref(a_metrics), ref(b_sim)], "不能从累计tokens推断单次上下文压力或压缩质量。"),
        ]
        analysis = await call("submit_comparison_case", {"comparison_id": cid, "case_id": CASE, "analysis": {
            "request_id": request_id, "revision": revision, "summary": "真实A暴露修复未落地；模拟B用于演示改善、资源取舍与未覆盖项。", "observations": observations}})
        refs = lambda *ids: [{"case_id": CASE, "observation_id": value} for value in ids]
        report = await call("submit_comparison_report", {"comparison_id": cid, "report": {
            "request_id": f"u05-scripted-final-{RESPONSE_VERSION}", "case_report_ids": [analysis["id"]],
            "summary": "模拟情景假设修复交付改善，但耗时和累计tokens增加。真实材料仅支持旧版U05的基线诊断；本报告验证链路，不证明新版Agent更强。",
            "findings": [
                {"title": "修复落地与验证改善（模拟）", "outcome": "improved", "explanation": "A的补丁失败有真实记录；B的成功只是假设。", "refs": refs("delivery", "edit", "validation")},
                {"title": "资源代价存在取舍", "outcome": "mixed", "explanation": "模拟B请求更少，但耗时和累计tokens更高；分别展示，不合成总分。", "refs": refs("resources")},
                {"title": "错误恢复尚不能判断", "outcome": "insufficient", "explanation": "B没有真实恢复过程；不能把避免错误当作恢复能力提升。", "refs": refs("recovery")},
                {"title": "压缩质量未被本题有效考察", "outcome": "not_covered", "explanation": "没有压缩后关键事实是否保留的实际证据。", "refs": refs("context")},
            ],
            "recommendations": [
                {"title": "优先核查通用编辑失败反馈与恢复流程", "phenomenon": "真实A的补丁匹配失败，修复未落地，随后步数耗尽。",
                 "cause_status": "hypothesis", "cause": "需进一步核对匹配文本、换行、工具反馈和剩余预算，当前不能确定Harness责任模块。",
                 "action": "先只读核查已有编辑尝试和通用工具行为，确认缺口后再选择最小开发改动，不添加U05专用分支。",
                 "priority_reason": "真实失败直接影响交付，但目前只是一题一次的线索。", "validation": "后续取得相同模型、任务与预算下的真实B，并补足实际可恢复错误的观察机会。",
                 "success_signals": "目标修改落地，原运行完成有效自测和交付；错误出现时可观察到恢复推进。",
                 "guardrails": "原有功能、测试保护范围和权限边界保持；资源代价单列。", "refs": refs("edit", "recovery", "validation")},
                {"title": "先取得真实资源对照，再决定是否优化", "phenomenon": "模拟B展示了请求下降但耗时与tokens增加的情景。",
                 "cause_status": "unresolved", "cause": "B未真实运行，没有证据说明资源差异的原因。", "action": "先补齐真实B的运行记录；不根据模拟数字直接开展性能优化。",
                 "priority_reason": "先确认完成了相同工作，才能解释资源变化。", "validation": "比较同题完成程度、实际自测、请求、tokens和耗时，并报告运行次数与波动。",
                 "success_signals": "得到可重复核查的真实A/B记录，明确功能收益和资源代价。", "guardrails": "避免用提前失败或漏做验证换取更少调用。", "refs": refs("resources")},
            ]}})
        final = await call("get_comparison", {"comparison_id": cid})
        assert final["is_simulation"] and final["progress"]["received"] == 1
        return {"comparison_id": cid, "report_id": report["id"], "workflow": workflow,
                "url": f"http://127.0.0.1:3100/comparison?comparison={cid}", "progress": final["progress"],
                "mcp_calls": calls, "agent_model_requests": 0, "judge_model_requests": 0, "is_simulation": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--receipt", type=Path, default=ROOT / "data/comparison-demo-receipt.json")
    args = parser.parse_args()
    parsed = urlsplit(args.api)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Only a local platform root is supported")
    source = ROOT / "data/evaluation-runs" / RUN
    before = hashes(source)
    with httpx.Client(base_url=args.api + "/api/v1", trust_env=False, timeout=30) as http:
        workflow = publish_workflow(http)
    receipt = asyncio.run(submit_demo(args.api, workflow))
    after = hashes(source)
    if before != after:
        raise RuntimeError("Original archive changed")
    receipt.update(original_archive_unchanged=True, original_archive_files=len(before))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

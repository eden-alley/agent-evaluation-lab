"""Validate retro workflow publication and reporting using saved U05 evidence only.

An actual MCP client reads the workflow and archive, then submits scripted analysis.
There is no candidate B, model call, evaluation run, or checker execution.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from seed_comparison_demo import ROOT, RUN, CASE, hashes, publish_workflow

RESPONSE_VERSION = "retro-v3"


async def submit_baseline(api, workflow):
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "backend/run_mcp.py")],
        env={"LAB_API_URL": api, "LAB_CLIENT_NAME": "offline-retro-validation", "PYTHONIOENCODING": "utf-8"})
    calls = []
    async with Client(params, read_timeout_seconds=30) as client:
        async def call(name, payload=None):
            response = await client.call_tool(name, payload or {})
            if response.is_error:
                raise RuntimeError(str(response))
            calls.append(name)
            return response.structured_content

        contract = await call("get_comparison_contract")
        assert contract["schema_version"] == 1
        fixed = await call("get_skill", {"skill_id": workflow["skill_id"], "version_id": workflow["version_id"]})
        assert fixed["version"]["content_hash"] == workflow["content_hash"]
        assert "已有机制与实际缺口" in fixed["version"]["content"]
        assert "工程复盘清单与建议取舍" in fixed["version"]["content"]
        plan = await call("create_comparison", {"comparison": {
            "request_id": "u05-retro-" + workflow["content_hash"][:16],
            "name": "U05 · 工程复盘与开发方向 · 离线基线验证",
            "objective": "只用真实旧归档，核查已有机制、实际缺口和最小动作；缺少真实B，不判断能力升降。",
            "baseline_run_id": RUN, "candidate": {"kind": "missing"}, "case_ids": [CASE], "workflow": workflow,
            "analyst": {"kind": "offline_fixture", "name": "离线脚本响应 · retro方法示例", "model": None}}})
        cid = plan["id"]
        context = await call("get_comparison_case", {"comparison_id": cid, "case_id": CASE})
        assert context["candidate"] is None and not context["baseline"]["is_simulation"]
        catalog = context["baseline"]["materials"]
        trace = next(m for m in catalog if m["kind"] == "archive" and m["path"].endswith("/events.jsonl"))
        metrics_material = next(m for m in catalog if m["kind"] == "observed_metrics")
        saved_check = next(m for m in catalog if m["kind"] == "saved_check")

        async def read(material, start=1, count=40):
            return await call("read_comparison_material", {"comparison_id": cid, "case_id": CASE,
                "material_id": material["id"], "start_line": start, "line_count": count})

        events = await read(trace, 97, 2)
        assert "AssertionError: 0" in events["excerpt"] and "max_steps" in events["excerpt"]
        metrics_page = await read(metrics_material)
        assert not metrics_page["truncated"]
        metrics = json.loads(metrics_page["excerpt"])["metrics"]
        assert metrics["model_requests"] == 30 and metrics["tool_calls"] == 33
        pages, positions, start = [], {}, 1
        while True:
            page = await read(saved_check, start)
            if page["truncated"]:
                raise RuntimeError("Saved check page truncated; cannot validate its evidence")
            pages.append(page["excerpt"])
            for offset, line in enumerate(page["excerpt"].splitlines()):
                for identity in ("result", "scope", "self_test"):
                    if f'"id": "{identity}"' in line:
                        positions[identity] = start + offset
            start += page["line_count"]
            if start > page["total_lines"]:
                break
        checks = {c["id"]: c["value"] for c in json.loads("\n".join(pages))["checks"]}
        assert checks["result"] == 0 and checks["self_test"] == 0 and checks["scope"] == 1

        def evidence(material, start=1, count=40):
            return {"material_id": material["id"], "sha256": material["sha256"], "start_line": start, "line_count": count}

        def observation(identity, dimension, title, before, reason, refs, outcome="insufficient"):
            return {"id": identity, "dimension": dimension, "title": title, "before": before, "after": None,
                "outcome": outcome, "reason": reason, "limits": "仅有一次真实A；无真实B。离线脚本示例不证明原因或能力改善。", "evidence": refs}

        request_id = "u05-" + RESPONSE_VERSION
        latest = context.get("latest_analysis")
        revision = (latest["content"]["revision"] if latest and latest["content"]["request_id"] == request_id
                    else latest["revision"] if latest else 0)
        analysis = await call("submit_comparison_case", {"comparison_id": cid, "case_id": CASE, "analysis": {
            "request_id": request_id, "revision": revision,
            "summary": "工具已返回失败信息；匹配失败后因步数限制停止。核查已有机制和恢复机会，暂不确认责任模块。",
            "observations": [
                observation("feedback", "工具与执行恢复", "已有错误反馈，不能直接认定反馈缺失", "事件97：run_shell退出码1，返回AssertionError: 0。", "错误已经暴露。是否需要改工具，应核查实际返回信息及匹配方式。", [evidence(trace, 97, 1)]),
                observation("recovery", "工具与执行恢复", "恢复机会尚需核查", "事件97失败，事件98以max_steps停止。", "这组事件不能证明Agent有机会恢复却忽略了错误，也不能直接证明预算应增加。", [evidence(trace, 97, 2)]),
                observation("verification", "验证行为", "原运行有效自测未满足，已有验证入口需核查", "已有保存检查：result=0、self_test=0、scope=1。", "这些是已保存的独立检查结论；不重新打分，也不据此断言项目缺少测试命令或CI。", [evidence(saved_check, max(1, positions[identity] - 3), 24) for identity in ("result", "self_test", "scope")]),
                observation("resources", "资源与效率", "资源计数不能单独证明浪费", f"30次模型请求、33次工具调用、{metrics['total_tokens']:g} tokens、约{metrics['elapsed_seconds']:.2f}秒。", "重复与无信息增益需结合实际调用内容判断；没有B不能判效率改善。", [evidence(metrics_material)]),
                observation("context", "上下文管理", "压缩质量未覆盖", "归档中没有context_compacted事件。", "没有触发压缩后的信息保留验证，保留未覆盖。", [evidence(metrics_material)], "not_covered"),
            ]}})
        refs = lambda *ids: [{"case_id": CASE, "observation_id": identity} for identity in ids]
        report = await call("submit_comparison_report", {"comparison_id": cid, "report": {
            "request_id": "u05-final-" + RESPONSE_VERSION, "case_report_ids": [analysis["id"]],
            "summary": "U05基线复盘：已存在错误反馈，修复与有效自测未完成。先核查匹配失败、停止时序和既有验证入口；尚不能确认应改哪个Harness模块。缺少真实B，不判断能力升降。",
            "findings": [
                {"title": "编辑失败已报告，责任模块待核查", "outcome": "insufficient", "explanation": "原记录支持失败事实；反馈缺失和忽略错误均不能直接成立。", "refs": refs("feedback", "recovery")},
                {"title": "有效自测未满足，不能直接认定缺少检查工具", "outcome": "insufficient", "explanation": "已有独立检查结果可读取；原运行测试入口是否可见、接通仍需核查。", "refs": refs("verification")},
                {"title": "压缩质量本次未覆盖", "outcome": "not_covered", "explanation": "没有压缩后行为证据，不能给出相关能力结论。", "refs": refs("context")},
            ],
            "recommendations": [
                {"title": "先核查匹配失败与停止时序，再确定最小改动位置",
                 "phenomenon": "最后补丁匹配失败，修复未落地，随后运行达到步数上限。",
                 "cause_status": "hypothesis", "cause": "已有机制：run_shell已返回退出码1和AssertionError: 0。实际缺口：仍需核查匹配方式、换行处理、运行时工具实现及剩余预算；不能确认责任模块，也不能说错误未暴露。",
                 "action": "作用位置尚未确定，候选为通用编辑工具或执行流程。先只读核对原编辑尝试和停止时序，复用已有反馈；确认缺口后才选择最小动作，不直接加预算或新增专用工具。",
                 "priority_reason": "真实失败直接阻断交付，先调查成本较低；优先复用已有机制。新增反馈、检查或指导内容会增加维护与运行负担，需证据支持。",
                 "validation": "后续在任务、模型和预算可比时取得真实B，检查修改落地、有效自测与交付；证明恢复能力还需实际存在可恢复错误及后续行为。",
                 "success_signals": "能定位真正缺口并给出通用最小改动；之后真实运行完成修复和验证，必要时可观察到恢复推进。",
                 "guardrails": "不修改原题、评分或受保护文件，不增加U05定位提示混入同条件比较；调用、耗时和tokens代价单列。", "refs": refs("feedback", "recovery", "resources")},
                {"title": "先核查既有验证入口，暂缓新增检查规则",
                 "phenomenon": "保存的独立检查指出原运行没有对应最终源码的有效成功自测。",
                 "cause_status": "unresolved", "cause": "已有机制：平台已保存结果、自测和保护范围检查。实际缺口：尚未确认原项目已有测试命令、入口可见性与原运行调用路径；外部检查不能代替Agent原自测。",
                 "action": "候选作用位置为执行流程或信息入口。先读取运行当时的项目说明、已有检查命令和调用记录；已有机制未接通时优先修复接入，只有确定缺少必要检查时才考虑最小自动检查。",
                 "priority_reason": "验证缺口影响交付可信度。复用既有检查可减少重复工具和冗余指令；新增检查的维护成本需明确。",
                 "validation": "后续真实B中核对原Agent是否实际执行对应最终源码的检查，并分别记录原自测与外部重检。",
                 "success_signals": "原运行留下有效成功自测和交付证据，既有测试与保护范围保持。",
                 "guardrails": "不把外部补跑算成Agent自测，不改变完成标准；不因一次失败直接认定项目没有CI或测试工具。", "refs": refs("verification")},
            ]}})
        final = await call("get_comparison", {"comparison_id": cid})
        assert final["candidate"] is None and final["state"] == "waiting_candidate"
        assert final["progress"]["assessed"] == 0 and final["progress"]["received"] == 1
        assert report["analyst"]["kind"] == "offline_fixture" and report["is_simulation"]
        with httpx.Client(base_url=api + "/api/v1", trust_env=False, timeout=30) as http:
            saved = http.get(f"/comparisons/{cid}/reports/{report['id']}")
            saved.raise_for_status()
            assert len(saved.json()["case_analyses"][0]["content"]["observations"]) == 5
            assert all(e["source"] == "baseline" and not e["is_simulation"] for o in saved.json()["case_analyses"][0]["content"]["observations"] for e in o["evidence"])
        return {"comparison_id": cid, "report_id": report["id"], "workflow": workflow,
            "url": f"http://127.0.0.1:3100/comparison?comparison={cid}", "progress": final["progress"],
            "mcp_calls": calls, "baseline_is_real": True, "candidate_present": False, "analysis_is_scripted": True,
            "agent_model_requests": 0, "judge_model_requests": 0, "evaluation_runs": 0, "checker_runs": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--receipt", type=Path, default=ROOT / "data/u05-retro-receipt.json")
    args = parser.parse_args()
    parsed = urlsplit(args.api)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Only a local platform root is supported")
    archive = ROOT / "data/evaluation-runs" / RUN
    before = hashes(archive)
    if not before:
        raise RuntimeError("U05 archive is unavailable")
    with httpx.Client(base_url=args.api + "/api/v1", trust_env=False, timeout=30) as http:
        workflow = publish_workflow(http)
    receipt = asyncio.run(submit_baseline(args.api, workflow))
    if before != hashes(archive):
        raise RuntimeError("Original archive changed")
    receipt.update(original_archive_unchanged=True, original_archive_files=len(before))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

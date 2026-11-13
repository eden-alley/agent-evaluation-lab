"""An external stdio client completes the comparison workflow without any model."""
import asyncio
from pathlib import Path
import socket
import sys
import threading
import time
import uvicorn
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from test_comparisons import comparison_env, CASE, analysis_payload, final_payload


def test_external_stdio_reads_materials_and_submits_reports(comparison_env):
    http, _, payload = comparison_env
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(http.app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).parents[1] / "run_mcp.py")],
            env={"LAB_API_URL": f"http://127.0.0.1:{port}", "LAB_CLIENT_NAME": "offline-comparison-client", "PYTHONIOENCODING": "utf-8"})

        async def workflow():
            async with Client(params, read_timeout_seconds=20) as client:
                async def call(name, data=None):
                    result = await client.call_tool(name, data or {})
                    assert not result.is_error, result
                    return result.structured_content
                contract = await call("get_comparison_contract")
                assert contract["schema_version"] == 1
                plan = await call("create_comparison", {"comparison": payload})
                checked = await call("verify_comparison_sources", {"comparison_id": plan["id"]})
                assert checked["source_state"] == "unchanged" and checked["source_checked_at"]
                assert checked["source_state_scope"] == "last_full_verification"
                material = await call("get_comparison_case", {"comparison_id": plan["id"], "case_id": CASE})
                ref = material["baseline"]["materials"][0]
                text = await call("read_comparison_material", {"comparison_id": plan["id"], "case_id": CASE, "material_id": ref["id"], "line_count": 5})
                assert text["sha256"] == ref["sha256"] and text["excerpt"]
                analysis = await call("submit_comparison_case", {"comparison_id": plan["id"], "case_id": CASE, "analysis": analysis_payload(material)})
                assert "excerpt" not in analysis["content"]["observations"][0]["evidence"][0]
                report = await call("submit_comparison_report", {"comparison_id": plan["id"], "report": final_payload(analysis)})
                assert report["is_simulation"] is True and report["recommendations"]
                assert "case_analyses" not in report
                detail = await call("get_comparison", {"comparison_id": plan["id"]})
                assert detail["progress"]["collection_complete"] is True
                packet = await call("prepare_capability_review", {"comparison_id": plan["id"]})
                assert packet["metric_report"]["registry_version"] == "saved-checks-0.2.0"
                friendly = await call("read_capability_material", {"comparison_id": plan["id"], "case_id": CASE,
                    "side": "baseline", "path": "events.jsonl", "line_count": 5})
                assert "AssertionError" in friendly["excerpt"]
                from test_capability_review import document
                lite = await call("submit_capability_review", {"comparison_id": plan["id"], "analysis": document()})
                assert lite["metric_report"]["coverage"]["unassessed"] >= 4
                assert lite["analysis_origin"]["kind"] == "external_agent"
                retry = await call("submit_capability_review", {"comparison_id": plan["id"], "analysis": document()})
                assert retry["id"] == lite["id"]
                assert "case_analyses" not in lite
                assert all("case_evidence" not in m for m in lite["metric_report"]["quality"])
                await call("prepare_capability_review", {"comparison_id": plan["id"]})
                from test_case_explanations import explained_document
                narrated = await call("submit_capability_review", {"comparison_id": plan["id"], "analysis": explained_document()})
                assert narrated["explanation_coverage"]["provided"] == 1
                saved_case = await call("get_comparison_case", {"comparison_id": plan["id"], "case_id": CASE})
                evidence = saved_case["latest_analysis"]["content"]["explanation"]["stages"][0]["evidence"][0]
                assert evidence["event_id"] == 2 and "excerpt" not in evidence and "display_excerpt" not in evidence
        asyncio.run(workflow())
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()
